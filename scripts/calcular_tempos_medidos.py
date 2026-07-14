#!/usr/bin/env python3
"""Preenche app/data/tempos_medidos.json com um motor de rotas.

O que faz
---------
Percorre os pares origem/destino ainda a null na tabela de tempos por
estrada e pede as rotas de carro a um motor, em LOTES (endpoints de
matriz: várias origens e vários destinos num só pedido). Grava depois
de cada lote, por isso pode ser interrompido e retomado à vontade: o
que já está preenchido não volta a ser pedido. Cada par fica com
tempo_min, distancia_km, a fonte e a data do cálculo.

Motores suportados (--motor)
----------------------------
ors            OpenRouteService (recomendado para o protótipo): dados
               do OpenStreetMap, plano gratuito com chave, registo em
               openrouteservice.org. Passar a chave com --chave ou pela
               variável de ambiente ORS_API_KEY.
osrm           Um servidor OSRM próprio (por defeito
               http://localhost:5000). Sem limites, ideal se a
               instituição montar um; ver docs/INTEGRACAO.md.
osrm-publico   O servidor de demonstração do projeto OSRM. Serve para
               um teste pequeno (usar --limite), NÃO para preencher a
               tabela toda: é um serviço partilhado com política de uso
               ligeiro e sem garantias.

Os limites dos planos gratuitos mudam; se o servidor recusar um pedido
por tamanho, baixa o --lote (menos origens por pedido).

Exemplos
--------
python scripts/calcular_tempos_medidos.py --motor ors --chave A_TUA_CHAVE
python scripts/calcular_tempos_medidos.py --motor osrm
python scripts/calcular_tempos_medidos.py --motor osrm-publico --limite 10
python scripts/calcular_tempos_medidos.py --motor ors --filtro santa_cruz
python scripts/calcular_tempos_medidos.py --motor ors --forcar

Nota honesta sobre a qualidade: estes motores usam o OpenStreetMap com
perfis de velocidade genéricos, sem trânsito. Para a Madeira dão tempos
muito melhores do que o modelo local da rede calibrada, mas um par
suspeito merece sempre conferência no Google Maps
(scripts/tempos_medidos_relatorio.py --links e --divergencias).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import requests  # noqa: E402  (dependência do projeto)

from app.core import unidades  # noqa: E402
from app.core.tempos_medidos import FICHEIRO, validar  # noqa: E402

URL_ORS = "https://api.openrouteservice.org/v2/matrix/driving-car"
URL_OSRM_LOCAL = "http://localhost:5000"
URL_OSRM_PUBLICO = "https://router.project-osrm.org"

ERROS_TRANSITORIOS = {429, 500, 502, 503, 504}


def _pedir_matriz(
    motor: str,
    origens: list[tuple[float, float]],
    destinos: list[tuple[float, float]],
    chave: str | None,
    url: str | None,
    tentativas: int = 3,
    pausa_erro: float = 6.0,
) -> tuple[list, list | None]:
    """Um pedido de matriz ao motor. Coordenadas como (lat, lng).

    Devolve (duracoes_s, distancias_m): matrizes com uma linha por
    origem e uma coluna por destino; células sem rota vêm a None.
    """
    for tentativa in range(1, tentativas + 1):
        try:
            if motor == "ors":
                pontos = [[lng, lat] for lat, lng in list(origens) + list(destinos)]
                corpo = {
                    "locations": pontos,
                    "sources": list(range(len(origens))),
                    "destinations": list(range(len(origens), len(pontos))),
                    "metrics": ["duration", "distance"],
                }
                resposta = requests.post(
                    url or URL_ORS,
                    json=corpo,
                    headers={"Authorization": chave or ""},
                    timeout=40,
                )
            else:
                base = (url or URL_OSRM_PUBLICO).rstrip("/")
                coords = ";".join(
                    f"{lng},{lat}" for lat, lng in list(origens) + list(destinos)
                )
                indices_origens = ";".join(str(i) for i in range(len(origens)))
                indices_destinos = ";".join(
                    str(i) for i in range(len(origens), len(origens) + len(destinos))
                )
                resposta = requests.get(
                    f"{base}/table/v1/driving/{coords}",
                    params={
                        "sources": indices_origens,
                        "destinations": indices_destinos,
                        "annotations": "duration,distance",
                    },
                    timeout=40,
                )
            if resposta.status_code in (401, 403):
                raise SystemExit(
                    f"O motor recusou o acesso (HTTP {resposta.status_code}). "
                    "Confirma a chave (--chave ou ORS_API_KEY)."
                )
            if resposta.status_code in ERROS_TRANSITORIOS:
                raise RuntimeError(f"HTTP {resposta.status_code}")
            resposta.raise_for_status()
            dados = resposta.json()
            duracoes = dados.get("durations")
            if duracoes is None:
                raise RuntimeError(f"resposta sem 'durations': {str(dados)[:200]}")
            return duracoes, dados.get("distances")
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001  (rede: repetir com calma)
            if tentativa == tentativas:
                raise
            print(
                f"    aviso: {exc}; nova tentativa em {pausa_erro:.0f}s "
                f"({tentativa}/{tentativas})"
            )
            time.sleep(pausa_erro)
    raise RuntimeError("sem resposta do motor")  # inatingível; acalma o linter


def _pendentes(dados: dict, forcar: bool, filtro: str | None) -> list[tuple[dict, list[str]]]:
    """(medição, uids por calcular), pela ordem do ficheiro."""
    saida: list[tuple[dict, list[str]]] = []
    for m in dados["medicoes"]:
        if filtro and filtro not in m["origem"]:
            continue
        uids = [
            uid
            for uid, valores in m["destinos"].items()
            if forcar or valores.get("tempo_min") is None
        ]
        if uids:
            saida.append((m, uids))
    return saida


def _aplicar_limite(
    pendentes: list[tuple[dict, list[str]]], limite: int | None
) -> list[tuple[dict, list[str]]]:
    if limite is None:
        return pendentes
    saida: list[tuple[dict, list[str]]] = []
    orcamento = limite
    for m, uids in pendentes:
        if orcamento <= 0:
            break
        recorte = uids[:orcamento]
        orcamento -= len(recorte)
        saida.append((m, recorte))
    return saida


def _lotes_por_ilha(
    pendentes: list[tuple[dict, list[str]]], lote: int
) -> list[list[tuple[dict, list[str]]]]:
    """Lotes de até `lote` origens, sem misturar ilhas (não há estrada
    entre a Madeira e o Porto Santo; misturar só enchia a matriz de
    células sem rota)."""
    saida: list[list[tuple[dict, list[str]]]] = []
    atual: list[tuple[dict, list[str]]] = []
    ilha_atual: str | None = None
    for m, uids in pendentes:
        if atual and (len(atual) >= lote or m["ilha"] != ilha_atual):
            saida.append(atual)
            atual = []
        atual.append((m, uids))
        ilha_atual = m["ilha"]
    if atual:
        saida.append(atual)
    return saida


def _contar(dados: dict) -> tuple[int, int]:
    total = feitos = 0
    for m in dados["medicoes"]:
        for valores in m["destinos"].values():
            total += 1
            if valores.get("tempo_min") is not None:
                feitos += 1
    return feitos, total


def preencher(
    dados: dict,
    pedir,
    motor: str,
    chave: str | None = None,
    url: str | None = None,
    lote: int = 5,
    pausa: float = 0.0,
    limite: int | None = None,
    forcar: bool = False,
    filtro: str | None = None,
    gravar=None,
) -> dict:
    """Preenche os pares em falta em `dados` (alterado no sítio).

    `pedir` é a função de matriz (injetável nos testes); `gravar`, se
    dada, é chamada com os dados após cada lote (retoma barata).
    """
    coordenadas = {u["id"]: (u["lat"], u["lng"]) for u in unidades.todas()}
    pendentes = _aplicar_limite(_pendentes(dados, forcar, filtro), limite)
    estatisticas = {"pedidos": 0, "preenchidos": 0, "sem_rota": 0}
    if not pendentes:
        return estatisticas

    hoje = date.today().isoformat()
    lotes = _lotes_por_ilha(pendentes, lote)
    for numero, grupo in enumerate(lotes, start=1):
        origens = [(m["lat"], m["lng"]) for m, _ in grupo]
        uids_uniao = sorted({uid for _, uids in grupo for uid in uids})
        destinos = [coordenadas[uid] for uid in uids_uniao]
        duracoes, distancias = pedir(motor, origens, destinos, chave, url)
        estatisticas["pedidos"] += 1

        for linha, (m, uids) in enumerate(grupo):
            for uid in uids:
                coluna = uids_uniao.index(uid)
                segundos = None
                if duracoes and duracoes[linha] is not None:
                    segundos = duracoes[linha][coluna]
                if segundos is None:
                    estatisticas["sem_rota"] += 1
                    print(f"    sem rota: {m['origem']} -> {uid} (fica a null)")
                    continue
                par = m["destinos"][uid]
                par["tempo_min"] = max(1, int(round(float(segundos) / 60.0)))
                metros = None
                if distancias and distancias[linha] is not None:
                    metros = distancias[linha][coluna]
                if metros is not None:
                    par["distancia_km"] = max(0.1, round(float(metros) / 1000.0, 1))
                par["fonte"] = motor
                par["calculado_em"] = hoje
                estatisticas["preenchidos"] += 1

        if gravar is not None:
            gravar(dados)
        print(
            f"  lote {numero}/{len(lotes)}: {len(origens)} origens x "
            f"{len(uids_uniao)} destinos ({estatisticas['preenchidos']} pares "
            "preenchidos até agora)"
        )
        if pausa and numero < len(lotes):
            time.sleep(pausa)
    return estatisticas


def main() -> int:
    analisador = argparse.ArgumentParser(
        description="Preenche tempos_medidos.json com um motor de rotas "
        "(ver o cabeçalho do ficheiro para detalhes).",
    )
    analisador.add_argument(
        "--motor", choices=["ors", "osrm", "osrm-publico"], default="ors"
    )
    analisador.add_argument(
        "--chave",
        default=os.environ.get("ORS_API_KEY"),
        help="chave do OpenRouteService (ou variável de ambiente ORS_API_KEY)",
    )
    analisador.add_argument(
        "--url",
        default=None,
        help="URL base do motor (por defeito: o ORS oficial, ou "
        f"{URL_OSRM_LOCAL} com --motor osrm)",
    )
    analisador.add_argument(
        "--lote", type=int, default=5, help="origens por pedido (defeito: 5)"
    )
    analisador.add_argument(
        "--pausa",
        type=float,
        default=None,
        help="segundos entre pedidos (defeito: 1.6 no ors, 1.5 no "
        "osrm-publico, 0 no osrm local)",
    )
    analisador.add_argument(
        "--limite", type=int, default=None, help="máximo de pares nesta corrida"
    )
    analisador.add_argument(
        "--forcar", action="store_true", help="recalcula também os pares já preenchidos"
    )
    analisador.add_argument(
        "--filtro", default=None, help="só origens que contenham este texto (ex.: gaula)"
    )
    argumentos = analisador.parse_args()

    if not FICHEIRO.exists():
        print("Não existe app/data/tempos_medidos.json.")
        print("Gera o esqueleto primeiro: python scripts/atualizar_tempos_medidos.py")
        return 1
    dados = json.loads(FICHEIRO.read_text(encoding="utf-8"))
    problemas = validar(dados)
    if problemas:
        print("tempos_medidos.json inválido; corrigir antes de calcular:")
        for p in problemas:
            print(f"  ERRO: {p}")
        return 1

    if argumentos.motor == "ors" and not argumentos.chave:
        print("O OpenRouteService precisa de uma chave (gratuita):")
        print("  1. registo em https://openrouteservice.org")
        print("  2. correr com --chave A_TUA_CHAVE (ou exportar ORS_API_KEY)")
        print("Sem chave, a alternativa é um OSRM local: --motor osrm")
        return 1

    url = argumentos.url
    if argumentos.motor == "osrm" and url is None:
        url = URL_OSRM_LOCAL
    pausa = argumentos.pausa
    if pausa is None:
        pausa = {"ors": 1.6, "osrm": 0.0, "osrm-publico": 1.5}[argumentos.motor]

    if argumentos.motor == "osrm-publico":
        print("AVISO: o servidor público do OSRM é de demonstração, para uso")
        print("ligeiro. Serve para um teste pequeno (--limite 10), não para a")
        print("tabela toda: usa --motor ors (chave gratuita) ou um OSRM local.")
        if argumentos.limite is None:
            print("Recusado sem --limite, para não abusar do serviço.")
            return 1

    def gravar(atual: dict) -> None:
        FICHEIRO.write_text(
            json.dumps(atual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    feitos_antes, total = _contar(dados)
    print(
        f"Por preencher: {total - feitos_antes} de {total} pares "
        f"(motor: {argumentos.motor}, lote: {argumentos.lote})."
    )
    estatisticas = preencher(
        dados,
        _pedir_matriz,
        argumentos.motor,
        chave=argumentos.chave,
        url=url,
        lote=argumentos.lote,
        pausa=pausa,
        limite=argumentos.limite,
        forcar=argumentos.forcar,
        filtro=argumentos.filtro,
        gravar=gravar,
    )
    feitos, total = _contar(dados)
    print(
        f"\nFeito: {estatisticas['pedidos']} pedidos, "
        f"{estatisticas['preenchidos']} pares preenchidos, "
        f"{estatisticas['sem_rota']} sem rota."
    )
    print(f"Tabela: {feitos} de {total} pares preenchidos.")
    print("Vale a pena espreitar: python scripts/tempos_medidos_relatorio.py --divergencias")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
