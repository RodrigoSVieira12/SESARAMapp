"""Testes do motor de triagem (fluxos v0.3, em 3 fases).

Padrão a seguir quando alterares/adicionares regras: cada caminho
clinicamente importante deve ter aqui um teste do género
"dadas estas respostas, esperada esta cor".
"""

import pytest

from app.core.triage_engine import ErroTriagem, TriageEngine

engine = TriageEngine()


def test_ha_queixas_carregadas():
    queixas = engine.listar_queixas()
    assert len(queixas) >= 5
    ids = {q["id"] for q in queixas}
    assert "dor_toracica" in ids
    assert "febre" in ids


def test_primeira_pergunta_tem_fase_geral():
    saida = engine.avaliar("dor_toracica", {})
    assert saida["tipo"] == "pergunta"
    assert saida["pergunta"]["id"] == "dt_q1"
    assert saida["pergunta"]["fase"] == 1
    assert saida["progresso"]["respondidas"] == 0


def test_respostas_parciais_devolvem_proxima_pergunta():
    saida = engine.avaliar("febre", {"fe_q1": "nao"})
    assert saida["tipo"] == "pergunta"
    assert saida["pergunta"]["id"] == "fe_q2"
    assert saida["progresso"]["respondidas"] == 1


def test_dor_toracica_intensa_com_suores_e_vermelho():
    respostas = {"dt_q1": "sim", "dt_q2": "sim", "dt_q4": "sim"}
    saida = engine.avaliar("dor_toracica", respostas)
    assert saida["tipo"] == "resultado"
    assert saida["resultado"]["cor"] == "vermelho"
    assert "112" in saida["resultado"]["nota"]


def test_dor_toracica_com_aperto_irradiado_e_laranja():
    respostas = {
        "dt_q1": "sim", "dt_q2": "nao", "dt_q3": "sim",
        "dt_q4": "nao", "dt_q5": "sim",
    }
    saida = engine.avaliar("dor_toracica", respostas)
    assert saida["resultado"]["cor"] == "laranja"


def test_dor_toracica_muscular_e_verde():
    respostas = {
        "dt_q1": "sim", "dt_q2": "nao", "dt_q3": "nao", "dt_q5": "nao",
        "dt_q6": "nao", "dt_q7": "nao", "dt_q8": "sim", "dt_q9": "sim",
    }
    saida = engine.avaliar("dor_toracica", respostas)
    assert saida["resultado"]["cor"] == "verde"


def test_dor_toracica_episodios_posicionais_e_azul():
    respostas = {"dt_q1": "nao", "dt_q11": "nao", "dt_q12": "sim"}
    saida = engine.avaliar("dor_toracica", respostas)
    assert saida["resultado"]["cor"] == "azul"


def test_febre_bem_tolerada_e_azul():
    respostas = {
        "fe_q1": "nao", "fe_q2": "nao", "fe_q4": "nao", "fe_q5": "nao",
        "fe_q6": "nao", "fe_q7": "nao", "fe_q8": "nao", "fe_q9": "nao",
        "fe_q12": "sim", "fe_q13": "sim",
    }
    saida = engine.avaliar("febre", respostas)
    assert saida["resultado"]["cor"] == "azul"


def test_febre_prolongada_resistente_e_amarelo():
    saida = engine.avaliar("febre", {"fe_q1": "sim", "fe_q10": "sim"})
    assert saida["resultado"]["cor"] == "amarelo"
    assert "à medicação" in saida["resultado"]["motivo"]  # acentos corretos


def test_dor_cabeca_subita_explosiva_e_vermelho():
    saida = engine.avaliar("dor_cabeca", {"dc_q1": "sim"})
    assert saida["resultado"]["cor"] == "vermelho"


def test_trauma_ligeiro_e_azul():
    respostas = {
        "tq_q1": "sim", "tq_q2": "nao", "tq_q4": "nao", "tq_q7": "nao",
        "tq_q8": "nao", "tq_q9": "nao", "tq_q10": "nao", "tq_q11": "sim",
    }
    saida = engine.avaliar("trauma_queda", respostas)
    assert saida["resultado"]["cor"] == "azul"


def test_falta_de_ar_labios_azulados_e_vermelho():
    saida = engine.avaliar(
        "falta_de_ar", {"fa_q1": "sim", "fa_q2": "sim", "fa_q3": "sim"}
    )
    assert saida["resultado"]["cor"] == "vermelho"


def test_red_flag_e_vermelho():
    resultado = engine.resultado_red_flags(["inconsciencia"])
    assert resultado["cor"] == "vermelho"
    assert "112" in resultado["nota"]


def test_red_flag_desconhecida_da_erro():
    with pytest.raises(ErroTriagem):
        engine.resultado_red_flags(["nao_existe"])


def test_queixa_desconhecida_da_erro():
    with pytest.raises(ErroTriagem):
        engine.avaliar("queixa_inventada", {})


def test_resposta_invalida_da_erro():
    with pytest.raises(ErroTriagem):
        engine.avaliar("febre", {"fe_q1": "talvez"})
