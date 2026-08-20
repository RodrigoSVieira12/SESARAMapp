"""Testes da v0.16.2 — robustez: erros legíveis, limites, fontes, contrato.

Cobrem as cinco frentes desta versão (segunda ronda da revisão externa
"engenheiro sénior exigente"; a primeira deu a v0.16.1):

  1. ERROS DE DADOS LEGÍVEIS: um erro de SINTAXE num JSON de regras (o
     engano mais provável de quem edita à mão) passa a dar um RuntimeError
     com o nome do ficheiro — no arranque e em /api/fluxogramas, que
     antes rebentava com um 500 apesar de a docstring prometer o campo
     "erro". O mesmo para raiz não-objeto e fluxo sem "id".
  2. LIMITES DE SANIDADE (anti-abuso): corpo do pedido com teto (413),
     campos de texto/lista com máximos folgados nos schemas (422), e o
     gerador de PDF apara o que desenha — o pedido artesanal que custava
     ~33 s de CPU passa a custar milissegundos. Pedidos legítimos
     continuam intocados (verificado aqui).
  3. FONTES EMBUTIDAS: sem Google Fonts em runtime — a Public Sans vive
     em static/vendor, como o resto dos vendors (offline + RGPD).
  4. CONTRATO DA API: os três endpoints principais declaram
     response_model (documentado em /docs via openapi.json) SEM mudar o
     formato no fio: as chaves que o routing não põe continuam ausentes
     (exclude_unset), fixado aqui nos dois sentidos.
  5. CI E LICENÇA: a matriz testa 3.11 e 3.12 (o que o README promete) e
     existe LICENSE na raiz.

A lógica de triagem (prioridades e cores) NÃO muda nesta versão.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import pdf_clinico
from app.core.triage_engine import PASTA_REGRAS, TriageEngine
from app.main import CORPO_MAXIMO_BYTES, app

cliente = TestClient(app)

RAIZ = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ #
# 1. Erros de dados legíveis (motor e /api/fluxogramas)               #
# ------------------------------------------------------------------ #


def _pasta_minima_de_regras(tmp_path: Path) -> Path:
    """Uma pasta de regras válida e mínima: red_flags + um fluxo real."""
    shutil.copy(PASTA_REGRAS / "red_flags.json", tmp_path / "red_flags.json")
    shutil.copy(PASTA_REGRAS / "dor_toracica.json", tmp_path / "dor_toracica.json")
    return tmp_path


def _motor(pasta: Path) -> TriageEngine:
    """Motor sobre a pasta dada, sem aconselhamento nem reescritas."""
    return TriageEngine(
        pasta_regras=pasta,
        ficheiro_aconselhamento=pasta / "sem_aconselhamento.json",
        ficheiro_perguntas_utente=pasta / "sem_perguntas.json",
    )


def test_json_com_erro_de_sintaxe_diz_o_ficheiro(tmp_path):
    pasta = _pasta_minima_de_regras(tmp_path)
    (pasta / "corrompido.json").write_text('{ "id": "x", isto nao e json', encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"corrompido\.json: JSON ilegível"):
        _motor(pasta)


def test_json_com_raiz_nao_objeto_diz_o_ficheiro(tmp_path):
    pasta = _pasta_minima_de_regras(tmp_path)
    (pasta / "lista.json").write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"lista\.json: formato inesperado"):
        _motor(pasta)


def test_fluxo_sem_id_diz_o_ficheiro(tmp_path):
    pasta = _pasta_minima_de_regras(tmp_path)
    fluxo = {
        "nome": "Sem id",
        "perguntas": [{"id": "q1", "texto": "t", "prioridade": "P4", "cor": "verde"}],
    }
    (pasta / "sem_id.json").write_text(json.dumps(fluxo), encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"sem_id\.json: fluxo sem 'id'"):
        _motor(pasta)


def test_fluxogramas_sobrevive_a_json_invalido_no_disco():
    """O caso reproduzido na revisão: um '{' a mais num ficheiro real e
    /api/fluxogramas devolvia 500 Internal Server Error — apesar de a
    docstring prometer a mensagem no campo "erro". Agora cumpre-a."""
    caminho = PASTA_REGRAS / "alergias.json"
    original = caminho.read_bytes()
    try:
        caminho.write_bytes(original + b"{")
        resposta = cliente.get("/api/fluxogramas")
        corpo = resposta.json()
        assert resposta.status_code == 200
        assert corpo["erro"] and "alergias.json" in corpo["erro"]
        assert corpo["fluxos"] == []
    finally:
        caminho.write_bytes(original)


# ------------------------------------------------------------------ #
# 2. Limites de sanidade nos pedidos                                  #
# ------------------------------------------------------------------ #


def test_limites_da_triagem_barram_o_abuso_e_deixam_o_legitimo():
    # Abuso: mais sinais do que existem no ecrã inteiro.
    resposta = cliente.post("/api/triagem", json={"red_flags": ["x"] * 21})
    assert resposta.status_code == 422
    # Abuso: id de queixa quilométrico.
    resposta = cliente.post("/api/triagem", json={"queixa": "a" * 81})
    assert resposta.status_code == 422
    # Abuso: mais respostas do que perguntas existem no maior fluxo.
    muitas = {f"q{i}": "sim" for i in range(201)}
    resposta = cliente.post("/api/triagem", json={"queixa": "dor_toracica", "respostas": muitas})
    assert resposta.status_code == 422
    # O pedido legítimo continua exatamente como antes.
    resposta = cliente.post("/api/triagem", json={"queixa": "dor_toracica"})
    assert resposta.status_code == 200
    assert resposta.json()["tipo"] == "pergunta"


def test_limites_do_pdf_barram_o_abuso_e_deixam_o_legitimo():
    resposta = cliente.post("/api/exportar_pdf", json={"alternativas": [{}] * 7})
    assert resposta.status_code == 422
    resposta = cliente.post("/api/exportar_pdf", json={"mensagem": "x" * 2001})
    assert resposta.status_code == 422
    resposta = cliente.post(
        "/api/exportar_pdf", json={"cor": "verde", "mensagem": "Vigie os sintomas em casa."}
    )
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF")


def test_corpo_gigante_e_rejeitado_cedo_com_413():
    corpo = b'{"mensagem": "' + b"a" * (CORPO_MAXIMO_BYTES + 1000) + b'"}'
    resposta = cliente.post(
        "/api/exportar_pdf",
        content=corpo,
        headers={"content-type": "application/json"},
    )
    assert resposta.status_code == 413
    assert "demasiado grande" in resposta.json()["detail"]


def test_gerador_de_pdf_apara_em_vez_de_custar_segundos():
    """O ataque medido na revisão (~33 s de CPU num pedido) tem de custar
    milissegundos mesmo chamando gerar_pdf diretamente, sem API."""
    hostil = {
        "cor": "verde",
        "lingua": "pt",
        "queixa": "q " * 40000,
        "mensagem": "palavra " * 60000,
        "unidade": {
            "nome": "N " * 5000,
            "morada": "m " * 5000,
            "telefone": "9" * 5000,
            "horarios": {f"servico_{i}": "h " * 4000 for i in range(60)},
        },
        "autocuidado": {"alerta_titulo": "t " * 5000, "alerta": ["a " * 4000] * 50},
    }
    inicio = time.monotonic()
    pdf = pdf_clinico.gerar_pdf(hostil)
    duracao = time.monotonic() - inicio
    assert pdf.startswith(b"%PDF")
    assert duracao < 5.0  # folga enorme para CI lento; real: ~0,03 s


def test_aparar_corta_no_teto_e_marca_o_corte():
    assert pdf_clinico._aparar("abc", 10) == "abc"
    aparado = pdf_clinico._aparar("a" * 100, 10)
    assert len(aparado) == 10
    assert aparado.endswith("…")


# ------------------------------------------------------------------ #
# 3. Fontes embutidas (sem Google Fonts em runtime)                   #
# ------------------------------------------------------------------ #


def test_fontes_locais_sem_google_fonts():
    html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in html
    assert "gstatic" not in html
    assert "/static/vendor/public-sans/public-sans.css" in html
    pasta = RAIZ / "static" / "vendor" / "public-sans"
    for peso in ("Regular", "SemiBold", "Bold", "ExtraBold"):
        ficheiro = pasta / f"PublicSans-{peso}.woff2"
        assert ficheiro.exists(), ficheiro
        assert ficheiro.read_bytes()[:4] == b"wOF2"  # assinatura woff2
    assert (pasta / "OFL.txt").exists()  # a licença viaja com a fonte


# ------------------------------------------------------------------ #
# 4. Contrato da API sem mudar o fio                                  #
# ------------------------------------------------------------------ #


def test_openapi_documenta_as_respostas_principais():
    corpo = cliente.get("/openapi.json").json()
    schemas = corpo["components"]["schemas"]
    for nome in ("TriagemResponse", "EncaminhamentoResponse", "IntegracaoTriagemResponse"):
        assert nome in schemas, nome
    ref = corpo["paths"]["/api/triagem"]["post"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"]
    assert ref.endswith("TriagemResponse")


def test_formato_no_fio_da_triagem_preservado():
    # Caminho da pergunta: as mesmas quatro chaves de sempre, nada de
    # "resultado": null a aparecer por causa do response_model.
    corpo = cliente.post("/api/triagem", json={"queixa": "dor_toracica", "respostas": {}}).json()
    assert set(corpo) == {"tipo", "queixa", "pergunta", "progresso"}
    # Caminho dos sinais de emergência: o resultado nunca teve
    # "prioridade" nem "aconselhamento" — e continua sem elas.
    sinal = cliente.get("/api/red-flags").json()[0]["id"]
    corpo = cliente.post("/api/triagem", json={"red_flags": [sinal]}).json()
    assert corpo["resultado"]["cor"] == "vermelho"
    assert "prioridade" not in corpo["resultado"]
    assert "aconselhamento" not in corpo["resultado"]


def test_formato_no_fio_do_encaminhamento_preservado():
    base = {"lat": 32.6499, "lng": -16.9084, "quando": "2026-07-15T10:00:00"}
    # O verde nunca traz "politica" (e traz sempre autocuidado)...
    verde = cliente.post("/api/encaminhamento", json={"cor": "verde", **base}).json()
    assert verde["cor"] == "verde"
    assert "politica" not in verde
    assert "autocuidado" in verde
    assert verde["motivos"]
    # ... e o amarelo traz — nos dois sentidos, o fio ficou igual.
    amarelo = cliente.post("/api/encaminhamento", json={"cor": "amarelo", **base}).json()
    assert amarelo["politica"]["destino"] == "hospital"


# ------------------------------------------------------------------ #
# 5. CI e licença                                                     #
# ------------------------------------------------------------------ #


def test_licenca_na_raiz_e_matriz_de_ci():
    licenca = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in licenca
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "matrix" in ci
    assert '"3.11"' in ci and '"3.12"' in ci
