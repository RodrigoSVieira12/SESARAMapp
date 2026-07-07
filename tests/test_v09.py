"""Testes das novidades da v0.9: endpoint de integração e exportação de PDF.

Cobrem o contrato que um sistema externo (ex.: uma plataforma clínica interna) vê:
- /api/integracao/triagem devolve 'pergunta' enquanto faltam respostas e
  'resultado' (+ encaminhamento quando há lat/lng) quando a cor é decidida;
- /api/exportar_pdf devolve um PDF válido (assinatura %PDF-);
- /api/exportar_pdf_base64 devolve o mesmo PDF em base64.
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.main import app

cliente = TestClient(app)


# --------------------------------------------------------------------- #
# /api/integracao/triagem                                                 #
# --------------------------------------------------------------------- #

def test_integracao_devolve_pergunta_quando_faltam_respostas():
    r = cliente.post("/api/integracao/triagem", json={"queixa": "febre", "respostas": {}})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["tipo"] == "pergunta"
    assert corpo["queixa"] == "febre"
    # tem de trazer uma pergunta para o chamador mostrar
    assert "pergunta" in corpo


def test_integracao_red_flag_da_vermelho_com_encaminhamento():
    r = cliente.post(
        "/api/integracao/triagem",
        json={"red_flags": ["inconsciencia"], "lat": 32.65, "lng": -16.91},
    )
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["tipo"] == "resultado"
    assert corpo["resultado"]["cor"] == "vermelho"
    # com lat/lng, o encaminhamento vem no mesmo pacote
    assert "encaminhamento" in corpo
    assert corpo["encaminhamento"]["acao"] == "ligar_112"


def test_integracao_sem_localizacao_nao_traz_encaminhamento():
    r = cliente.post("/api/integracao/triagem", json={"red_flags": ["inconsciencia"]})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["tipo"] == "resultado"
    assert "encaminhamento" not in corpo


def test_integracao_sem_queixa_nem_red_flag_e_422():
    r = cliente.post("/api/integracao/triagem", json={"respostas": {}})
    assert r.status_code == 422


# --------------------------------------------------------------------- #
# /api/exportar_pdf e /api/exportar_pdf_base64                             #
# --------------------------------------------------------------------- #

_PAYLOAD_PDF = {
    "cor": "verde",
    "classificacao": "Pouco urgente",
    "cor_hex": "#2E7D32",
    "tempo_alvo": "Observação em cerca de 120 minutos",
    "queixa": "Febre",
    "respostas": [{"texto": "Tem falta de ar?", "resposta": "nao"}],
    "mensagem": "Dirija-se ao centro de saúde.",
    "unidade": {
        "nome": "Centro de Saúde de Câmara de Lobos",
        "morada": "Rua X",
        "telefone": "291 009 250",
        "distancia_km": 2.1,
        "aberta_agora": True,
        "horarios": {"consulta_aberta": "Seg-Sex 08:00-20:00"},
    },
}


def test_exportar_pdf_devolve_pdf_valido():
    r = cliente.post("/api/exportar_pdf", json=_PAYLOAD_PDF)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    assert len(r.content) > 800  # não é um ficheiro vazio


def test_exportar_pdf_funciona_com_payload_minimo():
    # O gerador tem de ser tolerante: só a cor chega para produzir algo.
    r = cliente.post("/api/exportar_pdf", json={"cor": "azul"})
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"


def test_exportar_pdf_base64_decodifica_para_pdf():
    r = cliente.post("/api/exportar_pdf_base64", json=_PAYLOAD_PDF)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["tipo_mime"] == "application/pdf"
    conteudo = base64.b64decode(corpo["pdf_base64"])
    assert conteudo[:5] == b"%PDF-"
