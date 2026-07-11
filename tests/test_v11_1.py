"""Testes da v0.11.1: modo manual de localização por concelho → freguesia → sítio.

O que mudou (e o que estes testes prendem):
- app/data/localidades.json: árvore editável de concelhos, freguesias e
  sítios da RAM, com coordenadas verificadas pelo estagiário.
- app/core/localidades.py: carrega e VALIDA no arranque (ids únicos,
  pontos dentro da ilha certa, freguesia sempre com forma de a situar),
  calcula o centro de cada nível (coordenada própria ou centroide dos
  sítios), ordena tudo alfabeticamente sem os acentos contarem, e emite
  avisos brandos (sítio longe de mais, quase-duplicados, por confirmar).
- GET /api/localidades serve essa árvore ao ecrã "Onde está?".

Porquê isto importa: escolher só o CONCELHO é grosseiro. Quem está na
Camacha e escolhia "Santa Cruz" ficava com as coordenadas da vila, do
lado errado do concelho — e o encaminhamento mandava-o a ~19 min de
carro quando o seu centro de saúde está a ~8. Estes testes fixam esse
ganho com números reais do modelo de viagem.
"""

from __future__ import annotations

import copy
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core import espera, localidades, routing, viagem
from app.main import app

cliente = TestClient(app)

# Segunda-feira, 10:00 — dia útil normal, determinístico (igual ao test_v11).
SEGUNDA_10H = datetime(2026, 6, 29, 10, 0)


@pytest.fixture()
def sem_esperas(monkeypatch):
    """Encaminhamento sem tempos de espera: isola o efeito da localização
    (a regra de troca viagem+espera nunca dispara)."""
    monkeypatch.setattr(
        espera,
        "do_cache",
        lambda: {"disponivel": False, "desatualizado": False, "unidades": {}, "obtido_em": None},
    )


def _prep():
    return localidades.carregar(recarregar=True)


def _concelho(prep, cid):
    return next(c for c in prep["concelhos"] if c["id"] == cid)


def _freguesia(prep, cid, fid):
    return next(f for f in _concelho(prep, cid)["freguesias"] if f["id"] == fid)


def _sitio(prep, cid, fid, sid):
    return next(s for s in _freguesia(prep, cid, fid)["sitios"] if s["id"] == sid)


# --------------------------------------------------------------------- #
# Carregamento e forma dos dados                                          #
# --------------------------------------------------------------------- #

def test_carrega_e_conta_os_niveis():
    prep = _prep()
    concelhos = prep["concelhos"]
    n_freg = sum(len(c["freguesias"]) for c in concelhos)
    n_sitios = sum(len(f["sitios"]) for c in concelhos for f in c["freguesias"])
    assert len(concelhos) == 11
    assert n_freg == 53
    assert n_sitios == 145


def test_todos_os_niveis_tem_centro():
    prep = _prep()
    for c in prep["concelhos"]:
        assert set(c["centro"]) == {"lat", "lng"}
        for f in c["freguesias"]:
            assert set(f["centro"]) == {"lat", "lng"}


def test_nomes_de_concelho_batem_com_unidades():
    """Se um concelho tiver grafia diferente da das unidades, o cruzamento
    de dados no encaminhamento falha em silêncio — por isso prende-se aqui."""
    import json
    from app.core import unidades as mod_unidades

    prep = _prep()
    nomes_localidades = {c["nome"] for c in prep["concelhos"]}
    nomes_unidades = {u["concelho"] for u in mod_unidades.todas()}
    assert nomes_localidades == nomes_unidades


# --------------------------------------------------------------------- #
# Ordenação e centros                                                     #
# --------------------------------------------------------------------- #

def test_freguesias_ordenadas_sem_acentos():
    """'Água de Pena' tem de ficar no princípio (A), não no fim — a
    ordenação ignora acentos. Machico é o caso canónico."""
    prep = _prep()
    nomes = [f["nome"] for f in _concelho(prep, "machico")["freguesias"]]
    assert nomes == ["Água de Pena", "Caniçal", "Machico", "Porto da Cruz", "Santo António da Serra"]


