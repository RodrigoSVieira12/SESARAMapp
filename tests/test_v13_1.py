"""Testes da v0.13.1: explicabilidade, logging e consolidação.

O que esta versão mudou (e o que se fixa aqui):
- todas as respostas do encaminhamento passam a trazer `motivos` — a
  lista bilingue "porquê esta recomendação?" (app/core/motivos.py);
- routing.py foi dividido: os textos vivem em routing_textos.py e os
  nomes antigos continuam acessíveis via routing (compatibilidade);
- a aplicação passou a usar logging (avisos no recuo do hospital e nas
  falhas de scraping), em vez de falhar em silêncio;
- a documentação foi reorganizada: histórico em CHANGELOG.md, decisões
  em docs/adr/, estado de validação em docs/VALIDATION.md, números de
  desempenho em docs/PERFORMANCE.md, e um CI em GitHub Actions.

Convenção herdada: pisos de versão, não igualdade (ver test_v11_3.py).
"""

from __future__ import annotations

import importlib.util
import logging
import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import versao
from app.core import espera, motivos, routing
from app.main import app

cliente = TestClient(app)

RAIZ = Path(__file__).resolve().parent.parent

FUNCHAL = (32.6496, -16.9086)
MACHICO = (32.7167, -16.7676)
PORTO_SANTO = (33.06, -16.35)

SEGUNDA_10H = datetime(2026, 6, 29, 10, 0)  # dia útil normal
SABADO_15H = datetime(2026, 7, 4, 15, 0)  # fim de semana

TRAVESSOES = ("\u2014", "\u2013")  # — e – (regra de copy da v0.11.2)


@pytest.fixture
def sem_esperas(monkeypatch):
    """Isola os testes do cache de espera que outros testes escrevem."""
    monkeypatch.setattr(
        espera,
        "do_cache",
        lambda: {"disponivel": False, "desatualizado": False, "unidades": {}, "obtido_em": None},
    )


# --------------------------------------------------------------------- #
# Versão                                                                  #
# --------------------------------------------------------------------- #


def test_versao_no_minimo_0_13_1():
    partes = tuple(int(x) for x in versao.VERSAO.split("."))
    assert partes >= (0, 13, 1)


# --------------------------------------------------------------------- #
# Explicabilidade: todos os ramos devolvem motivos                        #
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("cor", ["vermelho", "laranja", "amarelo", "verde", "azul"])
def test_todas_as_cores_tem_motivos_bilingues(sem_esperas, cor):
    saida = routing.decidir_encaminhamento(cor, *FUNCHAL, quando=SEGUNDA_10H)
    lista = saida["motivos"]
    assert isinstance(lista, list) and lista, f"{cor}: motivos vazios"
    # O primeiro motivo é sempre a cor estimada.
    assert lista[0]["tipo"] == "cor"
    for m in lista:
        assert m["tipo"], m
        assert isinstance(m["texto"], str) and m["texto"].strip()
        assert isinstance(m["texto_en"], str) and m["texto_en"].strip()
        # A regra de copy da casa aplica-se também aos motivos.
        for t in TRAVESSOES:
            assert t not in m["texto"], m["texto"]
            assert t not in m["texto_en"], m["texto_en"]


def test_hospital_direto_explica_a_politica(sem_esperas):
    saida = routing.decidir_encaminhamento("laranja", *FUNCHAL, quando=SEGUNDA_10H)
    tipos = [m["tipo"] for m in saida["motivos"]]
    assert "politica" in tipos
    assert "aberta" in tipos
    texto_politica = next(m["texto"] for m in saida["motivos"] if m["tipo"] == "politica")
    assert "hospital de referência" in texto_politica


def test_amarelo_com_destino_do_fluxograma_explica_a_excecao(sem_esperas):
    saida = routing.decidir_encaminhamento(
        "amarelo", *FUNCHAL, quando=SEGUNDA_10H, destino="atendimento_urgente"
    )
    assert saida["politica"]["fonte"] == "fluxograma"
    texto_politica = next(m["texto"] for m in saida["motivos"] if m["tipo"] == "politica")
    assert "fluxograma" in texto_politica


def test_verde_ao_sabado_explica_o_dia(sem_esperas):
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=SABADO_15H)
    motivo_dia = next(m for m in saida["motivos"] if m["tipo"] == "dia")
    assert "sábado" in motivo_dia["texto"].lower()
    assert "saturday" in motivo_dia["texto_en"].lower()


def test_porto_santo_inclui_a_regra_da_ilha(sem_esperas):
    saida = routing.decidir_encaminhamento("laranja", *PORTO_SANTO, quando=SEGUNDA_10H)
    tipos = [m["tipo"] for m in saida["motivos"]]
    assert "ilha" in tipos


def test_troca_por_espera_gera_motivo(sem_esperas, monkeypatch):
    """Quando a regra experimental troca a unidade, o motivo aparece —
    com os mesmos números da mensagem (viagem + espera dos dois lados)."""

    def escolha_falsa(abertas):
        principal = abertas[0]
        preterida = {"nome": "Unidade Perto", "distancia_km": 2.0}
        troca = {
            "preterida": preterida,
            "total_preterida_min": 120,
            "total_escolhida_min": 30,
        }
        return principal, abertas[1:], troca

    monkeypatch.setattr(espera, "escolher_principal", escolha_falsa)
    saida = routing.decidir_encaminhamento(
        "amarelo", *FUNCHAL, quando=SEGUNDA_10H, destino="atendimento_urgente"
    )
    assert saida["reordenado_por_espera"] is True
    motivo_troca = next(m for m in saida["motivos"] if m["tipo"] == "troca")
    assert "120" in motivo_troca["texto"] and "30" in motivo_troca["texto"]
    assert "experimental" in motivo_troca["texto"]


