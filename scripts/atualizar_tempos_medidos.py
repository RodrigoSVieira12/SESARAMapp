#!/usr/bin/env python3
"""Gera (ou atualiza) o esqueleto de app/data/tempos_medidos.json.

O que faz
---------
Cria uma entrada por cada SÍTIO e por cada FREGUESIA de
app/data/localidades.json, com os destinos a medir:

  - o Hospital Dr. Nélio Mendonça (na Madeira);
  - os centros de saúde mais próximos dessa zona, pela UNIÃO de:
      · os 2 mais próximos em linha reta, e
      · os 2 mais próximos pela rede calibrada (tempo estimado).
    A união importa: quando os dois critérios discordam é exatamente
    onde uma medição real mais falta faz (o caso Achada da Rocha:
    Gaula vs Camacha).

Todos os valores começam a null. Enchem-se pelo caminho automático
(scripts/calcular_tempos_medidos.py, com um motor de rotas) ou à mão
com o Google Maps (scripts/tempos_medidos_relatorio.py --links gera os
links prontos). Com a opção --todos, os destinos passam a ser TODAS as
unidades da mesma ilha: o esqueleto fica maior e deixa de ser razoável
preenchê-lo à mão, mas o motor de rotas enche-o na mesma em minutos.

Atualização sem perder trabalho
-------------------------------
Se o ficheiro já existir, as medições preenchidas são PRESERVADAS para
os pares que continuarem a existir. Correr isto depois de editar as
localidades (sítios novos, coordenadas corrigidas) é seguro.

Correr:  python scripts/atualizar_tempos_medidos.py [--todos]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core import localidades, unidades, viagem  # noqa: E402
from app.core.geo import haversine_km  # noqa: E402
from app.core.tempos_medidos import FICHEIRO  # noqa: E402

HOSPITAL_MADEIRA = "hnm"
N_MAIS_PROXIMOS = 2  # por critério (linha reta e rede); a união junta-os


def _origens() -> list[dict]:
    """Uma origem por freguesia e por sítio, com as coordenadas que a
    própria app usa no modo manual (mesmos centros, mesmos centroides)."""
    saida: list[dict] = []
    prep = localidades.carregar()
    for c in prep["concelhos"]:
        for f in c["freguesias"]:
            saida.append(
                {
                    "origem": f"{c['id']}/{f['id']}",
                    "nome": f"{f['nome']} ({c['nome']})",
                    "nivel": "freguesia",
                    "lat": f["centro"]["lat"],
                    "lng": f["centro"]["lng"],
                    "ilha": c["ilha"],
                }
            )
            for s in f.get("sitios", []):
                saida.append(
                    {
                        "origem": f"{c['id']}/{f['id']}/{s['id']}",
                        "nome": f"{s['nome']}, {f['nome']} ({c['nome']})",
                        "nivel": "sitio",
                        "lat": s["lat"],
                        "lng": s["lng"],
                        "ilha": c["ilha"],
                    }
                )
    return saida


def _destinos_para(origem: dict, unidades_ilha: dict, todos: bool) -> list[str]:
    """Ids das unidades a medir a partir desta origem.

    Por defeito: o hospital (na Madeira) e os centros de saúde mais
    próximos, pela UNIÃO de linha reta e rede calibrada — um conjunto
    pequeno, preenchível à mão. Com todos=True: todas as unidades da
    mesma ilha, pensado para o preenchimento automático pelo motor de
    rotas (scripts/calcular_tempos_medidos.py).
    """
    lat, lng = origem["lat"], origem["lng"]

    def _tempo(u: dict) -> float:
        estimado = viagem._tempo_rede(lat, lng, u["lat"], u["lng"])
        return float("inf") if estimado is None else estimado

    escolhidos: list[str] = []
    if origem["ilha"] == "madeira":
        escolhidos.append(HOSPITAL_MADEIRA)

    if todos:
        candidatas = list(unidades_ilha["todas"])
    else:
        centros = unidades_ilha["centros"]
        por_linha_reta = sorted(
            centros, key=lambda u: haversine_km(lat, lng, u["lat"], u["lng"])
        )[:N_MAIS_PROXIMOS]
        por_rede = sorted(centros, key=_tempo)[:N_MAIS_PROXIMOS]
        candidatas = list({x["id"]: x for x in por_rede + por_linha_reta}.values())

    for u in sorted(candidatas, key=_tempo):
        if u["id"] not in escolhidos:
            escolhidos.append(u["id"])
    return escolhidos


def gerar(existente: dict | None, todos: bool = False) -> tuple[dict, dict]:
    """Devolve (dados_novos, resumo). Preserva medições do 'existente'."""
    antigos: dict[str, dict] = {}
    if existente:
        for m in existente.get("medicoes", []):
            antigos[m["origem"]] = m.get("destinos") or {}

    unidades_por_ilha: dict[str, dict] = {}
    for u in unidades.todas():
        ilha = u.get("ilha", "madeira")
        grupo = unidades_por_ilha.setdefault(ilha, {"centros": [], "todas": []})
        grupo["todas"].append(u)
        if u.get("tipo") == "centro_saude":
            grupo["centros"].append(u)

    medicoes: list[dict] = []
    preservados = 0
    for origem in _origens():
        grupo = unidades_por_ilha.get(origem["ilha"], {"centros": [], "todas": []})
        destinos: dict[str, dict] = {}
        for uid in _destinos_para(origem, grupo, todos):
            anterior = antigos.get(origem["origem"], {}).get(uid) or {}
            # Preserva o par antigo INTEIRO (incluindo "fonte" e
            # "calculado_em" do preenchimento automático), por cima do
            # molde a null.
            valores = {"tempo_min": None, "distancia_km": None, **anterior}
            if valores["tempo_min"] is not None:
                preservados += 1
            destinos[uid] = valores
        medicoes.append(
            {
                "origem": origem["origem"],
                "nome": origem["nome"],
                "nivel": origem["nivel"],
                "ilha": origem["ilha"],
                "lat": origem["lat"],
                "lng": origem["lng"],
                "destinos": destinos,
            }
        )

    dados = {
        "versao": "1.0",
        "descricao": [
            "Tempos de viagem por estrada, por zona da RAM, guardados",
            "localmente. Paliativo de protótipo: útil enquanto não há um",
            "serviço de rotas em produção (ver docs/INTEGRACAO.md).",
            "Cada entrada é um sítio ou uma freguesia de localidades.json;",
            "os destinos são o hospital e os centros de saúde mais próximos",
            "(ou todas as unidades da ilha, se gerado com --todos).",
        ],
        "como_preencher": [
            "AUTOMÁTICO (recomendado):",
            "  python scripts/calcular_tempos_medidos.py --motor ors --chave X",
            "  (chave gratuita em openrouteservice.org) ou --motor osrm com",
            "  um servidor local. Preenche tempo, distância e a fonte.",
            "MANUAL (para conferir ou corrigir pares):",
            "  python scripts/tempos_medidos_relatorio.py --links, abrir o",
            "  link no Google Maps (modo carro) e escrever tempo_min",
            "  (minutos, inteiro) e distancia_km (1 casa decimal).",
            "Deixar a null o que não estiver preenchido: a app recua para a",
            "rede calibrada. Validar no fim: python scripts/validar_dados.py",
        ],
        "como_remover": [
            "Apagar este ficheiro desativa a funcionalidade (sem erros).",
            "VIAGEM_TEMPOS_MEDIDOS=0 desliga sem apagar nada.",
            "app/core/tempos_medidos.py também pode ser apagado: o viagem.py",
            "importa-o de forma tolerante (módulo amovível por desenho).",
        ],
        "parametros": {
            "raio_ancoragem_km": 3.0,
            "nota": (
                "Raio máximo entre a posição do utente e a zona registada "
                "mais próxima para a medição ser usada; fora dele, rede "
                "calibrada. O pequeno desvio até à âncora é somado ao tempo."
            ),
        },
        "medicoes": medicoes,
    }
    total_pares = sum(len(m["destinos"]) for m in medicoes)
    resumo = {
        "origens": len(medicoes),
        "pares": total_pares,
        "preservados": preservados,
    }
    return dados, resumo


def main() -> int:
    analisador = argparse.ArgumentParser(
        description="Gera ou atualiza o esqueleto de tempos_medidos.json "
        "(preserva medições preenchidas).",
    )
    analisador.add_argument(
        "--todos",
        action="store_true",
        help="inclui TODAS as unidades da mesma ilha como destinos, em vez "
        "de só as mais próximas (pensado para o preenchimento automático "
        "com scripts/calcular_tempos_medidos.py)",
    )
    argumentos = analisador.parse_args()

    existente = None
    if FICHEIRO.exists():
        existente = json.loads(FICHEIRO.read_text(encoding="utf-8"))
    dados, resumo = gerar(existente, todos=argumentos.todos)
    FICHEIRO.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Escrito: {FICHEIRO}")
    print(
        f"  {resumo['origens']} origens (freguesias + sítios), "
        f"{resumo['pares']} pares origem/destino, "
        f"{resumo['preservados']} medições preservadas."
    )
    print("Próximo passo (automático): python scripts/calcular_tempos_medidos.py --motor ors --chave X")
    print("            (ou manual):    python scripts/tempos_medidos_relatorio.py --links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
