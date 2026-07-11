"""Tempo de viagem por estrada (v0.11).

Porquê: até à v0.10, "perto" era distância em linha reta e a viagem
estimava-se a 50 km/h. Na Madeira isso engana — o Curral das Freiras tem
o Funchal "encostado" no mapa e uma serra pelo meio; a via rápida faz o
contrário, encurta em tempo o que parece longe em quilómetros. A regra
de troca (viagem + espera) somava por isso uma medição real (espera do
SEISRAM) a um palpite (linha reta). Este módulo substitui o palpite por
uma estimativa por estrada, SEM enviar a localização de ninguém para
fora e SEM depender de serviços externos.

Como (três camadas, da mais rica para a mais simples):

1. OSRM opcional — se a variável de ambiente VIAGEM_OSRM_URL apontar
   para um servidor de rotas (idealmente alojado na rede do SESARAM),
   usa-se o serviço /table dele: um único pedido devolve os tempos para
   todas as unidades. Com cache, tempo limite curto, arrefecimento após
   falha e recuo automático para a camada 2. Por omissão está DESLIGADO:
   usar o servidor público de demonstração implicaria enviar coordenadas
   de utentes para terceiros (RGPD) — decisão que pertence à instituição.

2. Rede calibrada (a camada por omissão) — app/data/rede_viagem.json
   descreve a Madeira como ~16 pontos de referência ligados pelos troços
   de estrada REAIS (VR1, VE3, VE4, ER101, ...) com tempos típicos. O
   relevo entra como "barreiras": segmentos que os acessos em linha reta
   não podem atravessar (a crista do Curral, o Pico Grande). O tempo
   entre dois pontos quaisquer é o caminho mais curto nesse grafo
   (Dijkstra), com os acessos curtos estimados pela camada 3. Tal como
   os fluxogramas clínicos, é DADO EDITÁVEL, não código: quem conhece a
   ilha corrige um número; a validação no arranque apanha erros.

3. Modelo local — para trajetos curtos (mesmo vale) e para ligar a
   origem/destino aos nós da rede: linha reta × fator de desvio, com
   velocidades por escalão. Grosseiro, mas assumidamente grosseiro, e
   só usado em distâncias pequenas, onde o erro é limitado.

Regra da ilha: entre ilhas diferentes não há tempo de carro — devolve-se
None e quem chama decide (o encaminhamento já nunca atravessa o mar).

Privacidade: nas camadas 2 e 3 nenhuma coordenada sai do servidor. A
camada 1 só existe se a instituição a configurar conscientemente.
"""

from __future__ import annotations

import heapq
import json
import os
import time
from pathlib import Path

import requests

from .geo import haversine_km

# ------------------------------------------------------------ ficheiros -- #

_PASTA_DATA = Path(__file__).resolve().parents[1] / "data"
FICHEIRO_REDE = _PASTA_DATA / "rede_viagem.json"

# Caixa aproximada da RAM (mesma de scripts/validar_dados.py).
_LAT_MIN, _LAT_MAX = 32.3, 33.3
_LNG_MIN, _LNG_MAX = -17.5, -16.0

ILHAS_CONHECIDAS = {"madeira", "porto_santo"}

# ------------------------------------------------------------------ OSRM -- #

VARIAVEL_OSRM = "VIAGEM_OSRM_URL"
TEMPO_LIMITE_OSRM = 3.0          # segundos por pedido
TTL_OSRM_SEGUNDOS = 600          # cache de respostas
ARREFECIMENTO_OSRM_SEGUNDOS = 120  # após falha, não insistir já a seguir

_cache_osrm: dict[tuple, tuple[float, list]] = {}
# "Nunca falhou" tem de ser -infinito, não 0.0: logo após o arranque
# time.monotonic() pode valer poucos segundos e "monotonic() - 0.0" cairia
# dentro da janela de arrefecimento, desligando o OSRM sem razão.
_NUNCA_FALHOU = float("-inf")
_osrm_falhou_em: float = _NUNCA_FALHOU


class ErroRedeViagem(ValueError):
    """Rede de viagem inválida (apanhado no arranque, como nos fluxogramas)."""


# ---------------------------------------------------------------- rede --- #

_rede_cache: dict | None = None


