"""Testes das novidades da v0.12.1: encaminhamento direto ao hospital.

O que mudou e porquê: na reunião de acompanhamento, o SESARAM indicou
que todos os vermelhos e laranjas, e (por agora) todos os amarelos,
devem ser encaminhados diretamente para o Hospital Dr. Nélio Mendonça,
em vez da urgência aberta mais próxima. A v0.12.1:

  1. cria a política em app/data/encaminhamento.json — editável pela
     equipa clínica sem tocar em código (retirar uma cor da lista repõe
     o comportamento por proximidade para essa cor);
  2. deixa pronta a válvula para o futuro: um desfecho AMARELO pode
     declarar "destino": "atendimento_urgente" no ficheiro de regras e
     esse desfecho volta a ir à urgência aberta mais próxima (com a
     ordenação por tempo de estrada e a regra de troca por espera);
  3. valida o campo no arranque (valores permitidos; só em amarelos);
  4. mantém a regra da ilha: no Porto Santo nada atravessa o mar;
  5. recua em segurança para a proximidade se o hospital configurado
     não existir nos dados ou não tiver urgência aberta.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import versao
from app.core import espera, fluxogramas, routing
from app.core.triage_engine import TriageEngine
from app.main import app

RAIZ = Path(__file__).resolve().parent.parent

cliente = TestClient(app)

SEGUNDA_10H = datetime(2026, 6, 29, 10, 0)
FUNCHAL = (32.6496, -16.9086)
CALHETA = (32.7176, -17.1743)
MACHICO = (32.7167, -16.7676)
PORTO_MONIZ = (32.8668, -17.1666)
CURRAL = (32.7203, -16.9704)
PORTO_SANTO = (33.06, -16.35)


@pytest.fixture
def sem_esperas(monkeypatch):
    """Isola os testes do cache de espera que outros testes escrevem."""
    monkeypatch.setattr(
        espera, "do_cache",
        lambda: {"disponivel": False, "desatualizado": False, "obtido_em": None},
    )


# --------------------------------------------------------------------- #
# Versão e configuração                                                   #
# --------------------------------------------------------------------- #

def test_versao_e_pelo_menos_0_12_1():
    partes = tuple(int(p) for p in versao.VERSAO.split("."))
    assert partes >= (0, 12, 1)


def test_ficheiro_de_politica_existe_e_e_valido():
    caminho = RAIZ / "app" / "data" / "encaminhamento.json"
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["hospital_id"] == "hnm"
    cores_validas = {"vermelho", "laranja", "amarelo", "verde", "azul"}
    assert set(dados["direto_para_hospital"]) <= cores_validas
    # A indicação atual do SESARAM: as três cores mais graves.
    assert set(dados["direto_para_hospital"]) == {"vermelho", "laranja", "amarelo"}


def test_politica_carregada_aponta_para_unidade_real():
    from app.core import unidades

    assert routing.POLITICA["hospital_id"] == "hnm"
    hospital = unidades.por_id(routing.POLITICA["hospital_id"])
    assert hospital is not None
    assert "urgencia_polivalente" in hospital["servicos"]


# --------------------------------------------------------------------- #
# A política em ação: laranja e amarelo vão diretos ao hospital           #
# --------------------------------------------------------------------- #

def test_laranja_e_amarelo_vao_ao_hnm_de_qualquer_concelho(sem_esperas):
    """O cerne da v0.12.1: mesmo com atendimento urgente aberto ao lado
    (Calheta, Machico, Porto Moniz), o encaminhamento é o hospital."""
    for cor in ("laranja", "amarelo"):
        for local in (CALHETA, MACHICO, PORTO_MONIZ, FUNCHAL):
            saida = routing.decidir_encaminhamento(cor, *local, quando=SEGUNDA_10H)
            assert saida["acao"] == "ir_unidade", (cor, local)
            assert saida["unidade"]["id"] == "hnm", (cor, local)
            assert saida["alternativas"] == [], (cor, local)
            assert saida["reordenado_por_espera"] is False, (cor, local)


def test_resposta_indica_a_politica_aplicada(sem_esperas):
    saida = routing.decidir_encaminhamento("amarelo", *MACHICO, quando=SEGUNDA_10H)
    assert saida["politica"] == {
        "destino": "hospital",
        "fonte": "configuracao",
        "aplicada": True,
    }


def test_mensagem_explica_o_hospital_direto_nas_duas_linguas(sem_esperas):
    saida = routing.decidir_encaminhamento("laranja", *CALHETA, quando=SEGUNDA_10H)
    assert "Nélio Mendonça" in saida["mensagem"]
    assert "diretamente" in saida["mensagem"]
    assert "min de carro" in saida["mensagem"]
    assert "directly" in saida["mensagem_en"]
    assert "orange" in saida["mensagem_en"]
    for texto in (saida["mensagem"], saida["mensagem_en"]):
        assert "\u2014" not in texto and "\u2013" not in texto  # sem travessões


def test_vermelho_mostra_o_hospital_como_referencia(sem_esperas):
    """No vermelho a ação continua a ser ligar 112; a unidade abaixo é o
    hospital de referência (é para lá que a emergência transporta)."""
    saida = routing.decidir_encaminhamento("vermelho", *CALHETA, quando=SEGUNDA_10H)
    assert saida["acao"] == "ligar_112"
    assert saida["unidade"]["id"] == "hnm"
    assert "112" in saida["mensagem"]
    assert "hospital de referência" in saida["mensagem"]
    assert saida["politica"]["aplicada"] is True


def test_hospital_mostra_espera_da_cor_do_utente(monkeypatch):
    """A coluna de espera certa (a da cor) continua a acompanhar o
    encaminhamento direto — era um dos ganhos da v0.8 e mantém-se."""
    monkeypatch.setattr(espera, "do_cache", lambda: {
        "disponivel": True, "desatualizado": False,
        "obtido_em": "2026-06-29T10:00:00",
        "unidades": {
            "hnm": {
                "tipo_dados": "por_cor",
                "por_cor": {"amarelo": {"em_espera": 5, "tempo_medio_min": 55, "atendidos": 9}},
                "geral": {"em_espera": 20, "tempo_medio_min": 90, "atendidos": 40},
                "fonte": "hospital",
                "atualizado_no_site": "2026-06-29 10:00",
            },
        },
    })
    saida = routing.decidir_encaminhamento("amarelo", *FUNCHAL, quando=SEGUNDA_10H)
    te = saida["unidade"]["tempo_espera"]
    assert te["minutos"] == 55 and te["ambito"] == "cor"


# --------------------------------------------------------------------- #
# Regra da ilha: o Porto Santo não muda                                   #
# --------------------------------------------------------------------- #

def test_porto_santo_mantem_a_regra_da_ilha(sem_esperas):
    for cor in ("vermelho", "laranja", "amarelo"):
        saida = routing.decidir_encaminhamento(cor, *PORTO_SANTO, quando=SEGUNDA_10H)
        assert saida["unidade"]["id"] == "cs_porto_santo", cor
        assert saida["politica"]["aplicada"] is False, cor


# --------------------------------------------------------------------- #
# A válvula: desfechos amarelos com "destino": "atendimento_urgente"      #
# --------------------------------------------------------------------- #

def test_excecao_amarela_volta_a_urgencia_mais_proxima(sem_esperas):
    saida = routing.decidir_encaminhamento(
        "amarelo", *MACHICO, quando=SEGUNDA_10H, destino="atendimento_urgente"
    )
    assert saida["unidade"]["id"] == "cs_machico"
    assert saida["unidade"]["aberta_agora"] is True
    assert saida["politica"] == {
        "destino": "atendimento_urgente",
        "fonte": "fluxograma",
        "aplicada": False,
    }


def test_excecao_amarela_mantem_a_ordenacao_por_estrada(sem_esperas):
    """A rationale da v0.11 sobrevive na válvula: do Curral das Freiras,
    o hospital vem primeiro POR TEMPO DE ESTRADA (o caminho para Câmara
    de Lobos passa-lhe à porta), com o CS de CML nas alternativas."""
    saida = routing.decidir_encaminhamento(
        "amarelo", *CURRAL, quando=SEGUNDA_10H, destino="atendimento_urgente"
    )
    assert saida["unidade"]["id"] == "hnm"
    assert "cs_camara_lobos" in [a["id"] for a in saida["alternativas"]]


def test_destino_hospital_explicito_no_amarelo(sem_esperas):
    saida = routing.decidir_encaminhamento(
        "amarelo", *MACHICO, quando=SEGUNDA_10H, destino="hospital"
    )
    assert saida["unidade"]["id"] == "hnm"
    assert saida["politica"]["fonte"] == "fluxograma"
    assert saida["politica"]["aplicada"] is True


def test_destino_e_ignorado_fora_do_amarelo(sem_esperas):
    saida = routing.decidir_encaminhamento(
        "laranja", *MACHICO, quando=SEGUNDA_10H, destino="atendimento_urgente"
    )
    assert saida["unidade"]["id"] == "hnm"
    assert saida["politica"]["fonte"] == "configuracao"


def test_recuo_seguro_se_o_hospital_da_politica_nao_tem_urgencia(sem_esperas, monkeypatch):
    """Se alguém trocar o hospital_id por uma unidade sem urgência
    (os Marmeleiros não têm serviços nos dados), ninguém é mandado para
    uma porta fechada: recua-se para a urgência aberta mais próxima."""
    monkeypatch.setitem(routing.POLITICA, "hospital_id", "marmeleiros")
    saida = routing.decidir_encaminhamento("laranja", *MACHICO, quando=SEGUNDA_10H)
    assert saida["unidade"]["id"] != "marmeleiros"
    assert saida["unidade"]["aberta_agora"] is True
    assert saida["politica"]["aplicada"] is False
    assert saida["politica"]["recuo"] is True


def test_cor_retirada_da_politica_volta_a_proximidade(sem_esperas, monkeypatch):
    """O caminho previsto para "certos amarelos" globalmente: retirar
    'amarelo' de encaminhamento.json repõe a proximidade sem mexer em
    código."""
    monkeypatch.setitem(
        routing.POLITICA, "direto_para_hospital", ["vermelho", "laranja"]
    )
    saida = routing.decidir_encaminhamento("amarelo", *MACHICO, quando=SEGUNDA_10H)
    assert saida["unidade"]["id"] == "cs_machico"
    assert saida["politica"]["fonte"] == "predefinicao"


# --------------------------------------------------------------------- #
# Validação do campo "destino" no arranque                                #
# --------------------------------------------------------------------- #

RED_FLAGS_MINIMO = {
    "id": "red_flags",
    "sinais": [{"id": "rf1", "texto": "Sinal de emergência"}],
}


def _escrever(pasta: Path, nome: str, dados: dict) -> None:
    (pasta / nome).write_text(
        json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def _fluxo(perguntas: list[dict]) -> dict:
    return {"id": "teste", "nome": "Teste", "descricao": "t", "perguntas": perguntas}


def test_validador_aceita_destino_em_amarelo(tmp_path):
    _escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    _escrever(tmp_path, "teste.json", _fluxo([
        {"id": "q1", "texto": "?",
         "sim": {"resultado": {"cor": "amarelo", "destino": "atendimento_urgente"}},
         "nao": {"resultado": {"cor": "verde"}}},
    ]))
    motor = TriageEngine(tmp_path)
    saida = motor.avaliar("teste", {"q1": "sim"})
    # O motor passa o campo tal e qual ao resultado, para a API e o
    # frontend o reenviarem ao encaminhamento.
    assert saida["resultado"]["destino"] == "atendimento_urgente"


def test_validador_rejeita_destino_invalido(tmp_path):
    _escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    _escrever(tmp_path, "teste.json", _fluxo([
        {"id": "q1", "texto": "?",
         "sim": {"resultado": {"cor": "amarelo", "destino": "hospitall"}},
         "nao": {"resultado": {"cor": "verde"}}},
    ]))
    with pytest.raises(RuntimeError, match="destino inválido"):
        TriageEngine(tmp_path)


def test_validador_rejeita_destino_fora_do_amarelo(tmp_path):
    _escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    _escrever(tmp_path, "teste.json", _fluxo([
        {"id": "q1", "texto": "?",
         "sim": {"resultado": {"cor": "verde", "destino": "atendimento_urgente"}},
         "nao": {"resultado": {"cor": "azul"}}},
    ]))
    with pytest.raises(RuntimeError, match="amarelos"):
        TriageEngine(tmp_path)


def test_regras_reais_continuam_a_validar():
    """As regras em produção não usam (ainda) o campo destino e têm de
    continuar a carregar sem erros."""
    motor = TriageEngine()
    assert motor.fluxos


# --------------------------------------------------------------------- #
# API: o destino viaja do desfecho até ao encaminhamento                  #
# --------------------------------------------------------------------- #

def test_api_encaminhamento_aceita_destino(sem_esperas):
    resposta = cliente.post("/api/encaminhamento", json={
        "cor": "amarelo", "lat": MACHICO[0], "lng": MACHICO[1],
        "destino": "atendimento_urgente",
        "quando": SEGUNDA_10H.isoformat(),
    })
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["unidade"]["id"] == "cs_machico"
    assert corpo["politica"]["fonte"] == "fluxograma"


def test_api_encaminhamento_rejeita_destino_desconhecido():
    resposta = cliente.post("/api/encaminhamento", json={
        "cor": "amarelo", "lat": MACHICO[0], "lng": MACHICO[1],
        "destino": "farmacia",
    })
    assert resposta.status_code == 422


def test_api_encaminhamento_sem_destino_vai_ao_hospital(sem_esperas):
    resposta = cliente.post("/api/encaminhamento", json={
        "cor": "amarelo", "lat": MACHICO[0], "lng": MACHICO[1],
        "quando": SEGUNDA_10H.isoformat(),
    })
    assert resposta.status_code == 200
    assert resposta.json()["unidade"]["id"] == "hnm"


def test_integracao_propaga_o_destino_do_desfecho(sem_esperas, tmp_path, monkeypatch):
    """Ponta a ponta: um fluxo cujo desfecho amarelo declara o destino
    faz o /api/integracao/triagem devolver o encaminhamento da exceção."""
    from app.api import routes

    _escrever(tmp_path, "red_flags.json", RED_FLAGS_MINIMO)
    _escrever(tmp_path, "teste.json", _fluxo([
        {"id": "q1", "texto": "?",
         "sim": {"resultado": {"cor": "amarelo", "destino": "atendimento_urgente",
                               "motivo": "m"}},
         "nao": {"resultado": {"cor": "verde"}}},
    ]))
    monkeypatch.setattr(routes, "engine", TriageEngine(tmp_path))
    resposta = cliente.post("/api/integracao/triagem", json={
        "queixa": "teste", "respostas": {"q1": "sim"},
        "lat": MACHICO[0], "lng": MACHICO[1],
    })
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["resultado"]["destino"] == "atendimento_urgente"
    assert corpo["encaminhamento"]["unidade"]["id"] == "cs_machico"
    assert corpo["encaminhamento"]["politica"]["fonte"] == "fluxograma"


# --------------------------------------------------------------------- #
# Fluxogramas: a exceção fica visível na árvore                           #
# --------------------------------------------------------------------- #

def test_fluxograma_marca_desfechos_com_excecao():
    fluxo = _fluxo([
        {"id": "q1", "texto": "Pergunta?", "texto_en": "Question?",
         "sim": {"resultado": {"cor": "amarelo", "destino": "atendimento_urgente"}},
         "nao": {"resultado": {"cor": "verde"}}},
    ])
    pt = fluxogramas.mermaid_do_fluxo(fluxo, "pt")
    en = fluxogramas.mermaid_do_fluxo(fluxo, "en")
    assert "pode ir ao atendimento urgente" in pt
    assert "may go to urgent care" in en


def test_fluxograma_sem_excecao_nao_ganha_marca():
    """Regressão: sem o campo destino, o desenho fica exatamente como
    dantes (os .mmd do repositório não podem mudar por esta feature)."""
    fluxo = _fluxo([
        {"id": "q1", "texto": "Pergunta?",
         "sim": {"resultado": {"cor": "amarelo"}},
         "nao": {"resultado": {"cor": "verde"}}},
    ])
    assert "atendimento urgente" not in fluxogramas.mermaid_do_fluxo(fluxo, "pt")


# --------------------------------------------------------------------- #
# Documentação                                                            #
# --------------------------------------------------------------------- #

def test_readmes_mostram_o_link_da_previsualizacao():
    """Pedido explícito da v0.12.1: o link completo da pré-visualização
    tem de estar nos READMEs, para qualquer pessoa o abrir."""
    for nome in ("README.md", "README.pt.md"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert "http://127.0.0.1:8000/fluxogramas" in texto, nome


def test_readmes_documentam_a_politica():
    for nome in ("README.md", "README.pt.md"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert "encaminhamento.json" in texto, nome
        assert "0.12.1" in texto, nome
