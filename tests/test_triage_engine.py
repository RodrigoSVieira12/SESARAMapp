"""Testes do motor de triagem por discriminadores de Manchester (v0.14.0).

Modelo: cada queixa é uma lista de discriminadores ordenados por
prioridade (P1->P5). O primeiro "sim" decide a cor; se todos forem "não",
o desfecho fica um nível abaixo do discriminador menos urgente do fluxo,
sem passar de azul (v0.14.1). Padrão a seguir ao alterar regras: cada
caminho clinicamente importante deve ter aqui um teste "dadas estas
respostas, esperada esta cor".
"""

import pytest

from app.core.triage_engine import ErroTriagem, TriageEngine

engine = TriageEngine()


def _primeiro_da_prioridade(fluxo_id: str, prioridade: str) -> dict:
    """Devolve o primeiro discriminador de uma dada prioridade num fluxo."""
    for d in engine.fluxos[fluxo_id]["perguntas"]:
        if d["prioridade"] == prioridade:
            return d
    raise AssertionError(f"{fluxo_id} sem discriminador {prioridade}")


def _responder_nao_ate(fluxo_id: str, alvo_id: str) -> dict[str, str]:
    """Respostas 'não' a todos os discriminadores antes de `alvo_id`."""
    respostas: dict[str, str] = {}
    for d in engine.fluxos[fluxo_id]["perguntas"]:
        if d["id"] == alvo_id:
            break
        respostas[d["id"]] = "nao"
    return respostas


# ------------------------------------------------------------- carregamento --


def test_ha_muitas_queixas_carregadas():
    queixas = engine.listar_queixas()
    assert len(queixas) >= 50
    ids = {q["id"] for q in queixas}
    assert "agressao" in ids
    assert "asma" in ids
    assert "dor_toracica" in ids


def test_queixa_tem_nome_e_flag_pediatrico():
    queixas = {q["id"]: q for q in engine.listar_queixas()}
    assert queixas["agressao"]["nome"] == "Agressão"
    assert queixas["agressao"]["pediatrico"] is False
    # Fluxos pediátricos vêm marcados (a tabela identifica-os com "(P)").
    assert queixas["bebe_que_chora_12_meses"]["pediatrico"] is True


# --------------------------------------------------------------- perguntas --


def test_pergunta_nao_expoe_cor_nem_prioridade():
    """A cor de Manchester não aparece durante as perguntas (v0.14.1):
    só deve surgir no resultado final."""
    saida = engine.avaliar("agressao", {})
    assert saida["tipo"] == "pergunta"
    pergunta = saida["pergunta"]
    assert "cor" not in pergunta
    assert "prioridade" not in pergunta
    assert saida["progresso"]["respondidas"] == 0


def test_pergunta_usa_linguagem_do_utente():
    """A pergunta mostrada usa o texto_utente (linguagem do dia a dia) e já
    não traz um campo 'ajuda' à parte. O texto clínico e a descrição
    continuam guardados no discriminador, para os fluxogramas."""
    saida = engine.avaliar("agressao", {})
    pergunta = saida["pergunta"]
    assert "ajuda" not in pergunta
    disc = engine.fluxos["agressao"]["perguntas"][0]
    # texto clínico e descrição intactos no discriminador
    assert disc["texto"] == "Compromisso da via aérea?"
    assert "descricao" in disc
    # o que é mostrado é o texto do utente, não o clínico
    assert pergunta["texto"] == disc["texto_utente"]
    assert pergunta["texto"] != disc["texto"]
    # e a tradução para o utente segue no texto_en
    assert "breathing" in pergunta["texto_en"].lower()


def test_respostas_parciais_devolvem_proxima_pergunta():
    disc = engine.fluxos["agressao"]["perguntas"]
    saida = engine.avaliar("agressao", {disc[0]["id"]: "nao"})
    assert saida["tipo"] == "pergunta"
    assert saida["pergunta"]["id"] == disc[1]["id"]
    assert saida["progresso"]["respondidas"] == 1


# ---------------------------------------------------------------- desfechos --