def test_concelhos_ordenados_alfabeticamente():
    prep = _prep()
    nomes = [c["nome"] for c in prep["concelhos"]]
    assert nomes == sorted(nomes, key=lambda n: n.replace("â", "a").replace("ã", "a").casefold())
    assert nomes[0] == "Calheta"  # antes de "Câmara de Lobos"


def test_centro_de_freguesia_com_coordenada_propria():
    """Água de Pena não tem sítios: o centro é a sua própria coordenada."""
    prep = _prep()
    f = _freguesia(prep, "machico", "agua_de_pena")
    assert f["sitios"] == []
    assert f["centro"] == {"lat": 32.70857, "lng": -16.773848}


def test_centro_de_freguesia_e_centroide_dos_sitios():
    """Caniço não tem coordenada própria: o centro é a média dos sítios."""
    prep = _prep()
    f = _freguesia(prep, "santa_cruz", "canico")
    lat = sum(s["lat"] for s in f["sitios"]) / len(f["sitios"])
    lng = sum(s["lng"] for s in f["sitios"]) / len(f["sitios"])
    assert f["centro"] == {"lat": round(lat, 6), "lng": round(lng, 6)}


def test_pontos_dentro_dos_limites_da_ilha():
    prep = _prep()
    for c in prep["concelhos"]:
        lat_min, lat_max, lng_min, lng_max = localidades._LIMITES[c["ilha"]]
        pontos = [c["centro"]]
        for f in c["freguesias"]:
            pontos.append(f["centro"])
            pontos.extend({"lat": s["lat"], "lng": s["lng"]} for s in f["sitios"])
        for p in pontos:
            assert lat_min <= p["lat"] <= lat_max
            assert lng_min <= p["lng"] <= lng_max


# --------------------------------------------------------------------- #
# Validação: erros sintéticos rebentam                                    #
# --------------------------------------------------------------------- #

def _base_valida() -> dict:
    """Um documento mínimo mas válido, para lhe injetar defeitos."""
    return {
        "concelhos": [
            {
                "id": "funchal", "nome": "Funchal", "ilha": "madeira",
                "lat": 32.6496, "lng": -16.9086,
                "freguesias": [
                    {"id": "se", "nome": "Sé", "sitios": [
                        {"id": "mar", "nome": "Avenida do Mar", "lat": 32.6463, "lng": -16.9115},
                    ]},
                ],
            },
        ],
    }


def test_valida_documento_bom():
    assert localidades.validar(_base_valida()) == []


def test_erro_freguesia_sem_coords_nem_sitios():
    d = _base_valida()
    d["concelhos"][0]["freguesias"][0]["sitios"] = []
    problemas = localidades.validar(d)
    assert any("não há como situar" in p for p in problemas)


def test_erro_id_de_sitio_repetido():
    d = _base_valida()
    sitios = d["concelhos"][0]["freguesias"][0]["sitios"]
    sitios.append({"id": "mar", "nome": "Outro", "lat": 32.646, "lng": -16.911})
    assert any("id repetido" in p for p in localidades.validar(d))


def test_erro_coordenada_fora_da_ilha():
    d = _base_valida()
    d["concelhos"][0]["freguesias"][0]["sitios"][0]["lat"] = 33.05  # Porto Santo
    assert any("fora dos limites" in p or "noutra ilha" in p for p in localidades.validar(d))


def test_erro_ilha_desconhecida():
    d = _base_valida()
    d["concelhos"][0]["ilha"] = "lua"
    assert any("ilha desconhecida" in p for p in localidades.validar(d))


# --------------------------------------------------------------------- #
# Avisos brandos                                                          #
# --------------------------------------------------------------------- #

def test_aviso_sitio_longe_do_centro():
    """Um sítio a >12 km do centro do concelho é quase de certeza um
    engano de transcrição — foi assim que se apanhou o 'Outeiro'."""
    prep = copy.deepcopy(_prep())
    f = _freguesia(prep, "santa_cruz", "camacha")
    f["sitios"][0]["lat"] = 32.698331   # coordenadas que caíam nos Canhas
    f["sitios"][0]["lng"] = -17.117938
    avisos = localidades.avisos(prep)
    assert any("Camacha" in a and "km do centro" in a for a in avisos)


