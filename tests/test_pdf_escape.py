"""Testes de robustez do PDF a texto hostil (v0.16.1).

O Paragraph do reportlab interpreta um mini-HTML. Antes desta versão,
qualquer texto do pedido com "<" ou "&" mal formados rebentava a geração
(500), e uma tag <img> fazia o servidor tentar abrir um ficheiro. A
correção (app/core/pdf_clinico.py::_esc) escapa TODO o texto vindo de
fora antes de o entregar ao reportlab; estes testes fixam esse
comportamento para sempre:

- nenhum destes pedidos pode voltar a dar 500;
- o texto hostil tem de aparecer LITERALMENTE no PDF (escapado, não
  interpretado nem engolido).
"""

from __future__ import annotations

import base64
import re
import zlib

import pytest
from fastapi.testclient import TestClient

from app.core.pdf_clinico import gerar_pdf
from app.main import app

cliente = TestClient(app)


def _texto_do_pdf(pdf: bytes) -> str:
    """Extrai o texto dos content streams (ASCII85 + Flate) do reportlab.

    O reportlab parte o texto em vários operadores Tj — "cuidado <b>agora"
    sai como (cuidado <) Tj (b) Tj (>) Tj (agora) Tj — por isso
    concatenam-se os fragmentos antes de procurar a substring.
    """
    fragmentos: list[str] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        dados = m.group(1).strip()
        try:
            dados = base64.a85decode(dados, adobe=True)
        except ValueError:
            pass
        try:
            dados = zlib.decompress(dados)
        except zlib.error:
            continue
        texto = dados.decode("latin-1", "replace")
        fragmentos.extend(re.findall(r"\((.*?)\)\s*Tj", texto))
    return "".join(fragmentos)


# Casos reais que antes davam 500 (ver CHANGELOG v0.16.1).
_HOSTIS = [
    pytest.param({"mensagem": "cuidado <b>agora"}, "cuidado <b>agora", id="tag-aberta-na-mensagem"),
    pytest.param(
        {"unidade": {"nome": "Centro <img src='x'/>", "morada": "Rua A"}},
        "Centro <img src='x'/>",
        id="tag-img-no-nome-da-unidade",
    ),
    pytest.param(
        {"queixa": "dor &#xZZ; toracica"}, "dor &#xZZ; toracica", id="entidade-xml-invalida"
    ),
    pytest.param({"mensagem": "a < b & c > d"}, "a < b & c > d", id="sinais-soltos"),
]


@pytest.mark.parametrize("payload,literal", _HOSTIS)
def test_pdf_nao_rebenta_com_texto_hostil(payload: dict, literal: str):
    r = cliente.post("/api/exportar_pdf", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


@pytest.mark.parametrize("payload,literal", _HOSTIS)
def test_pdf_mostra_o_texto_hostil_literalmente(payload: dict, literal: str):
    """Escapar não pode significar apagar: o utente tem de ler o que escreveu."""
    pdf = gerar_pdf(payload)
    assert literal in _texto_do_pdf(pdf)


def test_pdf_hostil_em_todos_os_campos_de_texto():
    """Um pedido com markup em TODOS os campos livres continua a dar PDF válido."""
    hostil = "<script>&'\"</para>"
    pdf = gerar_pdf(
        {
            "queixa": hostil,
            "mensagem": hostil,
            "classificacao": hostil,
            "tempo_alvo": hostil,
            "gerado_em": hostil,
            "cor": "amarelo",
            "cor_hex": hostil,  # cai no _cor_segura, não pode rebentar
            "unidade": {
                "nome": hostil,
                "morada": hostil,
                "telefone": hostil,
                "horarios": {hostil: hostil},
            },
            "autocuidado": {"alerta_titulo": hostil, "alerta": [hostil, hostil]},
            "contactos": {"emergencia": {"numero": hostil}, "sns24": {"numero": hostil}},
        }
    )
    assert pdf.startswith(b"%PDF")


def test_pdf_limpo_continua_igual():
    """Sanidade: com texto normal nada muda (o markup do módulo continua a funcionar)."""
    pdf = gerar_pdf(
        {
            "mensagem": "Dirija-se ao centro de saúde mais próximo.",
            "cor": "verde",
            "cor_hex": "#2E7D32",
            "classificacao": "Pouco urgente",
            "queixa": "dor de garganta",
        }
    )
    assert pdf.startswith(b"%PDF")
    assert "Dirija-se ao centro de sa" in _texto_do_pdf(pdf)
