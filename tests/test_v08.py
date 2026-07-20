"""Testes das novidades da v0.8: tempos de espera do SESARAM.

Sem tocar na rede: as descargas são simuladas por monkeypatch de
espera._obter_html com HTML de fixture que imita os dois formatos reais
do SEISRAM (centros de saúde e hospital), e o ficheiro de cache é
redirecionado para tmp_path. A regra de troca e a integração no
encaminhamento são testadas com um cache injetado.

Data de referência: 2026-07-04 é um sábado.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.core import espera, routing
from app.main import app

cliente = TestClient(app)

SABADO_15H = datetime(2026, 7, 4, 15, 0)

# Câmara de Lobos (perto do hospital) e Machico (longe), para o cenário.
PERTO_CAMARA_LOBOS = (32.6514, -16.9799)
EM_MACHICO = (32.7249, -16.7715)

# --- fixtures HTML: imitam a estrutura das páginas do SEISRAM ---------

FIX_CENTROS = """
<html><body>
<p>Última Atualização: 2026-07-06 00:10</p>
<table>
  <tr><th>Unidade</th><th>Nº Utentes em espera</th><th>Tempo médio / Nº Atendidos</th></tr>
  <tr><td>BOM JESUS</td><td>0</td><td></td></tr>
  <tr><td>CÂMARA DE LOBOS</td><td>4</td><td>1h05 / 3</td></tr>
  <tr><td>MACHICO</td><td>2</td><td>9m / 1</td></tr>
  <tr><td>UNIDADE FANTASMA</td><td>3</td><td>15m / 2</td></tr>
</table>
</body></html>
"""

FIX_HOSPITAL = """
<html><body>
<p>Última Atualização: 2026-07-06 14:34</p>
<table>
  <tr><th>Área</th><th>Emergente</th><th>Muito Urgente</th><th>Urgente</th><th>Pouco Urgente</th><th>Não Urgente</th></tr>
  <tr><td>Área Médica</td><td>0</td><td>2</td><td>11</td><td>4</td><td>0</td></tr>
</table>
<table>
  <tr><th>Área</th><th>Emergente</th><th>Muito Urgente</th><th>Urgente</th><th>Pouco Urgente</th><th>Não Urgente</th></tr>
  <tr><td>Área Médica</td><td></td><td>16m / 8</td><td>27m / 28</td><td>54m / 12</td><td></td></tr>