def carregar_rede(recarregar: bool = False) -> dict:
    """Carrega e VALIDA a rede uma única vez (erros rebentam no arranque)."""
    global _rede_cache
    if _rede_cache is None or recarregar:
        dados = json.loads(FICHEIRO_REDE.read_text(encoding="utf-8"))
        problemas = validar_rede(dados)
        if problemas:
            raise ErroRedeViagem(
                "rede_viagem.json inválido:\n- " + "\n- ".join(problemas)
            )
        _rede_cache = _preparar(dados)
    return _rede_cache


def validar_rede(dados: dict) -> list[str]:
    """Lista de problemas (vazia = ok). Usada aqui e por validar_dados.py."""
    problemas: list[str] = []
    nos = dados.get("nos")
    ligacoes = dados.get("ligacoes")
    if not isinstance(nos, list) or not nos:
        return ["'nos' em falta ou vazio"]
    if not isinstance(ligacoes, list):
        return ["'ligacoes' em falta"]

    por_id: dict[str, dict] = {}
    for no in nos:
        nid = no.get("id")
        if not nid or not isinstance(nid, str):
            problemas.append(f"nó sem id: {no!r}")
            continue
        if nid in por_id:
            problemas.append(f"id de nó repetido: {nid}")
        por_id[nid] = no
        lat, lng = no.get("lat"), no.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            problemas.append(f"nó {nid}: lat/lng em falta")
        elif not (_LAT_MIN <= lat <= _LAT_MAX and _LNG_MIN <= lng <= _LNG_MAX):
            problemas.append(f"nó {nid}: coordenadas fora da RAM ({lat}, {lng})")
        if no.get("ilha") not in ILHAS_CONHECIDAS:
            problemas.append(f"nó {nid}: ilha desconhecida {no.get('ilha')!r}")

    vistas: set[frozenset] = set()
    for lig in ligacoes:
        entre = lig.get("entre")
        if not isinstance(entre, list) or len(entre) != 2:
            problemas.append(f"ligação sem par 'entre': {lig!r}")
            continue
        a, b = entre
        if a == b:
            problemas.append(f"ligação de um nó a si próprio: {a}")
            continue
        for nid in (a, b):
            if nid not in por_id:
                problemas.append(f"ligação refere nó inexistente: {nid}")
        if a in por_id and b in por_id:
            if por_id[a].get("ilha") != por_id[b].get("ilha"):
                problemas.append(f"ligação atravessa o mar: {a} ↔ {b}")
            par = frozenset((a, b))
            if par in vistas:
                problemas.append(f"ligação repetida: {a} ↔ {b}")
            vistas.add(par)
        minutos = lig.get("minutos")
        if not isinstance(minutos, (int, float)) or minutos <= 0:
            problemas.append(f"ligação {a} ↔ {b}: minutos inválidos ({minutos!r})")

    # Conetividade por ilha: numa ilha com 2+ nós, todos devem ligar-se
    # entre si (senão o Dijkstra pode não encontrar caminho).
    if not problemas:
        for ilha in {no["ilha"] for no in por_id.values()}:
            ids_ilha = [nid for nid, no in por_id.items() if no["ilha"] == ilha]
            if len(ids_ilha) < 2:
                continue
            vizinhos: dict[str, list[str]] = {nid: [] for nid in ids_ilha}
            for lig in ligacoes:
                a, b = lig["entre"]
                if a in vizinhos and b in vizinhos:
                    vizinhos[a].append(b)
                    vizinhos[b].append(a)
            alcancados, fila = {ids_ilha[0]}, [ids_ilha[0]]
            while fila:
                for v in vizinhos[fila.pop()]:
                    if v not in alcancados:
                        alcancados.add(v)
                        fila.append(v)
            soltos = sorted(set(ids_ilha) - alcancados)
            if soltos:
                problemas.append(f"nós sem ligação ao resto da ilha {ilha}: {', '.join(soltos)}")

    for barreira in dados.get("barreiras", []):
        for extremo in ("de", "para"):
            ponto = barreira.get(extremo)
            if (
                not isinstance(ponto, list)
                or len(ponto) != 2
                or not all(isinstance(x, (int, float)) for x in ponto)
            ):
                problemas.append(f"barreira {barreira.get('nome')!r}: '{extremo}' inválido")

    modelo = dados.get("modelo_local") or {}
    for chave in ("tempo_arranque_min", "raio_ligacao_km", "alcance_direto_km"):
        valor = modelo.get(chave)
        if not isinstance(valor, (int, float)) or valor < 0:
            problemas.append(f"modelo_local.{chave} inválido ({valor!r})")
    for chave in ("fator_desvio", "velocidade_kmh"):
        escaloes = modelo.get(chave)
        if not isinstance(escaloes, list) or not escaloes or not all(
            isinstance(e, list) and len(e) == 2 and all(isinstance(x, (int, float)) for x in e) and e[1] > 0
            for e in escaloes
        ):
            problemas.append(f"modelo_local.{chave} inválido")

    return problemas


