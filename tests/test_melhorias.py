"""Testes das validações do motor no arranque (modelo por discriminadores,
v0.14.0) e da hora simulada no encaminhamento.

No modelo por discriminadores não há ramos nem saltos, por isso deixam de
existir ciclos e perguntas inalcançáveis. Em troca, o validador garante
que cada discriminador tem prioridade e cor válidas, que a cor
corresponde à prioridade, e que os discriminadores estão ordenados de P1
para P5.
"""

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
    (pasta / nome).write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def fluxo(perguntas):
    return {"id": "teste", "nome": "Teste", "perguntas": perguntas}


def _disc(pid, prioridade, cor, texto="?", **extra):
    return {"id": pid, "prioridade": prioridade, "cor": cor, "texto": texto, **extra}


# ----------------------------------------- validação estrutural do motor --


def test_cor_invalida_e_detetada(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(tmp_path, "teste.json", fluxo([_disc("q1", "P1", "roxo")]))
    with pytest.raises(RuntimeError, match="cor inválida"):
        TriageEngine(tmp_path)


def test_prioridade_invalida_e_detetada(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(tmp_path, "teste.json", fluxo([_disc("q1", "P9", "vermelho")]))
    with pytest.raises(RuntimeError, match="prioridade inválida"):
        TriageEngine(tmp_path)


def test_cor_que_nao_corresponde_a_prioridade_e_detetada(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    # P1 devia ser vermelho, não verde.
    escrever(tmp_path, "teste.json", fluxo([_disc("q1", "P1", "verde")]))
    with pytest.raises(RuntimeError, match="cor"):
        TriageEngine(tmp_path)


def test_discriminadores_fora_de_ordem_sao_detetados(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    # P3 (amarelo) antes de P1 (vermelho): fora de ordem.
    escrever(
        tmp_path,
        "teste.json",
        fluxo(
            [
                _disc("q1", "P3", "amarelo"),
                _disc("q2", "P1", "vermelho"),
            ]
        ),
    )
    with pytest.raises(RuntimeError, match="ordene|prioridade mais baixa"):
        TriageEngine(tmp_path)


def test_discriminador_sem_texto_e_detetado(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(tmp_path, "teste.json", fluxo([_disc("q1", "P1", "vermelho", texto="  ")]))
    with pytest.raises(RuntimeError, match="sem texto"):
        TriageEngine(tmp_path)


def test_fluxo_valido_carrega_e_avalia(tmp_path):
    escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    escrever(
        tmp_path,
        "teste.json",
        fluxo(
            [
                _disc("q1", "P1", "vermelho", texto="Grave?"),
                _disc("q2", "P3", "amarelo", texto="Urgente?"),
            ]
        ),
    )
    motor = TriageEngine(tmp_path)
    assert "teste" in motor.fluxos
    # q1 não, q2 sim -> amarelo
    saida = motor.avaliar("teste", {"q1": "nao", "q2": "sim"})
    assert saida["resultado"]["cor"] == "amarelo"
    # tudo não -> um nível abaixo do menos urgente (aqui P3/amarelo), ou
    # seja P4/verde (regra "sem discriminador positivo" da v0.14.1).
    saida = motor.avaliar("teste", {"q1": "nao", "q2": "nao"})
    assert saida["resultado"]["cor"] == "verde"
    assert saida["resultado"]["prioridade"] == "P4"


# --------------------------------------------- hora simulada (API) --------


def test_encaminhamento_com_hora_simulada_de_madrugada():
    resposta = cliente.post(
        "/api/encaminhamento",
        json={
            "cor": "verde",
            "lat": 32.6496,
            "lng": -16.9086,
            "quando": "2026-06-29T03:00:00",
        },
    )
    corpo = resposta.json()
    assert resposta.status_code == 200
    # As 3h os centros de saude normais estao fechados, mas ha
    # atendimentos urgentes 24h: a app envia para um deles, aberto.
    assert corpo["acao"] == "ir_unidade"
    assert corpo["unidade"]["aberta_agora"] is True
    assert "atendimento_urgente" in corpo["unidade"]["horarios"]


def test_encaminhamento_com_hora_simulada_de_dia():
    resposta = cliente.post(
        "/api/encaminhamento",
        json={
            "cor": "verde",
            "lat": 32.6496,
            "lng": -16.9086,
            "quando": "2026-06-29T10:00:00",
        },
    )
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["acao"] == "ir_unidade"
    assert corpo["unidade"]["aberta_agora"] is True
