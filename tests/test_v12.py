"""Testes das novidades da v0.12: fluxogramas offline e pré-visualização viva.

O que mudou e porquê: até à v0.11 o documento de validação clínica ia
buscar a biblioteca de desenho (mermaid) ao CDN unpkg.com no momento de
abrir — quando o CDN falhava (esteve instável em 2025–2026), os
fluxogramas desapareciam EM SILÊNCIO, porque o arranque estava guardado
por um `if (window.mermaid)`. A v0.12:

  1. embute a biblioteca no próprio documento (autossuficiente, desenha
     offline, partilhável como um único ficheiro);
  2. mostra o erro por extenso no lugar de qualquer diagrama que não
     desenhe, em vez de esconder a falha;
  3. tira o unpkg também da app (leaflet e qrcode passam a
     static/vendor/ — sem CDN em runtime);
  4. acrescenta a pré-visualização viva /fluxogramas + GET
     /api/fluxogramas: as regras são relidas do disco a cada pedido,
     em PT ou EN, com erros de validação legíveis;
  5. os fluxogramas ganham inglês (campos *_en, com recuo seguro
     para PT).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import versao
from app.core import fluxogramas
from app.core.triage_engine import TriageEngine
from app.main import app

RAIZ = Path(__file__).resolve().parent.parent
VENDOR = RAIZ / "static" / "vendor"

motor = TriageEngine()
cliente = TestClient(app)


def _carregar_script(nome: str):
    caminho = RAIZ / "scripts" / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


gerador = _carregar_script("gerar_validacao_clinica")

RE_CLASSE_USADA = re.compile(r":::(\w+)")
RE_CLASSDEF = re.compile(r"classDef (\w+)")


# --------------------------------------------------------------------- #
# Versão e bibliotecas embutidas (static/vendor)                          #
# --------------------------------------------------------------------- #

def test_versao_e_0_12_ou_superior():
    partes = tuple(int(x) for x in versao.VERSAO.split("."))
    assert partes >= (0, 12, 0)


def test_vendor_mermaid_existe_e_e_autossuficiente():
    caminho = VENDOR / "mermaid.min.js"
    assert caminho.exists(), "static/vendor/mermaid.min.js em falta"
    conteudo = caminho.read_text(encoding="utf-8")
    # Um bundle completo (não um redireccionamento nem um pedaço ESM):
    assert len(conteudo) > 1_000_000
    # Fica disponível como window.mermaid quando carregado numa tag <script>:
    assert 'globalThis["mermaid"]' in conteudo
    # Sem "</script>" lá dentro, pode embutir-se tal e qual num documento:
    assert "</script>" not in conteudo
    # E é a versão que o gerador diz embutir (rodapé do documento):
    assert gerador.VERSAO_MERMAID in conteudo
    # A licença acompanha o ficheiro:
    assert (VENDOR / "mermaid.LICENSE.txt").exists()


def test_vendor_leaflet_e_qrcode_completos():
    for relativo in (
        "leaflet/leaflet.js",
        "leaflet/leaflet.css",
        "leaflet/images/marker-icon.png",
        "leaflet/images/marker-shadow.png",
        "leaflet/LICENSE.txt",
        "qrcode-generator/qrcode.js",
        "qrcode-generator/LICENSE.txt",
    ):
        assert (VENDOR / relativo).exists(), f"static/vendor/{relativo} em falta"


def test_index_html_ja_nao_depende_do_unpkg():
    indice = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
    assert "unpkg.com" not in indice
    assert "/static/vendor/leaflet/leaflet.css" in indice
    assert "/static/vendor/leaflet/leaflet.js" in indice
    assert "/static/vendor/qrcode-generator/qrcode.js" in indice


# --------------------------------------------------------------------- #
# Documento de validação clínica: autossuficiente e com falhas visíveis  #
# --------------------------------------------------------------------- #

def test_documento_embute_a_biblioteca_e_todos_os_fluxogramas():
    documento = gerador.construir_documento(motor)
    assert "unpkg.com" not in documento
    assert 'globalThis["mermaid"]' in documento  # a biblioteca vai lá dentro
    assert documento.count('<pre class="mermaid') == len(motor.fluxos)
    # A frase antiga sobre precisar de internet desapareceu:
    assert "precisa de ligação à internet" not in documento
    # O caminho de falha é visível (classe usada pelo arranque JS):
    assert "erro-diagrama" in documento
    assert "suppressErrors" in documento
    # E o rodapé identifica a versão embutida:
    assert f"mermaid v{gerador.VERSAO_MERMAID}" in documento


def test_documento_no_disco_esta_regenerado():
    """docs/validacao_clinica.html tem de refletir o gerador atual.

    Apanha o esquecimento clássico: mudar o gerador (ou as regras) e não
    voltar a correr `python scripts/gerar_validacao_clinica.py`.
    """
    caminho = RAIZ / "docs" / "validacao_clinica.html"
    assert caminho.exists()
    documento = caminho.read_text(encoding="utf-8")
    assert "unpkg.com" not in documento
    assert 'globalThis["mermaid"]' in documento
    assert documento.count('<pre class="mermaid') == len(motor.fluxos)


def test_mmd_no_disco_sao_os_das_regras_atuais():
    """Cada docs/fluxogramas/<id>.mmd corresponde às regras de hoje.

    (Normaliza fins de linha: os ficheiros podem ter sido escritos em
    Windows, onde o write_text traduz \\n para \\r\\n.)
    """
    pasta = RAIZ / "docs" / "fluxogramas"
    for fid, fluxo in motor.fluxos.items():
        caminho = pasta / f"{fid}.mmd"
        assert caminho.exists(), f"{caminho} em falta"
        no_disco = caminho.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        assert no_disco == fluxogramas.mermaid_do_fluxo(fluxo).strip(), fid


# --------------------------------------------------------------------- #
# Fluxogramas em inglês (com recuo seguro para PT)                        #
# --------------------------------------------------------------------- #

def test_mermaid_pt_continua_exatamente_como_antes():
    for fluxo in motor.fluxos.values():
        texto = fluxogramas.mermaid_do_fluxo(fluxo)
        assert texto.startswith("flowchart TD")
        assert "|Sim|" in texto and "|Não|" in texto
        assert 'inicio(["Início:' in texto
        assert "|Yes|" not in texto


def test_mermaid_en_traduz_rotulos_textos_e_nome():
    texto = fluxogramas.mermaid_do_fluxo(motor.fluxos["febre"], "en")
    assert texto.startswith("flowchart TD")
    assert 'inicio(["Start: Fever"])' in texto
    assert "|Yes|" in texto and "|No|" in texto
    assert "|Sim|" not in texto
    # O texto clínico vem do campo texto_en (normalizando as quebras
    # de linha <br/> que o _quebrar mete dentro das caixas):
    assert "Has the fever lasted more than 3 days?" in texto.replace("<br/>", " ")


def test_mermaid_en_recua_para_pt_quando_falta_traducao():
    fluxo = {
        "id": "x",
        "nome": "Teste",  # sem nome_en de propósito
        "perguntas": [
            {
                "id": "q1",
                "texto": "Só em português?",
                "sim": {"resultado": {"cor": "verde", "motivo": "só PT"}},
                "nao": {"resultado": {"cor": "azul"}},
            }
        ],
    }
    texto = fluxogramas.mermaid_do_fluxo(fluxo, "en")
    # Rótulos do desenho em inglês, conteúdo clínico recua para PT:
    assert "|Yes|" in texto and "Start: Teste" in texto
    assert "Só em português?" in texto and "só PT" in texto


def _fluxo_com_todas_as_cores() -> dict:
    cores = ["vermelho", "laranja", "amarelo", "verde", "azul"]
    perguntas = []
    for i, cor in enumerate(cores, start=1):
        ramo_nao = (
            {"proxima": f"q{i + 1}"}
            if i < len(cores)
            else {"resultado": {"cor": "azul", "motivo": "fim"}}
        )
        perguntas.append(
            {
                "id": f"q{i}",
                "texto": f"Pergunta {i}?",
                "sim": {"resultado": {"cor": cor, "motivo": f"motivo {i}"}},
                "nao": ramo_nao,
            }
        )
    return {"id": "sintetico", "nome": "Sintético", "nome_en": "Synthetic", "perguntas": perguntas}


def test_desfechos_usam_o_nome_da_cor_no_idioma_do_desenho():
    sintetico = _fluxo_com_todas_as_cores()
    pt = fluxogramas.mermaid_do_fluxo(sintetico)
    en = fluxogramas.mermaid_do_fluxo(sintetico, "en")
    for nome_pt in ("VERMELHO", "LARANJA", "AMARELO", "VERDE", "AZUL"):
        assert nome_pt in pt
    for nome_en in ("RED", "ORANGE", "YELLOW", "GREEN", "BLUE"):
        assert nome_en in en
    # As CLASSES de estilo ficam sempre em PT (são ids internos):
    assert "classDef vermelho" in en and ":::vermelho" in en


def test_todas_as_classes_usadas_tem_classdef_em_ambos_os_idiomas():
    for fluxo in motor.fluxos.values():
        for idioma in ("pt", "en"):
            texto = fluxogramas.mermaid_do_fluxo(fluxo, idioma)
            usadas = set(RE_CLASSE_USADA.findall(texto))
            definidas = set(RE_CLASSDEF.findall(texto))
            assert usadas <= definidas, (fluxo["id"], idioma, usadas - definidas)


# --------------------------------------------------------------------- #
# API e página da pré-visualização viva                                   #
# --------------------------------------------------------------------- #

def test_api_fluxogramas_devolve_todos_os_fluxos():
    dados = cliente.get("/api/fluxogramas").json()
    assert dados["erro"] is None
    assert {f["id"] for f in dados["fluxos"]} == set(motor.fluxos)
    for f in dados["fluxos"]:
        assert f["mermaid"].startswith("flowchart TD")


def test_api_fluxogramas_em_ingles():
    dados = cliente.get("/api/fluxogramas?idioma=en").json()
    por_id = {f["id"]: f for f in dados["fluxos"]}
    assert por_id["febre"]["nome"] == "Fever"
    assert "|Yes|" in por_id["febre"]["mermaid"]


def test_api_fluxogramas_valida_o_idioma():
    assert cliente.get("/api/fluxogramas?idioma=fr").status_code == 422


def test_api_fluxogramas_rele_o_disco_a_cada_pedido(monkeypatch):
    from app.api import routes

    chamadas = {"n": 0}
    original = routes.TriageEngine

    def fabrica(*args, **kwargs):
        chamadas["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(routes, "TriageEngine", fabrica)
    cliente.get("/api/fluxogramas")
    cliente.get("/api/fluxogramas")
    assert chamadas["n"] == 2


def test_api_fluxogramas_erro_de_validacao_legivel(monkeypatch):
    from app.api import routes

    def rebenta(*args, **kwargs):
        raise RuntimeError("febre.json: ids de pergunta repetidos")

    monkeypatch.setattr(routes, "TriageEngine", rebenta)
    dados = cliente.get("/api/fluxogramas").json()
    assert dados["erro"] == "febre.json: ids de pergunta repetidos"
    assert dados["fluxos"] == []


def test_pagina_fluxogramas_servida_e_ligada_ao_vendor():
    resposta = cliente.get("/fluxogramas")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    corpo = resposta.text
    assert "/static/vendor/mermaid.min.js" in corpo
    assert "/api/fluxogramas" in corpo
    assert "unpkg.com" not in corpo


def test_vendor_mermaid_servido_pela_app():
    resposta = cliente.get("/static/vendor/mermaid.min.js")
    assert resposta.status_code == 200