def _preparar(dados: dict) -> dict:
    """Estruturas prontas a usar: índice de nós e lista de adjacência."""
    por_id = {no["id"]: no for no in dados["nos"]}
    vizinhos: dict[str, list[tuple[str, float]]] = {nid: [] for nid in por_id}
    for lig in dados["ligacoes"]:
        a, b = lig["entre"]
        minutos = float(lig["minutos"])
        vizinhos[a].append((b, minutos))
        vizinhos[b].append((a, minutos))
    barreiras = [
        (tuple(b["de"]), tuple(b["para"])) for b in dados.get("barreiras", [])
    ]
    return {
        "por_id": por_id,
        "vizinhos": vizinhos,
        "barreiras": barreiras,
        "modelo": dados["modelo_local"],
        "versao": dados.get("versao"),
    }


# ----------------------------------------------------------- geometria --- #

def _orientacao(p, q, r) -> int:
    valor = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if abs(valor) < 1e-12:
        return 0
    return 1 if valor > 0 else 2


def _no_segmento(p, q, r) -> bool:
    return (
        min(p[0], r[0]) - 1e-12 <= q[0] <= max(p[0], r[0]) + 1e-12
        and min(p[1], r[1]) - 1e-12 <= q[1] <= max(p[1], r[1]) + 1e-12
    )


def _segmentos_cruzam(p1, p2, q1, q2) -> bool:
    """Interseção clássica de segmentos (em graus; a esta escala chega)."""
    o1, o2 = _orientacao(p1, p2, q1), _orientacao(p1, p2, q2)
    o3, o4 = _orientacao(q1, q2, p1), _orientacao(q1, q2, p2)
    if o1 != o2 and o3 != o4:
        return True
    if o1 == 0 and _no_segmento(p1, q1, p2):
        return True
    if o2 == 0 and _no_segmento(p1, q2, p2):
        return True
    if o3 == 0 and _no_segmento(q1, p1, q2):
        return True
    if o4 == 0 and _no_segmento(q1, p2, q2):
        return True
    return False


def _cruza_barreira(p1, p2, barreiras) -> bool:
    return any(_segmentos_cruzam(p1, p2, b1, b2) for b1, b2 in barreiras)


# -------------------------------------------------------- modelo local --- #

def _escalao(valor: float, escaloes: list[list[float]]) -> float:
    for limite, resultado in escaloes:
        if valor <= limite:
            return resultado
    return escaloes[-1][1]


def _minutos_locais(d_km: float, modelo: dict) -> float:
    """Trajeto curto: linha reta × fator de desvio, à velocidade do escalão.

    Não inclui o tempo de arranque — esse soma-se UMA vez no fim, porque
    representa "chegar ao carro / estacionar", não cada troço.
    """
    fator = _escalao(d_km, modelo["fator_desvio"])
    d_estrada = d_km * fator
    velocidade = _escalao(d_estrada, modelo["velocidade_kmh"])
    return d_estrada / velocidade * 60.0


# ------------------------------------------------------------- grafo ----- #

def ilha_do_ponto(lat: float, lng: float, rede: dict | None = None) -> str:
    """Ilha estimada: a do nó da rede mais próximo (coerente com o routing)."""
    rede = rede or carregar_rede()
    return min(
        rede["por_id"].values(),
        key=lambda no: haversine_km(lat, lng, no["lat"], no["lng"]),
    )["ilha"]


