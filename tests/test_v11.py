"""Testes das alterações da v0.11: tempos de viagem por estrada.

O que mudou (e o que estes testes prendem):
- app/core/viagem.py: rede calibrada de estradas da RAM (grafo editável
  em app/data/rede_viagem.json) + modelo local de acessos + barreiras de
  relevo + OSRM opcional (desligado por omissão) com recuo automático.
- O encaminhamento ordena as candidatas por TEMPO de viagem (era por
  linha reta) e as mensagens passam a incluir "~X min de carro".
- A regra de troca (viagem + espera) soma agora a espera real do SEISRAM
  a uma viagem por estrada, não a um palpite em linha reta.

Casos geográficos escolhidos de propósito: o Curral das Freiras é o
exemplo em que a linha reta engana MESMO — a unidade "mais perto" no
mapa (Câmara de Lobos) fica do outro lado da serra, e o caminho real
para lá passa pelo Funchal, à porta do hospital.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core import espera, routing, viagem

# Segunda-feira, 10:00 (dia útil normal — determinístico).
SEGUNDA_10H = datetime(2026, 6, 29, 10, 0)

FUNCHAL = (32.6496, -16.9086)
CURRAL = (32.7206, -16.9663)
MACHICO = (32.7249, -16.7715)
SANTANA = (32.8060, -16.8850)
PORTO_SANTO = (33.0598, -16.3325)

HNM = (32.648496710138915, -16.92441301943404)
CS_CAMARA_LOBOS = (32.6514, -16.9799)


@pytest.fixture()
def sem_esperas(monkeypatch):
    """Encaminhamento sem tempos de espera: isola o efeito da viagem
    (a regra de troca nunca dispara) e torna os testes independentes do
    cache que outros testes escrevem."""
    monkeypatch.setattr(
        espera,
        "do_cache",
        lambda: {"disponivel": False, "desatualizado": False, "unidades": {}, "obtido_em": None},
    )


# --------------------------------------------------------------------- #
# Rede: carregamento e validação                                          #
# --------------------------------------------------------------------- #

def test_rede_carrega_e_e_valida():
    rede = viagem.carregar_rede(recarregar=True)
    assert len(rede["por_id"]) >= 12
    assert "funchal" in rede["por_id"]
    assert "porto_santo" in rede["por_id"]


def _rede_minima() -> dict:
    return {
        "nos": [
            {"id": "a", "nome": "A", "lat": 32.65, "lng": -16.91, "ilha": "madeira"},
            {"id": "b", "nome": "B", "lat": 32.72, "lng": -16.77, "ilha": "madeira"},
        ],
        "ligacoes": [{"entre": ["a", "b"], "minutos": 10}],
        "barreiras": [],
        "modelo_local": {
            "tempo_arranque_min": 3,
            "raio_ligacao_km": 9.0,
            "alcance_direto_km": 7.0,
            "fator_desvio": [[5.0, 1.5], [9999, 1.7]],
            "velocidade_kmh": [[2.0, 24], [5.0, 34], [9999, 40]],
        },
    }


def test_validacao_apanha_no_inexistente():
    dados = _rede_minima()
    dados["ligacoes"][0]["entre"] = ["a", "zzz"]
    assert any("inexistente" in p for p in viagem.validar_rede(dados))


def test_validacao_apanha_ligacao_entre_ilhas():
    dados = _rede_minima()
    dados["nos"][1]["ilha"] = "porto_santo"
    dados["nos"][1]["lat"], dados["nos"][1]["lng"] = 33.06, -16.33
    assert any("atravessa o mar" in p for p in viagem.validar_rede(dados))


def test_validacao_apanha_minutos_invalidos():
    dados = _rede_minima()
    dados["ligacoes"][0]["minutos"] = -5
    assert any("minutos inválidos" in p for p in viagem.validar_rede(dados))


def test_validacao_apanha_no_solto():
    dados = _rede_minima()
    dados["nos"].append({"id": "c", "nome": "C", "lat": 32.80, "lng": -17.10, "ilha": "madeira"})
    assert any("sem ligação" in p for p in viagem.validar_rede(dados))


# --------------------------------------------------------------------- #
# Estimador: propriedades e geografia da Madeira                          #
# --------------------------------------------------------------------- #

def test_mesmo_ponto_da_tempo_pequeno():
    est = viagem.estimar(*FUNCHAL, *FUNCHAL)
    assert est["metodo"] == "rede"
    assert 1 <= est["minutos"] <= 6  # essencialmente o tempo de arranque


def test_estimar_e_simetrico():
    ida = viagem.estimar(*CURRAL, *HNM)["minutos"]
    volta = viagem.estimar(*HNM, *CURRAL)["minutos"]
    assert abs(ida - volta) <= 1  # arredondamentos


def test_ilhas_diferentes_dao_none():
    assert viagem.estimar(*FUNCHAL, *PORTO_SANTO) is None


def test_santana_fica_mais_longe_que_machico_em_tempo():
    """Em linha reta são parecidos (~15-17 km); por estrada, Santana
    obriga a contornar a serra e demora bem mais."""
    para_machico = viagem.estimar(*FUNCHAL, *MACHICO)["minutos"]
    para_santana = viagem.estimar(*FUNCHAL, *SANTANA)["minutos"]
    assert para_santana > para_machico + 10
    assert 35 <= para_santana <= 70


def test_curral_hospital_ganha_a_camara_de_lobos():
    """O caso emblemático: CML é 'mais perto' em linha reta, mas o
    caminho real para lá passa pelo Funchal — o hospital tem de ganhar."""
    para_hnm = viagem.estimar(*CURRAL, *HNM)["minutos"]
    para_cml = viagem.estimar(*CURRAL, *CS_CAMARA_LOBOS)["minutos"]
    assert para_hnm < para_cml
    assert 15 <= para_hnm <= 45


def test_barreira_impede_atalho_sobre_a_serra():
    """Curral ↔ Serra de Água: 5,6 km em linha reta, vales vizinhos sem
    estrada direta. Sem barreiras seria ~10 min; tem de dar muito mais."""
    est = viagem.estimar(*CURRAL, 32.7275, -17.0260)
    assert est["minutos"] >= 35


def test_tempos_para_unidades_cobre_a_lista():
    lista = [
        {"id": "x1", "lat": HNM[0], "lng": HNM[1]},
        {"id": "x2", "lat": CS_CAMARA_LOBOS[0], "lng": CS_CAMARA_LOBOS[1]},
        {"id": "x3", "lat": PORTO_SANTO[0], "lng": PORTO_SANTO[1]},
    ]
    tempos = viagem.tempos_para_unidades(*FUNCHAL, lista)
    assert set(tempos) == {"x1", "x2", "x3"}
    assert tempos["x1"]["metodo"] == "rede"
    assert tempos["x3"] is None  # outra ilha


# --------------------------------------------------------------------- #
# Integração no encaminhamento                                            #
# --------------------------------------------------------------------- #

def test_resumo_da_unidade_tem_tempo_viagem(sem_esperas):
    saida = routing.decidir_encaminhamento("laranja", *FUNCHAL, quando=SEGUNDA_10H)
    tv = saida["unidade"]["tempo_viagem"]
    # O contrato é "o resumo traz um tempo de viagem utilizável", não
    # "veio deste método específico": desde a v0.11.3, quando a tabela
    # medida está preenchida (fonte ors/manual), ela tem prioridade
    # sobre a rede calibrada — e é isso que este cenário passa a dar
    # assim que alguém corre calcular_tempos_medidos.py.
    assert tv and tv["minutos"] >= 1
    assert tv["metodo"] in ("medido", "rede")
    assert saida["viagem_info"]["disponivel"] is True
    assert saida["viagem_info"]["metodo"] == tv["metodo"]


def test_do_curral_o_amarelo_vai_ao_hospital_e_nao_a_cml(sem_esperas):
    """Antes da v0.11 a ordenação em linha reta mandava o utente do
    Curral para Câmara de Lobos; por tempo de estrada, o hospital vem
    primeiro (o caminho para CML passa-lhe à porta)."""
    saida = routing.decidir_encaminhamento("amarelo", *CURRAL, quando=SEGUNDA_10H)
    assert saida["unidade"]["id"] == "hnm"
    ids_alternativas = [a["id"] for a in saida["alternativas"]]
    assert "cs_camara_lobos" in ids_alternativas


def test_candidatas_ordenadas_por_tempo(sem_esperas):
    saida = routing.decidir_encaminhamento("amarelo", *FUNCHAL, quando=SEGUNDA_10H)
    minutos = [
        u["tempo_viagem"]["minutos"]
        for u in [saida["unidade"], *saida["alternativas"]]
        if u.get("tempo_viagem")
    ]
    assert minutos == sorted(minutos)


def test_mensagens_incluem_minutos_de_carro(sem_esperas):
    saida = routing.decidir_encaminhamento("amarelo", *FUNCHAL, quando=SEGUNDA_10H)
    assert "min de carro" in saida["mensagem"]
    assert "min by car" in saida["mensagem_en"]


def test_porto_santo_continua_sem_atravessar_o_mar(sem_esperas):
    saida = routing.decidir_encaminhamento("amarelo", *PORTO_SANTO, quando=SEGUNDA_10H)
    assert saida["unidade"]["id"] == "cs_porto_santo"
    tv = saida["unidade"]["tempo_viagem"]
    assert tv and tv["minutos"] <= 15


# --------------------------------------------------------------------- #
# Regra de troca: viagem por estrada + espera real                        #
# --------------------------------------------------------------------- #

def test_tempo_total_usa_viagem_por_estrada():
    resumo = {
        "distancia_km": 40,  # o recuo antigo daria 48 min de viagem
        "tempo_viagem": {"minutos": 10, "metodo": "rede"},
        "tempo_espera": {"minutos": 20},
    }
    assert espera.tempo_total_estimado(resumo) == 30


def test_tempo_total_sem_estimativa_usa_o_recuo_antigo():
    resumo = {"distancia_km": 25, "tempo_espera": {"minutos": 10}}
    assert espera.tempo_total_estimado(resumo) == pytest.approx(40)  # 30 + 10


def test_troca_decide_com_tempos_de_estrada():
    """A montanha entra na conta: a unidade 'perto' em km mas com viagem
    longa por estrada perde para a que está a 10 min de carro."""
    perto = {
        "id": "perto", "nome": "perto", "aberta_agora": True,
        "distancia_km": 2, "tempo_viagem": {"minutos": 40, "metodo": "rede"},
        "tempo_espera": {"minutos": 30},
    }
    longe = {
        "id": "longe", "nome": "longe", "aberta_agora": True,
        "distancia_km": 7, "tempo_viagem": {"minutos": 10, "metodo": "rede"},
        "tempo_espera": {"minutos": 20},
    }
    principal, _, troca = espera.escolher_principal([perto, longe])
    assert principal is longe
    assert troca is not None
    assert troca["total_preterida_min"] == 70
    assert troca["total_escolhida_min"] == 30


# --------------------------------------------------------------------- #
# OSRM opcional: liga por configuração, recua em silêncio                 #
# --------------------------------------------------------------------- #

def test_osrm_desligado_por_omissao(monkeypatch):
    monkeypatch.delenv(viagem.VARIAVEL_OSRM, raising=False)
    viagem._repor_estado_osrm()
    assert viagem.estimar(*FUNCHAL, *MACHICO)["metodo"] == "rede"


def test_osrm_usado_quando_configurado(monkeypatch):
    monkeypatch.setenv(viagem.VARIAVEL_OSRM, "http://osrm.interno.exemplo")
    viagem._repor_estado_osrm()
    monkeypatch.setattr(
        viagem, "_pedir_osrm", lambda url: {"code": "Ok", "durations": [[0, 600.0]]}
    )
    est = viagem.estimar(*FUNCHAL, *MACHICO)
    assert est == {"minutos": 10, "metodo": "osrm"}
    viagem._repor_estado_osrm()


def test_osrm_em_falha_recua_para_a_rede_e_arrefece(monkeypatch):
    monkeypatch.setenv(viagem.VARIAVEL_OSRM, "http://osrm.interno.exemplo")
    viagem._repor_estado_osrm()
    chamadas = []

    def _explode(url):
        chamadas.append(url)
        raise TimeoutError("servidor em baixo")

    monkeypatch.setattr(viagem, "_pedir_osrm", _explode)
    primeira = viagem.estimar(*FUNCHAL, *MACHICO)
    segunda = viagem.estimar(*FUNCHAL, *SANTANA)
    assert primeira["metodo"] == "rede"  # recuou, a app não fica presa
    assert segunda["metodo"] == "rede"
    assert len(chamadas) == 1  # arrefecimento: não insiste já a seguir
    viagem._repor_estado_osrm()


# --------------------------------------------------------------------- #
# API                                                                     #
# --------------------------------------------------------------------- #

def test_api_encaminhamento_devolve_viagem(sem_esperas):
    from fastapi.testclient import TestClient
    from app.main import app

    cliente = TestClient(app)
    resposta = cliente.post(
        "/api/encaminhamento",
        json={"cor": "amarelo", "lat": FUNCHAL[0], "lng": FUNCHAL[1],
              "quando": SEGUNDA_10H.isoformat()},
    )
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["viagem_info"]["disponivel"] is True
    assert corpo["unidade"]["tempo_viagem"]["minutos"] >= 1


def test_api_endpoint_viagem():
    from fastapi.testclient import TestClient
    from app.main import app

    cliente = TestClient(app)
    resposta = cliente.get(
        "/api/viagem",
        params={
            "lat": CURRAL[0], "lng": CURRAL[1],
            "lat_destino": HNM[0], "lng_destino": HNM[1],
        },
    )
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["estimativa"]["metodo"] == "rede"
    assert corpo["distancia_km_linha_reta"] < corpo["estimativa"]["minutos"]  # 8.9 km vs ~29 min


def test_api_unidades_proxima_inclui_tempo():
    from fastapi.testclient import TestClient
    from app.main import app

    cliente = TestClient(app)
    resposta = cliente.get(
        "/api/unidades/proxima", params={"lat": FUNCHAL[0], "lng": FUNCHAL[1], "n": 3}
    )
    unidades_devolvidas = resposta.json()["unidades"]
    assert resposta.status_code == 200
    assert all("tempo_viagem" in u for u in unidades_devolvidas)
