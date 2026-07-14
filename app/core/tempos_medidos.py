"""Tempos de viagem MEDIDOS à mão (v0.11.3) — módulo amovível.

O problema que isto remenda
---------------------------
A rede calibrada (app/core/viagem.py) descreve a ilha com ~16 pontos e
os troços principais. Funciona bem entre concelhos, mas nos acessos
locais depende de um modelo grosseiro (linha reta × fator), e esse
modelo pode inverter dois destinos vizinhos — o caso real que motivou
esta versão: da Achada da Rocha (Camacha), o modelo dava a Camacha à
frente de Gaula, quando por estrada Gaula é mais rápido.

A solução (paliativo assumido)
------------------------------
Uma tabela EDITÁVEL de tempos por estrada, por zona:
app/data/tempos_medidos.json tem uma entrada por cada sítio e por cada
freguesia de localidades.json, com os destinos relevantes (o Hospital
Dr. Nélio Mendonça e os centros de saúde mais próximos). Os valores
começam todos a null e enchem-se por dois caminhos que podem coexistir
(cada par pode registar a sua "fonte"):
  - automático (recomendado): scripts/calcular_tempos_medidos.py pede
    as rotas a um motor (OpenRouteService ou OSRM) e preenche tudo;
  - manual: medir no Google Maps e escrever tempo_min e distancia_km
    (scripts/tempos_medidos_relatorio.py --links dá os links prontos),
    útil para conferir ou corrigir pares suspeitos.
O que estiver preenchido passa a mandar; o resto continua a usar a
rede calibrada. O relatório mostra o progresso e as divergências.

Como se usa uma medição
-----------------------
1. Âncora: o ponto registado (sítio/freguesia) mais próximo da posição
   do utente, na mesma ilha, dentro de um raio curto (parametros.
   raio_ancoragem_km) e sem atravessar as barreiras de relevo da rede
   (a crista do Curral não se salta em linha reta).
2. Se essa âncora tiver medição para a unidade pedida, o tempo é o
   medido MAIS um pequeno ajuste pelo desvio entre o utente e a âncora
   (modelo local da rede, sem tempo de arranque). Se a âncora mais
   próxima não tiver a medição, tenta-se a seguinte dentro do raio.
3. Sem âncora no raio, ou sem medição preenchida: devolve-se None e o
   viagem.py recua para a rede calibrada, como até aqui.

Porque é AMOVÍVEL (e como se remove)
------------------------------------
Isto é um remendo de protótipo: preciso enquanto não há um serviço de
rotas, dispensável no dia em que houver (OSRM interno ou uma API paga,
p. ex. Google Routes — ver README e docs/INTEGRACAO.md). Por isso:
- o viagem.py importa este módulo de forma preguiçosa e tolerante:
  APAGAR app/core/tempos_medidos.py não parte nada;
- APAGAR app/data/tempos_medidos.json desativa a funcionalidade em
  silêncio (ficheiro ausente = desligado; ficheiro presente mas
  inválido = erro claro no arranque, como nos fluxogramas);
- definir a variável de ambiente VIAGEM_TEMPOS_MEDIDOS=0 desliga sem
  apagar nada;
- com o OSRM ligado (VIAGEM_OSRM_URL), o OSRM tem prioridade e esta
  tabela só serve de recuo — o ciclo de vida previsto: o serviço de
  rotas substitui o remendo sem ser preciso mexer em código.

Privacidade: tudo local; nenhuma coordenada sai do servidor.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .geo import haversine_km

_PASTA_DATA = Path(__file__).resolve().parents[1] / "data"
FICHEIRO = _PASTA_DATA / "tempos_medidos.json"

VARIAVEL_DESLIGAR = "VIAGEM_TEMPOS_MEDIDOS"

# Limites de sanidade para valores preenchidos à mão (a RAM atravessa-se
# em ~1h15; nada de tempos de 4 horas por gralha).
_TEMPO_MAX_MIN = 180.0
_DISTANCIA_MAX_KM = 120.0

ILHAS_CONHECIDAS = {"madeira", "porto_santo"}


class ErroTemposMedidos(ValueError):
    """tempos_medidos.json inválido (apanhado no arranque, como nos fluxogramas)."""


_cache: dict | None = None


def _desligado_por_ambiente() -> bool:
    valor = (os.environ.get(VARIAVEL_DESLIGAR) or "").strip().lower()
    return valor in {"0", "nao", "não", "off", "false"}


def carregar(recarregar: bool = False) -> dict:
    """Carrega e VALIDA a tabela uma única vez.

    Ficheiro AUSENTE não é erro: devolve uma tabela inativa (o módulo é
    amovível por definição). Ficheiro presente mas inválido rebenta no
    arranque com mensagem clara.
    """
    global _cache
    if _cache is None or recarregar:
        if not FICHEIRO.exists():
            _cache = {"ativo": False, "ancoras": [], "por_ilha": {}, "parametros": {}}
        else:
            dados = json.loads(FICHEIRO.read_text(encoding="utf-8"))
            problemas = validar(dados)
            if problemas:
                raise ErroTemposMedidos(
                    "tempos_medidos.json inválido:\n- " + "\n- ".join(problemas)
                )
            _cache = _preparar(dados)
    return _cache


# ------------------------------------------------------------ validação -- #

def _numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def validar(dados: dict) -> list[str]:
    """Lista de problemas (vazia = ok). Usada aqui e por validar_dados.py."""
    # Import local para evitar custos no arranque de quem só valida.
    from . import unidades as _unidades

    problemas: list[str] = []
    medicoes = dados.get("medicoes")
    if not isinstance(medicoes, list) or not medicoes:
        return ["'medicoes' em falta ou vazio"]

    parametros = dados.get("parametros") or {}
    raio = parametros.get("raio_ancoragem_km")
    if not _numero(raio) or raio <= 0 or raio > 15:
        problemas.append(f"parametros.raio_ancoragem_km inválido ({raio!r})")

    unidades_por_id = {u["id"]: u for u in _unidades.todas()}
    ids_vistos: set[str] = set()

    for m in medicoes:
        mid = m.get("origem") or "(sem origem)"
        onde = f"medição '{mid}'"
        if not m.get("origem"):
            problemas.append(f"{onde}: falta 'origem'")
            continue
        if mid in ids_vistos:
            problemas.append(f"{onde}: origem repetida")
        ids_vistos.add(mid)

        ilha = m.get("ilha")
        if ilha not in ILHAS_CONHECIDAS:
            problemas.append(f"{onde}: ilha desconhecida ({ilha!r})")
        if not (_numero(m.get("lat")) and _numero(m.get("lng"))):
            problemas.append(f"{onde}: 'lat'/'lng' em falta ou não numéricos")

        destinos = m.get("destinos")
        if not isinstance(destinos, dict) or not destinos:
            problemas.append(f"{onde}: 'destinos' em falta ou vazio")
            continue
        for uid, valores in destinos.items():
            unidade = unidades_por_id.get(uid)
            if unidade is None:
                problemas.append(f"{onde}: destino '{uid}' não existe em unidades.json")
                continue
            if ilha in ILHAS_CONHECIDAS and unidade.get("ilha", "madeira") != ilha:
                problemas.append(
                    f"{onde}: destino '{uid}' fica noutra ilha (uma medição "
                    "de carro não atravessa o mar)"
                )
            if not isinstance(valores, dict):
                problemas.append(f"{onde}: destino '{uid}' deve ser um objeto")
                continue
            tempo = valores.get("tempo_min")
            dist = valores.get("distancia_km")
            if tempo is not None and (
                not _numero(tempo) or tempo <= 0 or tempo > _TEMPO_MAX_MIN
            ):
                problemas.append(f"{onde}: '{uid}'.tempo_min inválido ({tempo!r})")
            if dist is not None and (
                not _numero(dist) or dist <= 0 or dist > _DISTANCIA_MAX_KM
            ):
                problemas.append(f"{onde}: '{uid}'.distancia_km inválido ({dist!r})")
            for campo in ("fonte", "calculado_em"):
                extra = valores.get(campo)
                if extra is not None and not isinstance(extra, str):
                    problemas.append(
                        f"{onde}: '{uid}'.{campo} deve ser texto ({extra!r})"
                    )

    return problemas


def avisos(dados: dict | None = None) -> list[str]:
    """Suspeitas que não impedem nada mas merecem olhos humanos."""
    if dados is None:
        if not FICHEIRO.exists():
            return []
        dados = json.loads(FICHEIRO.read_text(encoding="utf-8"))
    saida: list[str] = []
    total = preenchidos = 0
    for m in dados.get("medicoes", []):
        for uid, valores in (m.get("destinos") or {}).items():
            if not isinstance(valores, dict):
                continue
            total += 1
            if valores.get("tempo_min") is not None:
                preenchidos += 1
            elif valores.get("distancia_km") is not None:
                saida.append(
                    f"medição '{m.get('origem')}' / '{uid}': tem distancia_km "
                    "mas não tempo_min (sem tempo, a medição não é usada)"
                )
    if total:
        saida.append(
            f"tempos medidos: {preenchidos} de {total} pares preenchidos "
            "(os restantes usam a rede calibrada; ver "
            "scripts/tempos_medidos_relatorio.py)"
        )
    return saida


# ------------------------------------------------------------ preparação -- #

def _preparar(dados: dict) -> dict:
    ancoras = []
    for m in dados["medicoes"]:
        preenchidos = {
            uid: v
            for uid, v in m["destinos"].items()
            if isinstance(v, dict) and v.get("tempo_min") is not None
        }
        ancoras.append(
            {
                "origem": m["origem"],
                "nome": m.get("nome") or m["origem"],
                "lat": m["lat"],
                "lng": m["lng"],
                "ilha": m["ilha"],
                "medidos": preenchidos,
            }
        )
    por_ilha: dict[str, list[dict]] = {}
    for a in ancoras:
        por_ilha.setdefault(a["ilha"], []).append(a)
    tem_medicoes = any(a["medidos"] for a in ancoras)
    return {
        "ativo": tem_medicoes,
        "ancoras": ancoras,
        "por_ilha": por_ilha,
        "parametros": dados.get("parametros") or {},
        "versao": dados.get("versao"),
    }


# --------------------------------------------------------------- procura -- #

def procurar(lat: float, lng: float, unidade_id: str) -> dict | None:
    """Tempo MEDIDO da zona do utente até uma unidade, se existir.

    Devolve {"minutos": float, "distancia_km": float|None, "ancora": nome,
    "desvio_km": float} ou None (sem âncora no raio, sem medição para a
    unidade, módulo desligado). O arredondamento final é do viagem.py.
    """
    if _desligado_por_ambiente():
        return None
    tabela = carregar()
    if not tabela["ativo"]:
        return None

    # As barreiras e o modelo local vêm da rede calibrada: a mesma noção
    # de relevo e de acesso curto em toda a aplicação.
    from . import viagem as _viagem

    rede = _viagem.carregar_rede()
    ilha = _viagem.ilha_do_ponto(lat, lng, rede)
    candidatas = tabela["por_ilha"].get(ilha) or []
    if not candidatas:
        return None

    raio = float(tabela["parametros"].get("raio_ancoragem_km", 3.0))
    proximas = sorted(
        (
            (haversine_km(lat, lng, a["lat"], a["lng"]), a)
            for a in candidatas
        ),
        key=lambda par: par[0],
    )
    for d_km, ancora in proximas:
        if d_km > raio:
            break  # ordenado: daqui para a frente é tudo mais longe
        if not ancora["medidos"]:
            continue
        medido = ancora["medidos"].get(unidade_id)
        if medido is None:
            continue
        if _viagem._cruza_barreira(
            (lat, lng), (ancora["lat"], ancora["lng"]), rede["barreiras"]
        ):
            continue
        minutos = float(medido["tempo_min"])
        distancia = medido.get("distancia_km")
        # Ajuste pelo desvio utente ↔ âncora: o modelo local da rede,
        # sem o tempo de arranque (o tempo medido já é a viagem toda).
        if d_km > 0.05:
            minutos += _viagem._minutos_locais(d_km, rede["modelo"])
            if distancia is not None:
                fator = _viagem._escalao(d_km, rede["modelo"]["fator_desvio"])
                distancia = float(distancia) + d_km * fator
        return {
            "minutos": minutos,
            "distancia_km": None if distancia is None else round(float(distancia), 1),
            "ancora": ancora["nome"],
            "origem": ancora["origem"],
            "desvio_km": round(d_km, 2),
        }
    return None