</table>
</body></html>
"""


def _fake_html(centros=FIX_CENTROS, hospital=FIX_HOSPITAL):
    def _obter(url):
        return centros if "CSP" in url else hospital
    return _obter


@pytest.fixture
def cache_tmp(tmp_path, monkeypatch):
    """Redireciona o ficheiro de cache para uma pasta temporária."""
    monkeypatch.setattr(espera, "_FICHEIRO_CACHE", tmp_path / "cache.json")


# --- parsers ----------------------------------------------------------

def test_interpretar_tempo_formatos():
    assert espera.interpretar_tempo("8m") == 8
    assert espera.interpretar_tempo("2h37") == 157
    assert espera.interpretar_tempo("1h") == 60
    assert espera.interpretar_tempo("1:05") == 65
    assert espera.interpretar_tempo("") is None
    assert espera.interpretar_tempo("sem dados") is None


def test_interpretar_tempo_e_atendidos():
    assert espera.interpretar_tempo_e_atendidos("26m / 16") == (26, 16)
    assert espera.interpretar_tempo_e_atendidos("2h37 / 7") == (157, 7)
    assert espera.interpretar_tempo_e_atendidos("") == (None, None)


def test_extrair_centros_le_linhas():
    centros = espera.extrair_centros(FIX_CENTROS)
    cl = centros[espera.normalizar("CÂMARA DE LOBOS")]
    assert cl["em_espera"] == 4
    assert cl["tempo_medio_min"] == 65
    assert centros[espera.normalizar("MACHICO")]["tempo_medio_min"] == 9


def test_extrair_hospital_por_cor_ponderado():
    hosp = espera.extrair_hospital(FIX_HOSPITAL)
    por_cor = hosp["por_cor"]
    assert por_cor["laranja"]["em_espera"] == 2
    assert por_cor["laranja"]["tempo_medio_min"] == 16
    assert por_cor["amarelo"]["em_espera"] == 11
    assert por_cor["amarelo"]["tempo_medio_min"] == 27
    assert por_cor["amarelo"]["atendidos"] == 28
    # Geral agrega as contagens das cinco cores.
    assert hosp["geral"]["em_espera"] == 17


def test_extrair_ultima_atualizacao():
    assert espera.extrair_ultima_atualizacao(FIX_HOSPITAL) == "2026-07-06 14:34"


# --- descarga, mapeamento e cache ------------------------------------

def test_obter_mapeia_e_grava(cache_tmp, monkeypatch):
    monkeypatch.setattr(espera, "_obter_html", _fake_html())
    dados = espera.obter(force=True)
    assert dados["disponivel"] is True
    unidades = dados["unidades"]
    # 3 centros mapeados + hospital = 4; a "UNIDADE FANTASMA" fica por mapear.
    assert set(unidades) >= {"cs_camara_lobos", "cs_machico", "hnm"}
    assert dados["por_mapear"] == ["UNIDADE FANTASMA"]
    assert unidades["hnm"]["tipo_dados"] == "por_cor"


def test_cache_fresco_nao_vai_a_rede(cache_tmp, monkeypatch):
    monkeypatch.setattr(espera, "_obter_html", _fake_html())
    espera.obter(force=True)

    def _explode(url):
        raise AssertionError("não devia ir à rede com cache fresco")

    monkeypatch.setattr(espera, "_obter_html", _explode)
    dados = espera.obter(force=False)  # dentro do TTL
    assert dados["disponivel"] is True


def test_falha_herda_cache_valido(cache_tmp, monkeypatch):
    monkeypatch.setattr(espera, "_obter_html", _fake_html())
    espera.obter(force=True)

    def _falha(url):
        raise RuntimeError("site em baixo")

    monkeypatch.setattr(espera, "_obter_html", _falha)
    dados = espera.obter(force=True)  # força, mas a rede falha
    assert dados["disponivel"] is True          # herdou o cache
    assert dados["desatualizado"] is True


def test_do_cache_nunca_vai_a_rede(cache_tmp, monkeypatch):
    monkeypatch.setattr(espera, "_obter_html", _fake_html())
    espera.obter(force=True)

    def _explode(url):
        raise AssertionError("do_cache não pode ir à rede")

    monkeypatch.setattr(espera, "_obter_html", _explode)
    dados = espera.do_cache()
    assert dados["disponivel"] is True


# --- regra de troca (isolada) ----------------------------------------

def _unidade(uid, dist, minutos=None):
    resumo = {"id": uid, "nome": uid, "distancia_km": dist, "aberta_agora": True}
    if minutos is not None:
        resumo["tempo_espera"] = {"minutos": minutos}
    return resumo


def test_troca_quando_vale_a_pena():
    # Perto: 2 km mas 120 min de espera. Longe: 7 km e 8 min.
    perto = _unidade("perto", 2, 120)
    longe = _unidade("longe", 7, 8)
    principal, restantes, troca = espera.escolher_principal([perto, longe])
    assert principal is longe
    assert troca is not None
    assert restantes[0] is perto


def test_nao_troca_por_poupanca_pequena():
    perto = _unidade("perto", 2, 30)
    longe = _unidade("longe", 7, 20)  # poupança < 30 min
    principal, _, troca = espera.escolher_principal([perto, longe])
    assert principal is perto
    assert troca is None


def test_nao_troca_com_desvio_grande():
    perto = _unidade("perto", 2, 200)
    longe = _unidade("longe", 40, 5)  # desvio > 15 km
    principal, _, troca = espera.escolher_principal([perto, longe])
    assert principal is perto
    assert troca is None


def test_sem_dados_nunca_troca():
    perto = _unidade("perto", 2)   # sem tempo_espera
    longe = _unidade("longe", 7)
    principal, _, troca = espera.escolher_principal([perto, longe])
    assert principal is perto
    assert troca is None


# --- integração no encaminhamento ------------------------------------

MOCK_CACHE = {
    "disponivel": True,
    "desatualizado": False,
    "obtido_em": "2026-07-04T15:00:00",
    "unidades": {
        "cs_camara_lobos": {
            "tipo_dados": "geral",
            "em_espera": 9,
            "tempo_medio_min": 120,
            "atendidos": 6,
            "fonte": "centros_saude",
            "atualizado_no_site": "2026-07-04 15:00",
        },
        "hnm": {
            "tipo_dados": "por_cor",
            "por_cor": {"laranja": {"em_espera": 1, "tempo_medio_min": 8, "atendidos": 4}},
            "geral": {"em_espera": 12, "tempo_medio_min": 40, "atendidos": 30},
            "fonte": "hospital",
            "atualizado_no_site": "2026-07-04 15:00",
        },
        "cs_machico": {
            "tipo_dados": "geral",
            "em_espera": 2,
            "tempo_medio_min": 9,
            "atendidos": 3,
            "fonte": "centros_saude",
            "atualizado_no_site": "2026-07-04 15:00",
        },
    },
}


@pytest.fixture
def mock_esperas(monkeypatch):
    monkeypatch.setattr(espera, "do_cache", lambda: MOCK_CACHE)


def test_laranja_vai_ao_hospital_com_espera_da_cor(mock_esperas):
    """Na v0.8 este cenário testava a regra de troca por espera; desde a
    v0.12.1 o laranja vai DIRETO ao hospital por política, sem troca. O
    que se mantém: o hospital mostra a espera DA COR do utente."""
    saida = routing.decidir_encaminhamento("laranja", *PERTO_CAMARA_LOBOS, quando=SABADO_15H)
    assert saida["unidade"]["id"] == "hnm"
    assert saida["reordenado_por_espera"] is False
    assert saida["politica"] == {
        "destino": "hospital", "fonte": "configuracao", "aplicada": True
    }
    # O hospital mostra a espera DA COR (laranja = 8 min).
    te = saida["unidade"]["tempo_espera"]
    assert te["minutos"] == 8 and te["ambito"] == "cor"


def test_verde_mostra_espera_sem_reordenar(mock_esperas):
    saida = routing.decidir_encaminhamento("verde", *EM_MACHICO, quando=SABADO_15H)
    assert saida["unidade"]["id"] == "cs_machico"
    assert saida["unidade"]["tempo_espera"]["minutos"] == 9
    assert saida.get("reordenado_por_espera", False) is False


def test_vermelho_ignora_reordenacao(mock_esperas):
    # Vermelho manda ligar 112; a referência mostrada é o hospital
    # (v0.12.1), nunca reordenada por espera.
    saida = routing.decidir_encaminhamento("vermelho", *PERTO_CAMARA_LOBOS, quando=SABADO_15H)
    assert saida["acao"] == "ligar_112"
    assert saida["unidade"]["id"] == "hnm"


def test_espera_info_na_resposta(mock_esperas):
    saida = routing.decidir_encaminhamento("verde", *EM_MACHICO, quando=SABADO_15H)
    assert saida["espera_info"]["disponivel"] is True


def test_endpoint_espera_responde():
    resposta = cliente.get("/api/espera")
    assert resposta.status_code == 200
    assert "disponivel" in resposta.json()
