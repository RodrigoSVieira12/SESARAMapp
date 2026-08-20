"""Testes das novidades da v0.6: pesquisa da queixa em texto livre,
autocuidado estruturado (cartões de cuidado) e campos de tradução (*_en).

Data de referência: 2026-07-04 é um sábado (ver test_feriados_e_dias.py).
"""

from datetime import datetime

from fastapi.testclient import TestClient

from app.core import routing, sugestoes
from app.core.cores import info_cor
from app.main import app

cliente = TestClient(app)

FUNCHAL = (32.6669, -16.9241)
SABADO_15H = datetime(2026, 7, 4, 15, 0)


# ------------------------------------------- pesquisa em texto livre --


def test_sugerir_texto_livre_em_portugues():
    resposta = cliente.get("/api/queixas/sugerir", params={"q": "dói-me a barriga"})
    ids = [s["id"] for s in resposta.json()["sugestoes"]]
    assert ids and ids[0] == "dor_abdominal_no_adulto"


def test_sugerir_ignora_acentos_e_maiusculas():
    queixas = cliente.get("/api/queixas").json()
    ids = [s["id"] for s in sugestoes.sugerir("COLICA", queixas)]
    assert "dor_abdominal_no_adulto" in ids


def test_sugerir_em_ingles():
    resposta = cliente.get("/api/queixas/sugerir", params={"q": "fever and chills"})
    ids = [s["id"] for s in resposta.json()["sugestoes"]]
    assert ids and ids[0] == "indisposicao_no_adulto"


def test_sugerir_sem_correspondencia_devolve_lista_vazia():
    resposta = cliente.get("/api/queixas/sugerir", params={"q": "xyzqwerty"})
    assert resposta.json()["sugestoes"] == []


def test_sinonimos_apontam_para_fluxos_existentes():
    ids_fluxos = {q["id"] for q in cliente.get("/api/queixas").json()}
    assert set(sugestoes.SINONIMOS) <= ids_fluxos


# --------------------------------------------- autocuidado estruturado --


def test_autocuidado_do_verde_tem_listas_e_traducao():
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=SABADO_15H)
    ac = saida["autocuidado"]
    assert ac["fazer"] and isinstance(ac["fazer"], list)
    assert ac["alerta"] and isinstance(ac["alerta"], list)
    assert ac["titulo_en"] and ac["alerta_titulo"]


def test_autocuidado_do_azul_tem_listas():
    saida = routing.decidir_encaminhamento("azul", *FUNCHAL, quando=SABADO_15H)
    ac = saida["autocuidado"]
    assert ac["fazer"] and ac["alerta"]


# ------------------------------------------------- campos de tradução --


def test_cores_incluem_traducao_inglesa():
    info = info_cor("verde")
    assert info["nome_en"] == "Green"
    assert info["classificacao_en"] == "Less urgent"
    # As cores em si não mudam: continua o hex de sempre.
    assert info["hex"] == "#2E7D32"


def test_primeira_pergunta_traz_texto_ingles():
    resposta = cliente.post("/api/triagem", json={"queixa": "agressao", "respostas": {}})
    pergunta = resposta.json()["pergunta"]
    # v0.14.1: o texto passa a ser em linguagem do utente; a versão inglesa
    # deixa de ser a tradução clínica literal ("Airway compromise?"), mas
    # continua a existir e a falar de respiração.
    assert "breathing" in pergunta["texto_en"].lower()


def test_red_flags_vem_traduzidos():
    sinais = cliente.get("/api/red-flags").json()
    assert sinais and all(s.get("texto_en") for s in sinais)


def test_queixa_listada_com_nome_ingles():
    queixas = {q["id"]: q for q in cliente.get("/api/queixas").json()}
    assert queixas["dor_toracica"]["nome_en"] == "Chest pain"