def _ligacoes_de_acesso(lat: float, lng: float, rede: dict, ilha: str) -> list[tuple[str, float]]:
    """Nós da rede a que um ponto se pode "ligar" pelo modelo local.

    Regra: todos os nós da mesma ilha dentro do raio, DESDE QUE a linha
    reta não atravesse uma barreira de relevo. Se nenhum couber no raio
    (zonas periféricas), usam-se os 2 mais próximos que não cruzem
    barreiras; em último recurso, o mais próximo de todos — um ponto
    nunca fica desligado da rede.
    """
    modelo = rede["modelo"]
    candidatos: list[tuple[float, str, bool]] = []  # (dist, id, cruza_barreira)
    for nid, no in rede["por_id"].items():
        if no["ilha"] != ilha:
            continue
        d = haversine_km(lat, lng, no["lat"], no["lng"])
        cruza = _cruza_barreira((lat, lng), (no["lat"], no["lng"]), rede["barreiras"])
        candidatos.append((d, nid, cruza))
    if not candidatos:
        return []
    candidatos.sort()

    livres = [(d, nid) for d, nid, cruza in candidatos if not cruza]
    no_raio = [(d, nid) for d, nid in livres if d <= modelo["raio_ligacao_km"]]
    escolhidos = no_raio or livres[:2] or [(candidatos[0][0], candidatos[0][1])]
    return [(nid, _minutos_locais(d, rede["modelo"])) for d, nid in escolhidos]


def _tempo_rede(lat1: float, lng1: float, lat2: float, lng2: float) -> float | None:
    """Caminho mais curto no grafo, com acessos locais. None entre ilhas."""
    rede = carregar_rede()
    ilha1 = ilha_do_ponto(lat1, lng1, rede)
    ilha2 = ilha_do_ponto(lat2, lng2, rede)
    if ilha1 != ilha2:
        return None
    modelo = rede["modelo"]

    # Grafo temporário: ORIGEM e DESTINO ligados aos nós de acesso; a
    # ligação direta só é candidata em trajetos curtos (mesmo vale) —
    # em distâncias grandes o modelo local subestimaria as serras.
    arestas: dict[str, list[tuple[str, float]]] = {"@origem": [], "@destino": []}
    for nid, minutos in _ligacoes_de_acesso(lat1, lng1, rede, ilha1):
        arestas["@origem"].append((nid, minutos))
    for nid, minutos in _ligacoes_de_acesso(lat2, lng2, rede, ilha2):
        arestas.setdefault(nid, []).append(("@destino", minutos))

    d_direta = haversine_km(lat1, lng1, lat2, lng2)
    if d_direta <= modelo["alcance_direto_km"] and not _cruza_barreira(
        (lat1, lng1), (lat2, lng2), rede["barreiras"]
    ):
        arestas["@origem"].append(("@destino", _minutos_locais(d_direta, modelo)))

    def vizinhos(nid: str):
        yield from arestas.get(nid, [])
        yield from rede["vizinhos"].get(nid, [])

    # Dijkstra num grafo minúsculo (≈ 18 nós).
    melhores = {"@origem": 0.0}
    fila: list[tuple[float, str]] = [(0.0, "@origem")]
    while fila:
        custo, nid = heapq.heappop(fila)
        if nid == "@destino":
            return modelo["tempo_arranque_min"] + custo
        if custo > melhores.get(nid, float("inf")):
            continue
        for vizinho, minutos in vizinhos(nid):
            novo = custo + minutos
            if novo < melhores.get(vizinho, float("inf")):
                melhores[vizinho] = novo
                heapq.heappush(fila, (novo, vizinho))
    return None  # não deve acontecer (a validação garante conetividade)


# --------------------------------------------------------------- OSRM ---- #

def _osrm_base() -> str | None:
    return (os.environ.get(VARIAVEL_OSRM) or "").strip().rstrip("/") or None


def _pedir_osrm(url: str) -> dict:
    """Pedido HTTP ao OSRM (separado para os testes o simularem)."""
    resposta = requests.get(
        url,
        timeout=TEMPO_LIMITE_OSRM,
        headers={"User-Agent": "OndeIr-prototipo-academico (SESARAM; ver README)"},
    )
    resposta.raise_for_status()
    return resposta.json()


def _repor_estado_osrm() -> None:
    """Limpa cache e arrefecimento (usado pelos testes)."""
    global _osrm_falhou_em
    _cache_osrm.clear()
    _osrm_falhou_em = _NUNCA_FALHOU


