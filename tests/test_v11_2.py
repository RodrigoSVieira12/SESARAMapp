"""Testes da v0.11.2: limpeza de texto (sem travessões) e chips de trajeto.

O que mudou (e o que estes testes prendem):
- Toda a interface deixou de usar travessões (— e –). Frases foram
  reescritas com vírgulas, dois pontos ou pontos finais. Isto cobre
  textos.js, autocuidado.json, unidades.json, routing (mensagens de
  troca) e os títulos do PDF clínico.
- Os rótulos do modo manual perderam o "(se souber)": a primeira opção
  de cada lista já é "Não sei", por isso o parêntesis era redundante.
- Horários em unidades.json passaram de "08:00-20:00" para
  "das 08:00 às 20:00" (só nos campos de TEXTO; os campos máquina
  "horas" ficam como estavam). O tradutor _horario_en acompanha.
- No cartão da unidade, a distância e o tempo de carro saíram da linha
  de texto corrido e passaram a dois chips distintos (chaves chip_* em
  textos.js, ícones inline em app.js).

Estes testes são sobretudo GUARDAS DE REGRESSÃO: se alguém voltar a
introduzir um travessão num texto visível, ou reintroduzir as chaves
antigas un_km/un_km_tempo, um teste rebenta e aponta o ficheiro.
"""

from __future__ import annotations

import inspect
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import versao
from app.core import espera, pdf_clinico, routing
from app.main import app

cliente = TestClient(app)

RAIZ = Path(__file__).resolve().parents[1]

# Segunda-feira, 10:00 — dia útil normal, determinístico (igual ao test_v11).
SEGUNDA_10H = datetime(2026, 6, 29, 10, 0)

TRAVESSOES = ("\u2014", "\u2013")  # — e –


@pytest.fixture()
def sem_esperas(monkeypatch):
    """Encaminhamento sem tempos de espera: isola o texto das mensagens
    (a regra de troca viagem+espera nunca dispara)."""
    monkeypatch.setattr(
        espera,
        "do_cache",
        lambda: {"disponivel": False, "desatualizado": False, "unidades": {}, "obtido_em": None},
    )


# --------------------------------------------------------------- helpers --

def _sem_comentarios_js(codigo: str) -> str:
    """Remove comentários /* ... */ e // ... de um ficheiro JS.

    Os travessões só são proibidos no que o UTENTE vê; comentários de
    programador podem usar a pontuação que quiserem.
    """
    codigo = re.sub(r"/\*.*?\*/", "", codigo, flags=re.DOTALL)
    codigo = re.sub(r"//[^\n]*", "", codigo)
    return codigo


def _strings_recursivas(valor):
    """Itera todas as strings de uma estrutura JSON (dicts/listas)."""
    if isinstance(valor, str):
        yield valor
    elif isinstance(valor, dict):
        for v in valor.values():
            yield from _strings_recursivas(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _strings_recursivas(v)


def _assert_sem_travessoes(texto: str, origem: str):
    for t in TRAVESSOES:
        assert t not in texto, f"travessão ({t!r}) em {origem}: {texto[:120]!r}"


# ---------------------------------------------------------------- versão --

def test_versao_0_11_2():
    assert versao.VERSAO == "0.11.2"


def test_api_saude_reporta_versao():
    resposta = cliente.get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.json()["versao"] == "0.11.2"


# ------------------------------------------------- textos.js sem dashes --

def test_textos_js_sem_travessoes():
    codigo = (RAIZ / "static" / "js" / "textos.js").read_text(encoding="utf-8")
    _assert_sem_travessoes(_sem_comentarios_js(codigo), "textos.js")


def test_textos_js_sem_se_souber():
    codigo = (RAIZ / "static" / "js" / "textos.js").read_text(encoding="utf-8")
    assert "(se souber)" not in codigo
    assert "(if you know" not in codigo


def test_chaves_chip_presentes_e_antigas_ausentes():
    textos = (RAIZ / "static" / "js" / "textos.js").read_text(encoding="utf-8")
    appjs = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    # Cada chave nova aparece 2x em textos.js (bloco pt e bloco en).
    for chave in ("chip_km", "chip_km_nota", "chip_viagem", "chip_viagem_nota"):
        assert textos.count(f"{chave}:") == 2, f"esperava {chave} em pt e en"
    # As chaves antigas desapareceram dos dois ficheiros.
    for antiga in ("un_km_tempo", "un_km:"):
        assert antiga not in textos, f"chave antiga {antiga} ainda em textos.js"
    assert "un_km" not in appjs, "app.js ainda usa a chave antiga un_km"
    # O cartão usa mesmo os chips novos.
    assert "unidade__trajeto" in appjs
    assert 't("chip_km"' in appjs and 't("chip_viagem"' in appjs


# ------------------------------------------------------ dados sem dashes --

def test_autocuidado_sem_travessoes():
    dados = json.loads((RAIZ / "app" / "data" / "autocuidado.json").read_text(encoding="utf-8"))
    for texto in _strings_recursivas(dados):
        _assert_sem_travessoes(texto, "autocuidado.json")


def test_unidades_textos_sem_faixas_com_hifen():
    """Nos campos de texto, 'HH:MM-HH:MM' deu lugar a 'das HH:MM às HH:MM'."""
    dados = json.loads((RAIZ / "app" / "data" / "unidades.json").read_text(encoding="utf-8"))
    padrao = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")

    def _textos(valor):
        if isinstance(valor, dict):
            for chave, v in valor.items():
                if chave == "texto" and isinstance(v, str):
                    yield v
                else:
                    yield from _textos(v)
        elif isinstance(valor, list):
            for v in valor:
                yield from _textos(v)

    encontrados = [t for t in _textos(dados) if padrao.search(t)]
    assert not encontrados, f"faixas HH:MM-HH:MM ainda em campos texto: {encontrados[:3]}"


# ---------------------------------------------------- routing e tradução --

def test_horario_en_traduz_das_as():
    assert routing._horario_en("Dias úteis, das 08:00 às 20:00") == "Weekdays, 08:00 to 20:00"


def test_routing_sem_travessoes_nas_mensagens():
    fonte = inspect.getsource(routing)
    assert "— por isso sugerimos" not in fonte
    assert "— so we suggest" not in fonte


@pytest.mark.parametrize("lingua", ["pt", "en"])
def test_encaminhamento_resposta_sem_travessoes(sem_esperas, monkeypatch, lingua):
    """Varre TODAS as strings de uma resposta real do encaminhamento."""
    monkeypatch.setattr(routing, "agora_na_madeira", lambda: SEGUNDA_10H)
    corpo = {"cor": "verde", "lat": 32.65, "lng": -16.91, "lingua": lingua}
    resposta = cliente.post("/api/encaminhamento", json=corpo)
    assert resposta.status_code == 200
    for texto in _strings_recursivas(resposta.json()):
        _assert_sem_travessoes(texto, f"/api/encaminhamento ({lingua})")


# -------------------------------------------------------------- PDF ------

def test_pdf_titulos_sem_travessoes():
    for lingua, textos in pdf_clinico._TXT.items():
        for texto in _strings_recursivas(textos):
            _assert_sem_travessoes(texto, f"pdf_clinico._TXT[{lingua}]")