def test_sim_num_p1_da_vermelho_com_112():
    d = _primeiro_da_prioridade("agressao", "P1")
    saida = engine.avaliar("agressao", {d["id"]: "sim"})
    assert saida["tipo"] == "resultado"
    assert saida["resultado"]["cor"] == "vermelho"
    assert "112" in saida["resultado"]["nota"]


def test_sim_num_p2_da_laranja():
    d = _primeiro_da_prioridade("asma", "P2")
    respostas = _responder_nao_ate("asma", d["id"])
    respostas[d["id"]] = "sim"
    saida = engine.avaliar("asma", respostas)
    assert saida["resultado"]["cor"] == "laranja"


def test_sim_num_p3_da_amarelo():
    d = _primeiro_da_prioridade("asma", "P3")
    respostas = _responder_nao_ate("asma", d["id"])
    respostas[d["id"]] = "sim"
    saida = engine.avaliar("asma", respostas)
    assert saida["resultado"]["cor"] == "amarelo"


def test_sim_num_p4_da_verde():
    d = _primeiro_da_prioridade("asma", "P4")
    respostas = _responder_nao_ate("asma", d["id"])
    respostas[d["id"]] = "sim"
    saida = engine.avaliar("asma", respostas)
    assert saida["resultado"]["cor"] == "verde"


def test_todas_as_respostas_nao_da_azul():
    respostas = {d["id"]: "nao" for d in engine.fluxos["asma"]["perguntas"]}
    saida = engine.avaliar("asma", respostas)
    assert saida["resultado"]["cor"] == "azul"
    assert saida["resultado"]["prioridade"] == "P5"


def test_sem_positivo_fica_um_nivel_abaixo_do_menos_urgente():
    """v0.14.1: responder 'não' a tudo fica um nível abaixo do discriminador
    menos urgente do fluxo, sem passar de azul. Nos fluxos com discriminadores
    de prioridade baixa (verde/P4) continua a dar azul; nos que só têm
    discriminadores muito urgentes, evita o salto até azul."""
    casos = {
        # fluxo cujo menos urgente é laranja/P2 -> desfecho amarelo/P3
        "pedido_para_terceiros": ("P3", "amarelo"),
        # fluxos cujo menos urgente é amarelo/P3 -> desfecho verde/P4
        "autoagressao": ("P4", "verde"),
        "grande_traumatismo": ("P4", "verde"),
        # fluxo habitual (menos urgente verde/P4) -> continua azul/P5
        "asma": ("P5", "azul"),
    }
    for fid, (prioridade, cor) in casos.items():
        respostas = {d["id"]: "nao" for d in engine.fluxos[fid]["perguntas"]}
        resultado = engine.avaliar(fid, respostas)["resultado"]
        assert resultado["prioridade"] == prioridade, fid
        assert resultado["cor"] == cor, fid


def test_o_primeiro_sim_ganha_ainda_que_haja_respostas_a_seguir():
    """Discriminador de prioridade mais alta positivo decide, mesmo que
    haja respostas 'sim' em prioridades mais baixas."""
    disc = engine.fluxos["asma"]["perguntas"]
    p1 = _primeiro_da_prioridade("asma", "P1")
    # tudo "sim" -> ganha o P1 (vermelho)
    respostas = {d["id"]: "sim" for d in disc}
    saida = engine.avaliar("asma", respostas)
    assert saida["resultado"]["cor"] == "vermelho"
    assert saida["resultado"]["discriminador"] == p1.get("texto_utente", p1["texto"])


# -------------------------------------------------------------- red flags --


def test_red_flag_e_vermelho():
    resultado = engine.resultado_red_flags(["inconsciencia"])
    assert resultado["cor"] == "vermelho"
    assert "112" in resultado["nota"]


def test_red_flag_desconhecida_da_erro():
    with pytest.raises(ErroTriagem):
        engine.resultado_red_flags(["nao_existe"])


# ------------------------------------------------------------------ erros --


def test_queixa_desconhecida_da_erro():
    with pytest.raises(ErroTriagem):
        engine.avaliar("queixa_inventada", {})


def test_resposta_invalida_da_erro():
    d = engine.fluxos["asma"]["perguntas"][0]
    with pytest.raises(ErroTriagem):
        engine.avaliar("asma", {d["id"]: "talvez"})