def _tempos_osrm(lat: float, lng: float, destinos: list[tuple[float, float]]) -> list[float | None] | None:
    """Tempos (min) da origem a TODOS os destinos num só pedido /table.

    None (o todo) = OSRM desligado ou indisponível → quem chama recua
    para a rede calibrada. Coordenadas arredondadas a 4 casas (~11 m):
    chega para rotas e é o que fica em caches/registos.
    """
    global _osrm_falhou_em
    base = _osrm_base()
    if not base or not destinos:
        return None
    if time.monotonic() - _osrm_falhou_em < ARREFECIMENTO_OSRM_SEGUNDOS:
        return None

    chave = (round(lat, 4), round(lng, 4), tuple((round(a, 4), round(b, 4)) for a, b in destinos))
    guardado = _cache_osrm.get(chave)
    if guardado and time.monotonic() - guardado[0] <= TTL_OSRM_SEGUNDOS:
        return guardado[1]

    coordenadas = ";".join(
        f"{lng_:.4f},{lat_:.4f}" for lat_, lng_ in [(lat, lng), *destinos]
    )
    url = f"{base}/table/v1/driving/{coordenadas}?sources=0&annotations=duration"
    try:
        dados = _pedir_osrm(url)
        if dados.get("code") != "Ok":
            raise ValueError(f"OSRM devolveu code={dados.get('code')!r}")
        duracoes = dados["durations"][0][1:]
        if len(duracoes) != len(destinos):
            raise ValueError("OSRM devolveu um número inesperado de durações")
        minutos = [None if d is None else float(d) / 60.0 for d in duracoes]
    except Exception:  # noqa: BLE001 — qualquer falha: recuar em silêncio
        _osrm_falhou_em = time.monotonic()
        return None

    _cache_osrm[chave] = (time.monotonic(), minutos)
    if len(_cache_osrm) > 256:  # não crescer sem limite
        _cache_osrm.pop(next(iter(_cache_osrm)))
    return minutos


# ------------------------------------------------------------- público --- #

def _arredondar(minutos: float) -> int:
    return max(1, int(minutos + 0.5))


def estimar(lat1: float, lng1: float, lat2: float, lng2: float) -> dict | None:
    """Tempo de viagem estimado entre dois pontos.

    Devolve {"minutos": int, "metodo": "osrm"|"rede"} ou None entre
    ilhas diferentes (não há tempo de carro que atravesse o mar).
    """
    por_osrm = _tempos_osrm(lat1, lng1, [(lat2, lng2)])
    if por_osrm and por_osrm[0] is not None:
        return {"minutos": _arredondar(por_osrm[0]), "metodo": "osrm"}
    minutos = _tempo_rede(lat1, lng1, lat2, lng2)
    if minutos is None:
        return None
    return {"minutos": _arredondar(minutos), "metodo": "rede"}


def tempos_para_unidades(lat: float, lng: float, lista: list[dict]) -> dict[str, dict | None]:
    """{id_da_unidade: estimativa} para uma lista de unidades, de uma vez.

    Com OSRM ligado é UM pedido para todas; sem OSRM, a rede calibrada
    responde localmente. Unidades noutra ilha ficam a None.
    """
    saida: dict[str, dict | None] = {}
    por_osrm = _tempos_osrm(lat, lng, [(u["lat"], u["lng"]) for u in lista])
    for indice, unidade in enumerate(lista):
        minutos_osrm = por_osrm[indice] if por_osrm else None
        if minutos_osrm is not None:
            saida[unidade["id"]] = {"minutos": _arredondar(minutos_osrm), "metodo": "osrm"}
            continue
        minutos = _tempo_rede(lat, lng, unidade["lat"], unidade["lng"])
        saida[unidade["id"]] = (
            None if minutos is None else {"minutos": _arredondar(minutos), "metodo": "rede"}
        )
    return saida


NOTA_VIAGEM = (
    "Tempos de viagem de carro estimados com uma rede simplificada de "
    "estradas da RAM (valores típicos, sem trânsito) — por validar."
)
NOTA_VIAGEM_EN = (
    "Driving times estimated with a simplified RAM road network "
    "(typical values, no traffic) — pending validation."
)


def descrever(metodo: str | None) -> dict:
    """Bloco 'viagem_info' para a resposta do encaminhamento."""
    if metodo == "osrm":
        return {
            "disponivel": True,
            "metodo": "osrm",
            "descricao": "Tempos de viagem calculados por um servidor de rotas (OSRM) configurado pela instituição.",
            "descricao_en": "Driving times computed by an institution-configured routing server (OSRM).",
        }
    if metodo == "rede":
        return {
            "disponivel": True,
            "metodo": "rede",
            "descricao": NOTA_VIAGEM,
            "descricao_en": NOTA_VIAGEM_EN,
        }
    return {"disponivel": False, "metodo": None, "descricao": None, "descricao_en": None}