def test_recuo_do_hospital_gera_motivo_e_aviso_no_log(sem_esperas, monkeypatch, caplog):
    """Hospital configurado sem urgência nos dados: além do recuo seguro
    (v0.12.1), fica um WARNING no log e o motivo explica a troca."""
    monkeypatch.setitem(routing.POLITICA, "hospital_id", "marmeleiros")
    with caplog.at_level(logging.WARNING, logger="app.core.routing"):
        saida = routing.decidir_encaminhamento("laranja", *MACHICO, quando=SEGUNDA_10H)
    assert saida["politica"].get("recuo") is True
    tipos = [m["tipo"] for m in saida["motivos"]]
    assert "recuo" in tipos
    assert any("recuo para proximidade" in r.message for r in caplog.records)
    # Privacidade: o aviso não pode conter a localização do utente.
    for registo in caplog.records:
        assert str(MACHICO[0]) not in registo.getMessage()
        assert str(MACHICO[1]) not in registo.getMessage()


def test_compilar_ignora_nones_e_duplicados():
    a = {"tipo": "x", "texto": "a", "texto_en": "a"}
    assert motivos.compilar(None, a, None, a) == [a]


# --------------------------------------------------------------------- #
# API                                                                     #
# --------------------------------------------------------------------- #


def test_api_encaminhamento_devolve_motivos(sem_esperas):
    corpo = {"cor": "amarelo", "lat": FUNCHAL[0], "lng": FUNCHAL[1]}
    resposta = cliente.post("/api/encaminhamento", json=corpo)
    assert resposta.status_code == 200
    lista = resposta.json()["motivos"]
    assert lista and lista[0]["tipo"] == "cor"
    assert all("texto" in m and "texto_en" in m for m in lista)


# --------------------------------------------------------------------- #
# Divisão do routing (compatibilidade dos nomes)                          #
# --------------------------------------------------------------------- #


def test_textos_do_routing_continuam_acessiveis():
    """A divisão em routing_textos.py não pode partir quem importava os
    ajudantes a partir de routing (testes antigos, scripts)."""
    assert routing._horario_en("Dias úteis, 08:00-20:00") == "Weekdays, 08:00-20:00"
    assert routing._contexto_do_dia(SABADO_15H) == "É sábado e "
    assert routing.NOTA_TRANSFERENCIA_PORTO_SANTO.startswith(" Em situações")
    from app.core import routing_textos

    assert routing._horario_en is routing_textos._horario_en


# --------------------------------------------------------------------- #
# Benchmark de desempenho                                                 #
# --------------------------------------------------------------------- #


def _carregar_benchmark():
    caminho = RAIZ / "scripts" / "benchmark_desempenho.py"
    spec = importlib.util.spec_from_file_location("benchmark_desempenho", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_benchmark_mede_os_endpoints_principais():
    bench = _carregar_benchmark()
    resultados = bench.medir(iteracoes=3, aquecimento=1)
    rotas = {r["rota"] for r in resultados}
    assert any(r.startswith("POST /api/triagem") for r in rotas)
    assert any(r.startswith("POST /api/encaminhamento") for r in rotas)
    for r in resultados:
        assert r["erros"] == 0
        assert r["media_ms"] > 0
        assert r["p95_ms"] >= r["mediana_ms"] > 0


# --------------------------------------------------------------------- #
# Consolidação: documentação e CI com a forma certa                       #
# --------------------------------------------------------------------- #


def test_changelog_existe_e_tem_a_versao_corrente():
    for nome in ("CHANGELOG.md", "CHANGELOG.pt.md"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert versao.VERSAO in texto, f"{nome} sem a versão {versao.VERSAO}"


def test_readme_ficou_curto_e_sem_historico():
    """O histórico de versões saiu dos READMEs (vive no CHANGELOG); o
    README aponta para lá. Guarda-costas contra o regresso do 'manual'."""
    for nome in ("README.md", "README.pt.md"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert not re.search(
            r"^## (New in|Novidades) v", texto, re.MULTILINE
        ), f"{nome} voltou a ter histórico de versões"
        assert "CHANGELOG" in texto, f"{nome} não aponta para o CHANGELOG"
        assert len(texto.splitlines()) < 400, f"{nome} voltou a crescer demasiado"


def test_adrs_existem_e_estao_indexados():
    pasta = RAIZ / "docs" / "adr"
    numerados = sorted(p.name for p in pasta.glob("0*.md"))
    assert len(numerados) >= 8, "esperavam-se pelo menos 8 ADRs"
    indice = (pasta / "README.md").read_text(encoding="utf-8")
    for nome in numerados:
        assert nome in indice, f"ADR {nome} fora do índice docs/adr/README.md"


def test_documentos_de_validacao_e_desempenho_existem():
    docs = RAIZ / "docs"
    assert (docs / "VALIDATION.md").exists()
    assert (docs / "VALIDACAO.md").exists()
    texto = (docs / "PERFORMANCE.md").read_text(encoding="utf-8")
    assert "/api/triagem" in texto and "p95" in texto


def test_ci_do_github_corre_os_testes_e_valida_os_dados():
    ci = (RAIZ / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pytest" in ci
    assert "validar_dados.py" in ci
    assert "auditar_traducoes.py" in ci
