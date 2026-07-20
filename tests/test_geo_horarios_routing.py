"""Testes de geografia, horários e lógica de encaminhamento (v0.3).

Nota sobre datas fixas: 2026-06-29 é uma segunda-feira. Usar datas fixas
torna os testes determinísticos.
"""

from datetime import datetime

from app.core import horarios, routing
from app.core.geo import haversine_km

SEGUNDA_10H = datetime(2026, 6, 29, 10, 0)
SEGUNDA_03H = datetime(2026, 6, 29, 3, 0)
DOMINGO_15H = datetime(2026, 6, 28, 15, 0)

FUNCHAL = (32.6496, -16.9086)
CALHETA = (32.7318, -17.1764)
PORTO_SANTO = (33.06, -16.34)


# ---------------------------------------------------------------- geo --

def test_haversine_distancia_zero():
    assert haversine_km(32.65, -16.9, 32.65, -16.9) == 0


def test_haversine_funchal_machico_plausivel():
    distancia = haversine_km(32.6496, -16.9086, 32.7249, -16.7715)
    assert 10 < distancia < 25


def test_haversine_e_simetrica():
    ida = haversine_km(32.65, -16.9, 33.06, -16.34)
    volta = haversine_km(33.06, -16.34, 32.65, -16.9)
    assert abs(ida - volta) < 1e-9


# ----------------------------------------------------------- horarios --

def test_datas_de_referencia_corretas():
    assert SEGUNDA_10H.weekday() == 0
    assert DOMINGO_15H.weekday() == 6


def test_horario_24h_sempre_aberto():
    assert horarios.esta_aberto({"tipo": "24h"}, SEGUNDA_03H)


def test_horario_semanal():
    horario = {"tipo": "semanal", "horas": {"seg": ["08:00-20:00"]}}
    assert horarios.esta_aberto(horario, SEGUNDA_10H)
    assert not horarios.esta_aberto(horario, SEGUNDA_03H)
    assert not horarios.esta_aberto(horario, DOMINGO_15H)


def test_horario_fecha_no_limite():
    horario = {"tipo": "semanal", "horas": {"seg": ["08:00-20:00"]}}
    assert not horarios.esta_aberto(horario, datetime(2026, 6, 29, 20, 0))
    assert horarios.esta_aberto(horario, datetime(2026, 6, 29, 19, 59))


def test_horario_tolera_travessao_tipografico():
    # Se alguém escrever a faixa com o travessão do Word, não rebenta.
    horario = {"tipo": "semanal", "horas": {"seg": ["08:30\u201317:00"]}}
    assert horarios.esta_aberto(horario, SEGUNDA_10H)


# ------------------------------------------------------------ routing --

def test_vermelho_manda_ligar_112():
    saida = routing.decidir_encaminhamento("vermelho", *FUNCHAL, quando=SEGUNDA_10H)
    assert saida["acao"] == "ligar_112"
    assert saida["unidade"] is not None


def test_laranja_no_funchal_vai_ao_hospital():
    saida = routing.decidir_encaminhamento("laranja", *FUNCHAL, quando=SEGUNDA_10H)
    assert saida["acao"] == "ir_unidade"
    assert saida["unidade"]["id"] == "hnm"
    assert saida["unidade"]["aberta_agora"] is True


def test_laranja_na_calheta_vai_direto_ao_hospital():
    """v0.12.1 (indicação do SESARAM): laranja vai DIRETO ao hospital,
    mesmo havendo atendimento urgente aberto na Calheta. Antes, a app
    orientava para a urgência local; a política mudou e vive em
    app/data/encaminhamento.json."""
    saida = routing.decidir_encaminhamento("laranja", *CALHETA, quando=SEGUNDA_10H)
    assert saida["unidade"]["id"] == "hnm"
    assert "urgencia_polivalente" in saida["unidade"]["horarios"]
    assert saida["politica"]["aplicada"] is True


def test_verde_de_dia_vai_a_unidade_aberta():
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=SEGUNDA_10H)
    assert saida["acao"] == "ir_unidade"
    assert saida["unidade"]["aberta_agora"] is True
    assert saida["unidade"]["tipo"] == "centro_saude"


def test_verde_indica_centro_de_saude_para_seguimento():
    saida = routing.decidir_encaminhamento("verde", *CALHETA, quando=SEGUNDA_10H)
    assert "centro_saude_proximo" in saida


def test_verde_de_madrugada_vai_a_urgencia_aberta():
    # Com as urgências 24h dos centros de saúde, às 3h há sempre algo
    # aberto: já não se manda ninguém para uma porta fechada.
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=SEGUNDA_03H)
    assert saida["acao"] == "ir_unidade"
    assert saida["unidade"]["aberta_agora"] is True
    assert "atendimento_urgente" in saida["unidade"]["horarios"]


def test_azul_recomenda_autocuidado():
    saida = routing.decidir_encaminhamento("azul", *FUNCHAL, quando=SEGUNDA_10H)
    assert saida["acao"] == "autocuidado"
    assert "SNS 24" in saida["mensagem"]


# ------------------------------------------------------- regra da ilha --

def test_recomendacoes_no_funchal_nao_atravessam_o_mar():
    saida = routing.decidir_encaminhamento("laranja", *FUNCHAL, quando=SEGUNDA_10H)
    assert saida["ilha"] == "madeira"
    assert saida["unidade"]["concelho"] != "Porto Santo"
    for alternativa in saida["alternativas"]:
        assert alternativa["concelho"] != "Porto Santo"


def test_laranja_no_porto_santo_fica_na_ilha_com_nota_de_transferencia():
    saida = routing.decidir_encaminhamento("laranja", *PORTO_SANTO, quando=SEGUNDA_10H)
    assert saida["ilha"] == "porto_santo"
    assert saida["unidade"]["concelho"] == "Porto Santo"
    assert saida["alternativas"] == []
    assert "Nélio Mendonça" in saida["mensagem"]


def test_vermelho_no_porto_santo_referencia_local_com_nota():
    saida = routing.decidir_encaminhamento("vermelho", *PORTO_SANTO, quando=SEGUNDA_10H)
    assert saida["acao"] == "ligar_112"
    assert saida["unidade"]["concelho"] == "Porto Santo"
    assert "Nélio Mendonça" in saida["mensagem"]


def test_amarelo_no_porto_santo_sem_alternativas():
    saida = routing.decidir_encaminhamento("amarelo", *PORTO_SANTO, quando=SEGUNDA_10H)
    assert saida["unidade"]["concelho"] == "Porto Santo"
    assert saida["alternativas"] == []