def test_avisos_listam_freguesias_por_confirmar():
    """As 3 freguesias acrescentadas pelo protótipo (verificado=false)
    têm de aparecer nos avisos, para o orientador as validar."""
    avisos = localidades.avisos(_prep())
    for nome in ("Santa Luzia", "Caniçal", "Prazeres"):
        assert any(nome in a and "confirmar" in a for a in avisos)


def test_outeiro_ficou_de_fora_da_camacha():
    """Guarda de regressão documental: enquanto as coordenadas do Outeiro
    não forem corrigidas, não deve reaparecer na Camacha."""
    prep = _prep()
    nomes = [s["nome"] for s in _freguesia(prep, "santa_cruz", "camacha")["sitios"]]
    assert "Outeiro" not in nomes


# --------------------------------------------------------------------- #
# API                                                                     #
# --------------------------------------------------------------------- #

def test_endpoint_localidades_ok():
    resposta = cliente.get("/api/localidades")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo["concelhos"]) == 11
    primeiro = corpo["concelhos"][0]
    assert {"id", "nome", "ilha", "centro", "freguesias"} <= set(primeiro)
    assert "lat" in primeiro["centro"]


def test_endpoint_localidades_vem_ordenado():
    corpo = cliente.get("/api/localidades").json()
    nomes = [c["nome"] for c in corpo["concelhos"]]
    assert nomes[0] == "Calheta"
    freg = next(c for c in corpo["concelhos"] if c["id"] == "machico")["freguesias"]
    assert [f["nome"] for f in freg][0] == "Água de Pena"


# --------------------------------------------------------------------- #
# Integração: o ganho concreto do modo mais fino                          #
# --------------------------------------------------------------------- #

def test_camacha_encaminha_melhor_que_a_vila(sem_esperas):
    """Na Camacha (freguesia) o encaminhamento manda ao CS da Camacha;
    escolher só o concelho (vila de Santa Cruz) mandaria ao CS de Santa
    Cruz. É este o ganho da v0.11.1."""
    prep = _prep()
    camacha = _freguesia(prep, "santa_cruz", "camacha")["centro"]
    vila = _concelho(prep, "santa_cruz")["centro"]

    r_camacha = routing.decidir_encaminhamento(
        "verde", camacha["lat"], camacha["lng"], quando=SEGUNDA_10H
    )
    r_vila = routing.decidir_encaminhamento(
        "verde", vila["lat"], vila["lng"], quando=SEGUNDA_10H
    )
    assert r_camacha["unidade"]["id"] == "cs_camacha"
    assert r_vila["unidade"]["id"] == "cs_santa_cruz"


def test_viagem_camacha_vs_vila_em_minutos():
    """O número que motiva a funcionalidade: da Camacha, o CS da Camacha
    está muito mais perto (em tempo) do que o CS de Santa Cruz."""
    prep = _prep()
    camacha = _freguesia(prep, "santa_cruz", "camacha")["centro"]
    ate_camacha = viagem.estimar(camacha["lat"], camacha["lng"], 32.679459439871096, -16.844161004091234)
    ate_santa_cruz = viagem.estimar(camacha["lat"], camacha["lng"], 32.68960137504053, -16.794276586899944)
    assert ate_camacha["minutos"] < ate_santa_cruz["minutos"]
    assert ate_camacha["minutos"] <= 10
    assert ate_santa_cruz["minutos"] >= 15


def test_sitio_do_curral_usa_a_rede(sem_esperas):
    """De um sítio no fundo do Curral das Freiras, o encaminhamento
    responde por estrada (método 'rede') — o Curral é o caso em que a
    linha reta mais engana."""
    prep = _prep()
    faja = _sitio(prep, "camara_de_lobos", "curral_das_freiras", "faja_dos_cardos")
    estimativa = viagem.estimar(faja["lat"], faja["lng"], 32.648496710138915, -16.92441301943404)
    assert estimativa is not None
    assert estimativa["metodo"] == "rede"
