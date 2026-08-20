"""Testes de integração da API (endpoint a endpoint)."""

from fastapi.testclient import TestClient

from app.main import app
from app.versao import VERSAO

cliente = TestClient(app)


def test_saude():
    resposta = cliente.get("/api/saude")
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["estado"] == "ok"
    assert corpo["versao"] == VERSAO
    assert corpo["perguntas_total"] == 1187


def test_pagina_principal_serve_html():
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]


def test_listar_queixas():
    resposta = cliente.get("/api/queixas")
    assert resposta.status_code == 200
    assert any(q["id"] == "agressao" for q in resposta.json())


def test_listar_red_flags():
    resposta = cliente.get("/api/red-flags")
    assert resposta.status_code == 200
    assert len(resposta.json()) >= 4


def test_triagem_devolve_primeira_pergunta():
    resposta = cliente.post("/api/triagem", json={"queixa": "agressao", "respostas": {}})
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["tipo"] == "pergunta"
    # v0.14.1: a cor e a prioridade não seguem para o frontend durante as
    # perguntas (a cor só aparece no resultado final).
    assert "cor" not in corpo["pergunta"]
    assert "prioridade" not in corpo["pergunta"]
    assert corpo["pergunta"]["texto"]  # texto (linguagem do utente) presente


def test_triagem_completa_devolve_resultado_com_cor_info():
    # 1.º discriminador (P1) positivo -> vermelho.
    resposta = cliente.post(
        "/api/triagem",
        json={"queixa": "agressao", "respostas": {"agressao_p1_1738": "sim"}},
    )
    corpo = resposta.json()
    assert corpo["tipo"] == "resultado"
    assert corpo["resultado"]["cor"] == "vermelho"
    assert corpo["resultado"]["cor_info"]["nome"] == "Vermelho"


def test_triagem_red_flags_e_vermelho():
    resposta = cliente.post("/api/triagem", json={"red_flags": ["sinais_avc"]})
    corpo = resposta.json()
    assert corpo["resultado"]["cor"] == "vermelho"


def test_triagem_sem_queixa_nem_red_flags_da_422():
    resposta = cliente.post("/api/triagem", json={})
    assert resposta.status_code == 422


def test_triagem_queixa_desconhecida_da_422():
    resposta = cliente.post("/api/triagem", json={"queixa": "nao_existe"})
    assert resposta.status_code == 422


def test_unidades_proximas():
    resposta = cliente.get("/api/unidades/proxima", params={"lat": 32.65, "lng": -16.91, "n": 3})
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert len(corpo["unidades"]) == 3
    distancias = [u["distancia_km"] for u in corpo["unidades"]]
    assert distancias == sorted(distancias)


def test_encaminhamento():
    resposta = cliente.post(
        "/api/encaminhamento", json={"cor": "verde", "lat": 32.65, "lng": -16.91}
    )
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert "acao" in corpo
    assert corpo["contactos"]["sns24"]["numero"] == "808 24 24 24"


def test_encaminhamento_cor_invalida_da_422():
    resposta = cliente.post(
        "/api/encaminhamento", json={"cor": "roxo", "lat": 32.65, "lng": -16.91}
    )
    assert resposta.status_code == 422
