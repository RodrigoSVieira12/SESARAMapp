"""Tempos de espera em tempo real (SESARAM / sistema SEISRAM).

Fontes: as duas páginas públicas embebidas em
https://www.sesaram.pt/portal/utente/urgencia/tempo-de-espera

  1. Hospital Dr. Nélio Mendonça (URL_HOSPITAL): duas tabelas — utentes
     em espera e "tempo médio / nº atendidos" — por área clínica e pelas
     CINCO classificações de Manchester (Emergente … Não Urgente). Ou
     seja, dá para mostrar ao utente a espera DA COR DELE.
  2. Centros de saúde com atendimento urgente (URL_CENTROS): uma linha
     por unidade, com "Nº utentes em espera" e "tempo médio / nº
     atendidos" da última hora.

Decisões de robustez e ética (importantes):
- Cache em ficheiro com TTL curto: nunca se martela o site — no máximo
  um pedido a cada TTL_SEGUNDOS por fonte, com User-Agent honesto.
- Cache NEGATIVA: depois de uma falha, não se volta a tentar já a
  seguir; serve-se o que houver, marcado como desatualizado.
- Degradação graciosa: sem dados, a app diz "indisponível" e decide só
  por distância e horários, exatamente como antes.
- A "NOTA" de cortesia do site aparece MESMO quando há dados; por isso
  a indisponibilidade mede-se pela ausência de números, nunca pela
  presença da nota.
- O caminho robusto a prazo é uma API oficial do SESARAM (ver README);
  isto é a versão possível hoje, para o protótipo.

A regra de troca (escolher_principal) é EXPERIMENTAL e está por validar
clinicamente: só se aplica a laranja/amarelo, e só troca a unidade mais
próxima se a poupança estimada for grande e o desvio pequeno.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .sugestoes import normalizar

# ------------------------------------------------------------- fontes -- #

URL_HOSPITAL = "https://web.sesaram.pt/SEISRAM_WBE_WEB/PT/TEMPO-ESPERA.awp?t=1"
URL_CENTROS = "https://web.sesaram.pt/SEISRAM_WBE_WEB/PT/TEMPO-ESPERA-CSP.awp"

TEMPO_LIMITE_HTTP = 6            # segundos por pedido
TTL_SEGUNDOS = 180               # frescura normal do cache (e cache negativa)
VALIDADE_MAXIMA_SEGUNDOS = 1800  # com a fonte em baixo, o cache antigo vale 30 min

# Regra de troca (EXPERIMENTAL — por validar clinicamente):
VELOCIDADE_MEDIA_KMH = 50        # RECUO da viagem (v0.11 usa app/core/viagem.py)
POUPANCA_MINIMA_MIN = 30         # só trocar se poupar pelo menos isto
DESVIO_MAXIMO_KM = 15            # e sem obrigar a um grande desvio

_PASTA_DATA = Path(__file__).resolve().parents[1] / "data"
_FICHEIRO_CACHE = _PASTA_DATA / "espera_cache.json"
_FICHEIRO_NOMES = _PASTA_DATA / "espera_nomes.json"

NOMES_PARA_ID: dict[str, str] = {
    normalizar(nome): unidade_id
    for nome, unidade_id in json.loads(
        _FICHEIRO_NOMES.read_text(encoding="utf-8")
    )["nomes"].items()
}

# Cabeçalhos das colunas do hospital (já normalizados) → cor do projeto.
CLASSIFICACOES_PARA_COR = {
    "emergente": "vermelho",
    "muito urgente": "laranja",
    "urgente": "amarelo",
    "pouco urgente": "verde",
    "nao urgente": "azul",
}

# ------------------------------------------------------------ parsing -- #

_RE_HORAS = re.compile(r"(\d+)\s*h\s*(\d*)", re.I)
_RE_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")
_RE_MINUTOS = re.compile(r"(\d+)\s*m", re.I)
_RE_INTEIRO = re.compile(r"^\d+$")
# Uma célula "parece um tempo" se tiver dígitos com h, m ou hh:mm.
_RE_PARECE_TEMPO = re.compile(r"\d\s*[hm]|\d{1,2}:\d{2}", re.I)


def interpretar_tempo(texto: str) -> int | None:
    """"8m" → 8; "2h37" → 157; "1h" → 60; "1:05" → 65; lixo → None."""
    limpo = (texto or "").strip().lower()
    if not limpo:
        return None
    encontrado = _RE_HHMM.match(limpo)
    if encontrado:
        return int(encontrado.group(1)) * 60 + int(encontrado.group(2))
    encontrado = _RE_HORAS.search(limpo)
    if encontrado:
        return int(encontrado.group(1)) * 60 + int(encontrado.group(2) or 0)
    encontrado = _RE_MINUTOS.search(limpo)
    if encontrado:
        return int(encontrado.group(1))
    return None


def interpretar_tempo_e_atendidos(texto: str) -> tuple[int | None, int | None]:
    """"26m / 16" → (26, 16); "2h37 / 7" → (157, 7); "" → (None, None)."""
    limpo = (texto or "").strip()
    if not limpo:
        return None, None
    partes = limpo.split("/")
    tempo = interpretar_tempo(partes[0])
    atendidos = None
    if len(partes) > 1:
        digitos = re.search(r"\d+", partes[1])
        if digitos:
            atendidos = int(digitos.group())
    return tempo, atendidos


def extrair_ultima_atualizacao(html: str) -> str | None:
    texto = normalizar(BeautifulSoup(html, "html.parser").get_text(" "))
    encontrado = re.search(
        r"ultima atualizacao:?\s*(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2})", texto
    )
    return encontrado.group(1) if encontrado else None


def _celulas(linha) -> list[str]:
    return [c.get_text(" ", strip=True) for c in linha.find_all(["td", "th"])]


def extrair_centros(html: str) -> dict[str, dict]:
    """{nome_normalizado: {nome_site, em_espera, tempo_medio_min, atendidos}}.

    Lê qualquer tabela com linhas "NOME | inteiro | tempo": robusto a
    mudanças de estilo, desde que a estrutura de tabela se mantenha.
    """
    soup = BeautifulSoup(html, "html.parser")
    saida: dict[str, dict] = {}
    for linha in soup.find_all("tr"):
        celulas = _celulas(linha)
        if len(celulas) < 2:
            continue
        nome = celulas[0].strip()
        chave = normalizar(nome)
        if not (2 <= len(nome) <= 60) or "atualiza" in chave or "utentes" in chave:
            continue
        em_espera = next(
            (int(c) for c in celulas[1:] if _RE_INTEIRO.match(c.strip())), None
        )
        celula_tempo = next(
            (c for c in celulas[1:] if _RE_PARECE_TEMPO.search(c)), ""
        )
        tempo, atendidos = interpretar_tempo_e_atendidos(celula_tempo)
        if em_espera is None and tempo is None:
            continue  # linha decorativa ou de cabeçalho
        saida[chave] = {
            "nome_site": nome,
            "em_espera": em_espera,
            "tempo_medio_min": tempo,
            "atendidos": atendidos,
        }
    return saida


def extrair_hospital(html: str) -> dict:
    """Agrega as duas tabelas do hospital por cor de Manchester.

    Devolve {"por_cor": {cor: {em_espera, tempo_medio_min, atendidos}},
             "geral": {…}}. As médias são ponderadas pelo nº de
    atendidos de cada área clínica. Como as células decidem sozinhas o
    que são (inteiro = contagem; "26m / 16" = tempo), não interessa qual
    das tabelas é qual.
    """
    soup = BeautifulSoup(html, "html.parser")
    acumulado = {
        cor: {"em_espera": 0, "soma_tempo": 0, "peso": 0, "atendidos": 0, "tem_dados": False}
        for cor in CLASSIFICACOES_PARA_COR.values()
    }

    for tabela in soup.find_all("table"):
        linhas = tabela.find_all("tr")
        mapa_colunas: dict[int, str] = {}
        for linha in linhas:
            celulas = _celulas(linha)
            candidato = {
                indice: CLASSIFICACOES_PARA_COR[normalizar(c)]
                for indice, c in enumerate(celulas)
                if normalizar(c) in CLASSIFICACOES_PARA_COR
            }
            if len(candidato) >= 3:
                mapa_colunas = candidato
                continue
            if not mapa_colunas:
                continue
            for indice, cor in mapa_colunas.items():
                if indice >= len(celulas):
                    continue
                texto = celulas[indice].strip()
                if not texto:
                    continue
                registo = acumulado[cor]
                if _RE_PARECE_TEMPO.search(texto):
                    tempo, atendidos = interpretar_tempo_e_atendidos(texto)
                    if tempo is not None:
                        peso = atendidos or 1
                        registo["soma_tempo"] += tempo * peso
                        registo["peso"] += peso
                        registo["atendidos"] += atendidos or 0
                        registo["tem_dados"] = True
                elif _RE_INTEIRO.match(texto):
                    registo["em_espera"] += int(texto)
                    registo["tem_dados"] = True

    def _fechar(registo: dict) -> dict:
        tempo = (
            int(registo["soma_tempo"] / registo["peso"] + 0.5)
            if registo["peso"]
            else None
        )
        return {
            "em_espera": registo["em_espera"],
            "tempo_medio_min": tempo,
            "atendidos": registo["atendidos"] or None,
        }

    por_cor = {
        cor: _fechar(registo)
        for cor, registo in acumulado.items()
        if registo["tem_dados"]
    }

    geral = {
        "em_espera": sum(r["em_espera"] for r in acumulado.values()),
        "soma_tempo": sum(r["soma_tempo"] for r in acumulado.values()),
        "peso": sum(r["peso"] for r in acumulado.values()),
        "atendidos": sum(r["atendidos"] for r in acumulado.values()),
        "tem_dados": any(r["tem_dados"] for r in acumulado.values()),
    }
    return {
        "por_cor": por_cor,
        "geral": _fechar(geral) if geral["tem_dados"] else {},
    }


# --------------------------------------------------- descarga e cache -- #

def _obter_html(url: str) -> str:
    """Pedido HTTP às páginas do SESARAM (separado para os testes o simularem)."""
    resposta = requests.get(
        url,
        timeout=TEMPO_LIMITE_HTTP,
        headers={"User-Agent": "OndeIr-prototipo-academico (SESARAM; ver README)"},
    )
    resposta.raise_for_status()
    return resposta.text


def _agora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def descarregar() -> dict:
    """Vai às duas fontes e devolve o pacote pronto a guardar em cache."""
    unidades_encontradas: dict[str, dict] = {}
    por_mapear: list[str] = []
    erros: list[str] = []

    try:
        html = _obter_html(URL_CENTROS)
        atualizado = extrair_ultima_atualizacao(html)
        for chave, dados in extrair_centros(html).items():
            unidade_id = NOMES_PARA_ID.get(chave)
            if unidade_id:
                unidades_encontradas[unidade_id] = {
                    "tipo_dados": "geral",
                    "em_espera": dados["em_espera"],
                    "tempo_medio_min": dados["tempo_medio_min"],
                    "atendidos": dados["atendidos"],
                    "fonte": "centros_saude",
                    "atualizado_no_site": atualizado,
                }
            else:
                por_mapear.append(dados["nome_site"])
    except Exception as exc:  # noqa: BLE001 — a app segue sem tempos
        erros.append(f"centros_saude: {exc}")

    try:
        html = _obter_html(URL_HOSPITAL)
        atualizado = extrair_ultima_atualizacao(html)
        hospital = extrair_hospital(html)
        if hospital["por_cor"] or hospital["geral"]:
            unidades_encontradas["hnm"] = {
                "tipo_dados": "por_cor",
                "por_cor": hospital["por_cor"],
                "geral": hospital["geral"],
                "fonte": "hospital",
                "atualizado_no_site": atualizado,
            }
    except Exception as exc:  # noqa: BLE001
        erros.append(f"hospital: {exc}")

    return {
        "obtido_em": _agora_iso(),
        "ok": bool(unidades_encontradas),
        "erro": "; ".join(erros) or None,
        "unidades": unidades_encontradas,
        "por_mapear": por_mapear,
    }


def _ler_cache() -> dict | None:
    try:
        return json.loads(_FICHEIRO_CACHE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — sem cache é um estado normal
        return None


def _gravar_cache(pacote: dict) -> None:
    _FICHEIRO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _FICHEIRO_CACHE.write_text(
        json.dumps(pacote, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _idade_segundos(pacote: dict | None) -> float | None:
    if not pacote or not pacote.get("obtido_em"):
        return None
    try:
        obtido = datetime.fromisoformat(pacote["obtido_em"])
    except ValueError:
        return None
    return (datetime.now() - obtido).total_seconds()


def _com_estado(pacote: dict) -> dict:
    idade = _idade_segundos(pacote) or 0
    return pacote | {
        "disponivel": bool(pacote.get("unidades")),
        "desatualizado": bool(pacote.get("dados_de")) or idade > TTL_SEGUNDOS,
    }


def obter(force: bool = False) -> dict:
    """Tempos de espera, com cache. Pode ir à rede (na máquina do utilizador).

    - cache fresco (≤ TTL) → devolve-o sem rede. Isto inclui um ERRO
      fresco: é a cache negativa que evita insistir num site em baixo.
    - caso contrário descarrega; se falhar mas houver dados antigos
      ainda dentro da validade, herda-os e marca-os como desatualizados.
    """
    cache = _ler_cache()
    idade = _idade_segundos(cache)
    if cache is not None and not force and idade is not None and idade <= TTL_SEGUNDOS:
        return _com_estado(cache)

    novo = descarregar()
    if (
        not novo["ok"]
        and cache
        and cache.get("unidades")
        and (idade or 0) <= VALIDADE_MAXIMA_SEGUNDOS
    ):
        novo = novo | {
            "unidades": cache["unidades"],
            "dados_de": cache.get("dados_de") or cache.get("obtido_em"),
        }
    _gravar_cache(novo)
    return _com_estado(novo)


def do_cache() -> dict:
    """Só leitura do ficheiro — NUNCA vai à rede (usado pelo encaminhamento)."""
    cache = _ler_cache()
    if not cache:
        return {"disponivel": False, "desatualizado": False, "unidades": {}, "obtido_em": None}
    if (_idade_segundos(cache) or 0) > VALIDADE_MAXIMA_SEGUNDOS:
        return {
            "disponivel": False,
            "desatualizado": True,
            "unidades": {},
            "obtido_em": cache.get("obtido_em"),
        }
    return _com_estado(cache)


# ----------------------------------------------- uso pelo encaminhamento -- #

def para_unidade(esperas: dict, unidade_id: str, cor: str | None = None) -> dict | None:
    """Bloco 'tempo_espera' pronto a embutir no resumo de uma unidade.

    No hospital prefere-se a coluna DA COR do utente; se ela estiver
    vazia, cai-se no agregado geral. Devolve None quando não há nada."""
    registo = (esperas or {}).get("unidades", {}).get(unidade_id)
    if not registo:
        return None
    base = {
        "atualizado_no_site": registo.get("atualizado_no_site"),
        "fonte": registo.get("fonte"),
    }

    def _valido(dados: dict | None) -> bool:
        return bool(dados) and (
            dados.get("tempo_medio_min") is not None
            or dados.get("em_espera") is not None
        )

    if registo.get("tipo_dados") == "por_cor":
        da_cor = (registo.get("por_cor") or {}).get(cor) if cor else None
        if _valido(da_cor):
            return base | {
                "ambito": "cor",
                "minutos": da_cor.get("tempo_medio_min"),
                "em_espera": da_cor.get("em_espera"),
                "atendidos": da_cor.get("atendidos"),
            }
        geral = registo.get("geral") or {}
        if not _valido(geral):
            return None
        return base | {
            "ambito": "geral",
            "minutos": geral.get("tempo_medio_min"),
            "em_espera": geral.get("em_espera"),
            "atendidos": geral.get("atendidos"),
        }

    if not _valido(registo):
        return None
    return base | {
        "ambito": "geral",
        "minutos": registo.get("tempo_medio_min"),
        "em_espera": registo.get("em_espera"),
        "atendidos": registo.get("atendidos"),
    }


def tempo_total_estimado(resumo: dict) -> float | None:
    """Viagem estimada + espera atual.

    v0.11: usa a estimativa POR ESTRADA (resumo["tempo_viagem"], de
    app/core/viagem.py) quando existe — antes somava-se uma espera real
    a uma viagem em linha reta a 50 km/h, ou seja, uma medição a um
    palpite. O cálculo antigo mantém-se como recuo (resumos antigos,
    testes, unidades sem estimativa)."""
    minutos = (resumo.get("tempo_espera") or {}).get("minutos")
    if minutos is None:
        return None
    viagem_min = (resumo.get("tempo_viagem") or {}).get("minutos")
    if viagem_min is not None:
        return float(viagem_min) + minutos
    viagem = (resumo.get("distancia_km") or 0) / VELOCIDADE_MEDIA_KMH * 60
    return viagem + minutos


def escolher_principal(abertas: list[dict]) -> tuple[dict | None, list[dict], dict | None]:
    """REGRA EXPERIMENTAL (por validar clinicamente): pode preferir uma
    unidade um pouco mais longe se o tempo total estimado (viagem +
    espera) poupar ≥ POUPANCA_MINIMA_MIN e o desvio for ≤ DESVIO_MAXIMO_KM.

    Só é chamada para laranja/amarelo. Sem dados dos DOIS lados, nunca
    troca. Devolve (principal, restantes_por_ordem, troca|None)."""
    if not abertas:
        return None, [], None
    original = abertas[0]
    total_original = tempo_total_estimado(original)
    escolhida, total_escolhida = original, total_original

    if total_original is not None:
        for candidata in abertas[1:4]:
            total = tempo_total_estimado(candidata)
            if total is None:
                continue
            if (
                total < total_escolhida
                and (total_original - total) >= POUPANCA_MINIMA_MIN
                and (candidata["distancia_km"] - original["distancia_km"]) <= DESVIO_MAXIMO_KM
            ):
                escolhida, total_escolhida = candidata, total

    if escolhida is original:
        return original, abertas[1:], None

    restantes = [original] + [u for u in abertas[1:] if u is not escolhida]
    troca = {
        "preterida": original,
        "total_preterida_min": int(total_original + 0.5),
        "total_escolhida_min": int(total_escolhida + 0.5),
    }
    return escolhida, restantes, troca
