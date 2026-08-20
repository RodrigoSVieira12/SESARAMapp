"""Testes da v0.15.0 — aconselhamento ao utente ("O que pode fazer").

Cobrem: (1) o ficheiro app/data/aconselhamento.json carrega e tem estrutura
válida; (2) o motor anexa o aconselhamento ao resultado, nos dois ramos;
(3) a política de segurança (o backend guarda itens só-clínicos sem
texto_utente, que o frontend não deve mostrar); (4) a integração via API; e
(5) a tolerância do carregamento (ficheiro em falta não parte o motor;
ficheiro estruturalmente partido levanta erro).

A lógica de triagem em si (prioridades e cores) NÃO muda nesta versão — isso
continua coberto pelos testes do motor. Aqui só se testa o extra aditivo.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.triage_engine import FICHEIRO_ACONSELHAMENTO, TriageEngine
from app.main import app

engine = TriageEngine()
cliente = TestClient(app)

CORES_VALIDAS = {"vermelho", "laranja", "amarelo", "verde", "azul"}


def _primeiro_disc(fluxo_id: str) -> dict:
    return engine.fluxos[fluxo_id]["perguntas"][0]


def _cor_do_primeiro_sim(fluxo_id: str) -> str:
    return _primeiro_disc(fluxo_id)["cor"]


# ----------------------------------------------------- ficheiro de dados --


def test_ficheiro_aconselhamento_existe_e_carrega():
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    assert isinstance(dados, dict)
    assert "descricao" in dados
    assert isinstance(dados["fluxos"], dict)
    assert len(dados["fluxos"]) >= 50


def test_estrutura_de_cada_item_valida():
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    total = 0
    com_utente = 0
    for fid, blocos in dados["fluxos"].items():
        assert isinstance(blocos, dict)
        for cor, bloco in blocos.items():
            assert cor in CORES_VALIDAS
            itens = bloco["itens"]
            assert isinstance(itens, list) and itens
            for it in itens:
                # 'texto' (clínico) é sempre obrigatório
                assert isinstance(it.get("texto"), str) and it["texto"].strip()
                total += 1
                tu = it.get("texto_utente")
                if tu is not None:
                    assert isinstance(tu, str) and tu.strip()
                    # v0.15.1: cada versão de utente traz o par inglês.
                    tuen = it.get("texto_utente_en")
                    assert isinstance(tuen, str) and tuen.strip()
                    com_utente += 1
    assert total > 500
    # deve haver uma boa fatia com versão de utente (política: só essas são
    # mostradas), mas nem todos os itens a têm (os só-clínicos não a têm).
    assert com_utente > 0
    assert com_utente < total


def test_itens_utente_nao_usam_travessao():
    """Regra da casa: nada de travessões (— / –) nos textos do utente,
    em nenhuma das duas línguas."""
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    for blocos in dados["fluxos"].values():
        for bloco in blocos.values():
            for it in bloco["itens"]:
                for tu in (it.get("texto_utente"), it.get("texto_utente_en")):
                    if tu:
                        assert "\u2014" not in tu and "\u2013" not in tu


# ------------------------------------------------- motor: anexar resultado --


def test_motor_carrega_aconselhamento():
    assert engine.aconselhamento
    assert "dor_toracica" in engine.aconselhamento


def test_resultado_positivo_traz_aconselhamento():
    disc = _primeiro_disc("dor_toracica")
    out = engine.avaliar("dor_toracica", {disc["id"]: "sim"})
    resultado = out["resultado"]
    assert "aconselhamento" in resultado
    ac = resultado["aconselhamento"]
    assert ac is not None
    assert ac["itens"]
    # todos os itens têm 'texto'; a versão de utente é opcional
    for it in ac["itens"]:
        assert it.get("texto")


def test_helper_aconselhamento_para():
    cor = _cor_do_primeiro_sim("dor_toracica")
    ac = engine._aconselhamento_para("dor_toracica", cor)
    assert ac is not None and ac["itens"]
    # devolve uma cópia (não a referência interna), para o chamador não
    # conseguir alterar o estado do motor sem querer.
    ac["itens"].append({"texto": "xpto"})
    ac2 = engine._aconselhamento_para("dor_toracica", cor)
    assert all(it.get("texto") != "xpto" for it in ac2["itens"])


def test_aconselhamento_none_quando_nao_ha():
    # combinação (fluxo, cor) sem conselhos definidos -> None
    assert engine._aconselhamento_para("dor_toracica", "azul") is None


def test_chave_aconselhamento_presente_mesmo_quando_none():
    """A chave 'aconselhamento' existe sempre no resultado, ainda que None,
    para o frontend/integradores poderem contar com ela."""
    fluxo = engine.fluxos["dor_toracica"]
    respostas = {d["id"]: "nao" for d in fluxo["perguntas"]}
    resultado = engine.avaliar("dor_toracica", respostas)["resultado"]
    assert "aconselhamento" in resultado  # desfecho azul, sem conselhos
    assert resultado["aconselhamento"] is None


# --------------------------------------------- política de segurança (dados) --


def test_backend_guarda_itens_so_clinicos_sem_versao_utente():
    """Fidelidade + segurança: existem itens clínicos guardados SEM
    texto_utente (ex.: isolamento de contacto, fármacos por nome). O motor
    entrega-os; é o frontend que só mostra os que têm texto_utente."""
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    so_clinicos = [
        it["texto"]
        for blocos in dados["fluxos"].values()
        for bloco in blocos.values()
        for it in bloco["itens"]
        if "texto_utente" not in it
    ]
    assert so_clinicos  # a política pressupõe que estes existem
    junto = " || ".join(so_clinicos).lower()
    # pelo menos um exemplo claramente só-profissional está entre eles
    assert "isolamento de contacto" in junto or "nitroglicerina" in junto


# ------------------------------------------------------- integração via API --


def test_api_triagem_resultado_traz_aconselhamento():
    disc = _primeiro_disc("dor_toracica")
    resp = cliente.post(
        "/api/triagem",
        json={"queixa": "dor_toracica", "respostas": {disc["id"]: "sim"}},
    )
    corpo = resp.json()
    assert resp.status_code == 200
    assert corpo["tipo"] == "resultado"
    ac = corpo["resultado"]["aconselhamento"]
    assert ac and ac["itens"]
    assert all(it.get("texto") for it in ac["itens"])


def test_api_integracao_traz_aconselhamento_com_texto_clinico():
    disc = _primeiro_disc("dor_toracica")
    resp = cliente.post(
        "/api/integracao/triagem",
        json={"queixa": "dor_toracica", "respostas": {disc["id"]: "sim"}},
    )
    corpo = resp.json()
    assert resp.status_code == 200
    ac = corpo["resultado"]["aconselhamento"]
    assert ac and ac["itens"]
    # o integrador recebe o texto clínico (não só a versão de utente)
    assert all(it.get("texto") for it in ac["itens"])


# ----------------------------------------------------- carregamento robusto --


def test_motor_sem_ficheiro_de_aconselhamento_arranca(tmp_path: Path):
    """Ficheiro em falta: apenas avisa e segue sem aconselhamento."""
    inexistente = tmp_path / "nao_existe.json"
    motor = TriageEngine(ficheiro_aconselhamento=inexistente)
    assert motor.aconselhamento == {}
    disc = motor.fluxos["dor_toracica"]["perguntas"][0]
    resultado = motor.avaliar("dor_toracica", {disc["id"]: "sim"})["resultado"]
    assert resultado["aconselhamento"] is None  # chave presente, sem dados


def test_ficheiro_estruturalmente_partido_levanta_erro(tmp_path: Path):
    mau = tmp_path / "aconselhamento.json"
    mau.write_text(json.dumps({"sem_fluxos": True}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        TriageEngine(ficheiro_aconselhamento=mau)


def test_fluxo_ou_cor_desconhecidos_sao_ignorados(tmp_path: Path):
    """Chaves desconhecidas não partem o arranque: são avisadas e ignoradas."""
    conteudo = {
        "descricao": "teste",
        "fluxos": {
            "fluxo_que_nao_existe": {"vermelho": {"itens": [{"texto": "x"}]}},
            "dor_toracica": {
                "roxo": {"itens": [{"texto": "cor inválida"}]},
                "vermelho": {"itens": [{"texto": "válido", "texto_utente": "faça isto"}]},
            },
        },
    }
    bom = tmp_path / "aconselhamento.json"
    bom.write_text(json.dumps(conteudo, ensure_ascii=False), encoding="utf-8")
    motor = TriageEngine(ficheiro_aconselhamento=bom)
    # o fluxo inexistente e a cor inválida foram descartados
    assert "fluxo_que_nao_existe" not in motor.aconselhamento
    assert "roxo" not in motor.aconselhamento.get("dor_toracica", {})
    # o item válido sobreviveu
    assert motor.aconselhamento["dor_toracica"]["vermelho"]["itens"][0]["texto"] == "válido"
