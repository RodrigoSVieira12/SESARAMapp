"""Testes das melhorias: validação estrutural dos fluxos no arranque
(ciclos, perguntas inalcançáveis) e hora simulada no encaminhamento."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.triage_engine import TriageEngine
from app.main import app

cliente = TestClient(app)

RED_FLAGS_MINIMO = {
    "id": "red_flags",
    "sinais": [{"id": "x", "texto": "Sinal de teste"}],
}


def escrever(pasta, nome, dados):
    (pasta / nome).write_text(
        json.dumps(dados, ensure_ascii=False), encoding="utf-8"
    )


def fluxo(perguntas):
    return {"id": "teste", "nome": "Teste", "perguntas": perguntas}


# ----------------------------------------- validação estrutural do motor --

def test_ciclo_e_detetado_no_arranque(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(tmp_path, "teste.json", fluxo([
        {"id": "q1", "texto": "?", "sim": {"proxima": "q2"},
         "nao": {"resultado": {"cor": "verde"}}},
        {"id": "q2", "texto": "?", "sim": {"proxima": "q1"},
         "nao": {"resultado": {"cor": "verde"}}},
    ]))
    with pytest.raises(RuntimeError, match="[Cc]iclo"):
        TriageEngine(tmp_path)


def test_pergunta_inalcancavel_e_detetada(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(tmp_path, "teste.json", fluxo([
        {"id": "q1", "texto": "?", "sim": {"resultado": {"cor": "laranja"}},
         "nao": {"resultado": {"cor": "verde"}}},
        {"id": "q2", "texto": "solta", "sim": {"resultado": {"cor": "verde"}},
         "nao": {"resultado": {"cor": "verde"}}},
    ]))
    with pytest.raises(RuntimeError, match="inalcan"):
        TriageEngine(tmp_path)


def test_fluxo_valido_carrega(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(tmp_path, "teste.json", fluxo([
        {"id": "q1", "texto": "?", "sim": {"proxima": "q2"},
         "nao": {"resultado": {"cor": "verde"}}},
        {"id": "q2", "texto": "?", "sim": {"resultado": {"cor": "amarelo"}},
         "nao": {"resultado": {"cor": "azul"}}},
    ]))
    motor = TriageEngine(tmp_path)
    assert "teste" in motor.fluxos
    saida = motor.avaliar("teste", {"q1": "sim", "q2": "nao"})
    assert saida["resultado"]["cor"] == "azul"


# --------------------------------------------- hora simulada (API) --------

def test_encaminhamento_com_hora_simulada_de_madrugada():
    resposta = cliente.post("/api/encaminhamento", json={
        "cor": "verde", "lat": 32.6496, "lng": -16.9086,
        "quando": "2026-06-29T03:00:00",
    })
    corpo = resposta.json()
    assert resposta.status_code == 200
    # As 3h os centros de saude normais estao fechados, mas ha
    # atendimentos urgentes 24h: a app envia para um deles, aberto.
    assert corpo["acao"] == "ir_unidade"
    assert corpo["unidade"]["aberta_agora"] is True
    assert "atendimento_urgente" in corpo["unidade"]["horarios"]


def test_encaminhamento_com_hora_simulada_de_dia():
    resposta = cliente.post("/api/encaminhamento", json={
        "cor": "verde", "lat": 32.6496, "lng": -16.9086,
        "quando": "2026-06-29T10:00:00",
    })
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["acao"] == "ir_unidade"
    assert corpo["unidade"]["aberta_agora"] is True
