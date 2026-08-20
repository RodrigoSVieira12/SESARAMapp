# -*- coding: utf-8 -*-
"""Testes da v0.15.3 — as perguntas como dados.

O espelho da v0.15.2, agora para a outra metade do conteúdo leigo:

  1. REESCRITAS COMO DADOS: app/data/perguntas_utente.json (editável pela
     equipa clínica) é a única fonte das perguntas leigas; as regras
     espelham-no (via aplicar_perguntas_utente.py, idempotente e sem
     Excel) e a cobertura tem de ser TOTAL — discriminador sem entrada é
     erro, porque o utente veria o texto clínico.
  2. ESTADO DE VALIDAÇÃO por item e o portão ONDE_IR_APENAS_VALIDADO no
     motor — que aqui REVERTE para a pergunta clínica oficial (nunca
     esconde: esconder mudaria a triagem).
  3. VISTA DE REVISÃO: /api/perguntas/revisao e a secção "Perguntas" da
     página /revisao.
  4. FERRAMENTA marcar_validado.py (aconselhamento e perguntas) e a
     escolha bilingue do frontend fixada em Node (Nucleo.textoNaLingua).

A lógica de triagem (prioridades e cores) NÃO muda nesta versão.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from _manchester_comum import normalizar, sha256_de  # noqa: E402
from _perguntas_utente import (  # noqa: E402
    FICHEIRO_PERGUNTAS,
    PERGUNTAS_UTENTE,
    REGISTO_PERGUNTAS,
    carregar_perguntas,
)
from aplicar_perguntas_utente import aplicar_a_fluxo  # noqa: E402
from marcar_validado import gravar, marcar_itens, resolver_chave, sugerir  # noqa: E402
from verificar_perguntas import analisar  # noqa: E402

from app.core.triage_engine import (  # noqa: E402
    PASTA_REGRAS,
    TriageEngine,
)
from app.main import app  # noqa: E402

cliente = TestClient(app)


# --------------------------------------------- reescritas como dados --


def test_perguntas_ficheiro_editavel_estrutura():
    """O ficheiro que a equipa clínica edita: pt/en não vazios, estado são,
    chaves já na forma canónica (espaços colapsados)."""
    dados = carregar_perguntas()
    itens = dados["itens"]
    assert len(itens) >= 180, "esperavam-se ~186 reescritas de perguntas"
    for chave, item in itens.items():
        assert chave == normalizar(chave), f"chave por normalizar: {chave!r}"
        assert item["pt"].strip() and item["en"].strip()
        assert isinstance(item["validado"], bool)
        if item["validado"]:
            assert item["validado_por"] and item["validado_em"]
        else:
            assert item["validado_por"] is None and item["validado_em"] is None


def test_shim_historico_derivado_do_json():
    """PERGUNTAS_UTENTE (nome antigo, chave→(pt, en)) vem agora do JSON:
    o importador da tabela e os testes antigos continuam a funcionar."""
    assert set(PERGUNTAS_UTENTE) == set(REGISTO_PERGUNTAS)
    exemplo = next(iter(PERGUNTAS_UTENTE))
    pt, en = PERGUNTAS_UTENTE[exemplo]
    assert pt == REGISTO_PERGUNTAS[exemplo]["pt"]
    assert en == REGISTO_PERGUNTAS[exemplo]["en"]


def test_regras_espelham_o_registo_com_cobertura_total():
    """TODOS os 1187 discriminadores têm texto_utente/_en iguais ao JSON
    editável. É a invariante central: editar o JSON + aplicar = regras em
    dia; e nenhum discriminador fica de fora (o recuo para o clínico é
    seguro, mas em desenvolvimento quer-se a camada leiga completa)."""
    registo_norm = {normalizar(c): i for c, i in REGISTO_PERGUNTAS.items()}
    total = 0
    for caminho in sorted(PASTA_REGRAS.glob("*.json")):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if dados.get("id") == "red_flags":
            continue
        for disc in dados["perguntas"]:
            total += 1
            chave = normalizar(disc["texto"])
            assert chave in registo_norm, f"{caminho.name}: sem reescrita {chave!r}"
            item = registo_norm[chave]
            assert disc.get("texto_utente") == item["pt"]
            assert disc.get("texto_utente_en") == item["en"]
    assert total == 1187


def test_estado_de_validacao_nao_e_copiado_para_as_regras():
    """Decisão de desenho: o estado vive SÓ no JSON editável (o motor lê-o
    no arranque). As regras não o duplicam — duplicar era garantia de
    dessincronização, porque as regras também se editam à mão."""
    for caminho in sorted(PASTA_REGRAS.glob("*.json")):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if dados.get("id") == "red_flags":
            continue
        for disc in dados["perguntas"]:
            assert "validado" not in disc
            assert "validado_por" not in disc
            assert "validado_em" not in disc


def test_aplicar_e_idempotente_no_repo_real():
    """Correr o aplicar sem editar nada não muda um byte e di-lo."""
    res = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "aplicar_perguntas_utente.py")],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Sem alterações." in res.stdout


def test_aplicar_a_fluxo_refaz_e_preserva_ordem_dos_campos():
    """Unidade do aplicar: refaz texto_utente/_en a partir do registo e
    mantém a ordem canónica dos campos (texto_utente logo após texto)."""
    fluxo = {
        "id": "demo",
        "perguntas": [
            {
                "id": "d1",
                "disc_id": 1,
                "prioridade": "P1",
                "cor": "vermelho",
                "texto": "Dor  torácica?",
                "texto_en": "Chest pain?",
                "texto_utente": "ANTIGO",
                "texto_utente_en": "OLD",
            },
        ],
    }
    registo_norm = {"Dor torácica?": {"pt": "Sente dor no peito?", "en": "Do you feel chest pain?"}}
    saida = aplicar_a_fluxo(fluxo, registo_norm)
    disc = saida["perguntas"][0]
    assert disc["texto_utente"] == "Sente dor no peito?"
    assert disc["texto_utente_en"] == "Do you feel chest pain?"
    chaves = list(disc)
    assert chaves.index("texto") < chaves.index("texto_utente") < chaves.index("texto_en")


# ------------------------------------------------------- verificador --


@pytest.fixture()
def sandbox_regras(tmp_path):
    """Uma pasta de regras mínima + registo em dia, para partir dela."""
    pasta = tmp_path / "rules"
    pasta.mkdir()
    (pasta / "demo.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "nome": "Demo",
                "perguntas": [
                    {
                        "id": "d1",
                        "disc_id": 1,
                        "prioridade": "P1",
                        "cor": "vermelho",
                        "texto": "Compromisso da via aérea?",
                        "texto_utente": "Pergunta leiga A?",
                        "texto_en": "Airway?",
                        "texto_utente_en": "Lay question A?",
                    },
                    {
                        "id": "d2",
                        "disc_id": 2,
                        "prioridade": "P2",
                        "cor": "laranja",
                        "texto": "Dor severa?",
                        "texto_utente": "Pergunta leiga B?",
                        "texto_en": "Severe pain?",
                        "texto_utente_en": "Lay question B?",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registo = {
        "Compromisso da via aérea?": {
            "pt": "Pergunta leiga A?",
            "en": "Lay question A?",
            "validado": False,
            "validado_por": None,
            "validado_em": None,
        },
        "Dor severa?": {
            "pt": "Pergunta leiga B?",
            "en": "Lay question B?",
            "validado": True,
            "validado_por": "Dra. X",
            "validado_em": "2026-07-18",
        },
    }
    return pasta, registo


def test_verificador_sandbox_em_dia_passa(sandbox_regras):
    pasta, registo = sandbox_regras
    erros, _avisos = analisar(pasta, registo)
    assert erros == []


def test_verificador_apanha_divergencia_e_manda_correr_o_aplicar(sandbox_regras):
    """Editou o JSON e esqueceu-se de aplicar (ou editou a regra à mão):
    o erro diz exatamente o que correr."""
    pasta, registo = sandbox_regras
    registo["Dor severa?"]["pt"] = "Pergunta leiga B, corrigida?"
    erros, _ = analisar(pasta, registo)
    assert any("aplicar_perguntas_utente.py" in e for e in erros)


def test_verificador_apanha_orfa_sem_entrada_e_validacao_incompleta(sandbox_regras):
    pasta, registo = sandbox_regras
    # órfã: chave que não corresponde a nenhum discriminador
    registo["Chave fantasma?"] = {
        "pt": "x?",
        "en": "y?",
        "validado": False,
        "validado_por": None,
        "validado_em": None,
    }
    # sem entrada: discriminador novo nas regras, ainda sem reescrita
    dados = json.loads((pasta / "demo.json").read_text(encoding="utf-8"))
    dados["perguntas"].append(
        {
            "id": "d3",
            "disc_id": 3,
            "prioridade": "P3",
            "cor": "amarelo",
            "texto": "Discriminador novo?",
        }
    )
    (pasta / "demo.json").write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    # validação incompleta: validado sem data válida
    registo["Dor severa?"]["validado_em"] = "ontem"
    erros, _ = analisar(pasta, registo)
    texto = "\n".join(erros)
    assert "órfã" in texto
    assert "sem entrada" in texto
    assert "Dor severa?" in texto  # a validação incompleta identifica o item


def test_verificador_avisa_texto_clinico_repetido_intra_fluxo(tmp_path):
    """O caso herdado da tabela: o MESMO texto clínico repetido no mesmo
    fluxo partilha (por construção) a mesma reescrita — é aviso, não erro."""
    pasta = tmp_path / "rules"
    pasta.mkdir()
    (pasta / "demo.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "perguntas": [
                    {
                        "id": "a",
                        "disc_id": 1,
                        "prioridade": "P2",
                        "cor": "laranja",
                        "texto": "Pedido de apoio?",
                        "texto_utente": "Leiga?",
                        "texto_utente_en": "Lay?",
                    },
                    {
                        "id": "b",
                        "disc_id": 2,
                        "prioridade": "P3",
                        "cor": "amarelo",
                        "texto": "Pedido de apoio?",
                        "texto_utente": "Leiga?",
                        "texto_utente_en": "Lay?",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registo = {
        "Pedido de apoio?": {
            "pt": "Leiga?",
            "en": "Lay?",
            "validado": False,
            "validado_por": None,
            "validado_em": None,
        }
    }
    erros, avisos = analisar(pasta, registo)
    assert erros == []
    assert any("repetido" in a for a in avisos)


def test_verificador_repo_real_sem_erros():
    """A rede de segurança que o CI corre: o repositório real está em dia.
    (Os avisos dos textos repetidos herdados da tabela são tolerados.)"""
    erros, _avisos = analisar()
    assert erros == [], "\n".join(erros)


def test_normalizacao_do_portao_equivale_a_normalizar():
    """O motor usa ' '.join(s.split()) para não importar scripts/; tem de
    ser exatamente a normalizar() do resto do projeto — incluindo NBSP."""
    amostras = ["a  b", " a\tb ", "a\xa0b", "a \xa0  b", "só um", ""]
    for s in amostras:
        assert " ".join(s.split()) == normalizar(s)


# ------------------------------------------------- portão de produção --


@pytest.fixture()
def motor_sandbox(tmp_path):
    """Pasta de regras válida mínima + ficheiro de perguntas próprio, para
    construir motores sem tocar nos dados reais."""
    pasta = tmp_path / "rules"
    pasta.mkdir()
    shutil.copy(PASTA_REGRAS / "red_flags.json", pasta / "red_flags.json")
    (pasta / "demo.json").write_text(
        json.dumps(
            {
                "id": "demo",
                "nome": "Demo",
                "nome_en": "Demo",
                "descricao": "",
                "perguntas": [
                    {
                        "id": "d1",
                        "disc_id": 1,
                        "prioridade": "P1",
                        "cor": "vermelho",
                        "texto": "Compromisso da via aérea?",
                        "texto_utente": "Reescrita validada?",
                        "texto_en": "Airway compromise?",
                        "texto_utente_en": "Validated rewrite?",
                    },
                    {
                        "id": "d2",
                        "disc_id": 2,
                        "prioridade": "P2",
                        "cor": "laranja",
                        "texto": "Dor severa?",
                        "texto_utente": "Reescrita por validar?",
                        "texto_en": "Severe pain?",
                        "texto_utente_en": "Unvalidated rewrite?",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    ficheiro = tmp_path / "perguntas_utente.json"
    ficheiro.write_text(
        json.dumps(
            {
                "itens": {
                    "Compromisso da via aérea?": {
                        "pt": "Reescrita validada?",
                        "en": "Validated rewrite?",
                        "validado": True,
                        "validado_por": "Dra. X",
                        "validado_em": "2026-07-18",
                    },
                    "Dor severa?": {
                        "pt": "Reescrita por validar?",
                        "en": "Unvalidated rewrite?",
                        "validado": False,
                        "validado_por": None,
                        "validado_em": None,
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pasta, ficheiro


def _discs(motor):
    return {d["texto"]: d for d in motor.fluxos["demo"]["perguntas"]}


def test_portao_desligado_por_omissao_mantem_as_reescritas(motor_sandbox, monkeypatch):
    monkeypatch.delenv("ONDE_IR_APENAS_VALIDADO", raising=False)
    pasta, ficheiro = motor_sandbox
    discs = _discs(TriageEngine(pasta, ficheiro_perguntas_utente=ficheiro))
    assert discs["Dor severa?"]["texto_utente"] == "Reescrita por validar?"


def test_portao_reverte_nao_validado_e_mantem_validado(motor_sandbox, monkeypatch):
    """A semântica do portão: reverter (não esconder) a redação por
    validar; o utente vê a pergunta CLÍNICA oficial nesses itens."""
    monkeypatch.setenv("ONDE_IR_APENAS_VALIDADO", "1")
    pasta, ficheiro = motor_sandbox
    discs = _discs(TriageEngine(pasta, ficheiro_perguntas_utente=ficheiro))
    validado = discs["Compromisso da via aérea?"]
    por_validar = discs["Dor severa?"]
    assert validado["texto_utente"] == "Reescrita validada?"
    assert validado["texto_utente_en"] == "Validated rewrite?"
    assert "texto_utente" not in por_validar  # recua para `texto`
    assert "texto_utente_en" not in por_validar
    assert por_validar["texto"] == "Dor severa?"  # a pergunta nunca some


def test_portao_ficheiro_ausente_reverte_tudo_sem_partir(motor_sandbox, monkeypatch):
    monkeypatch.setenv("ONDE_IR_APENAS_VALIDADO", "sim")
    pasta, ficheiro = motor_sandbox
    discs = _discs(
        TriageEngine(pasta, ficheiro_perguntas_utente=ficheiro.parent / "nao_existe.json")
    )
    for disc in discs.values():
        assert "texto_utente" not in disc and disc["texto"]


def test_portao_ficheiro_corrompido_falha_no_arranque(motor_sandbox, monkeypatch):
    monkeypatch.setenv("ONDE_IR_APENAS_VALIDADO", "true")
    pasta, ficheiro = motor_sandbox
    ficheiro.write_text("{isto não é json", encoding="utf-8")
    with pytest.raises(RuntimeError):
        TriageEngine(pasta, ficheiro_perguntas_utente=ficheiro)


# --------------------------------------------------- vista de revisão --


def test_api_perguntas_revisao_estrutura_e_totais():
    r = cliente.get("/api/perguntas/revisao")
    assert r.status_code == 200
    dados = r.json()
    assert dados["erro"] is None
    t = dados["totais"]
    assert t["fluxos"] == 56 and t["discriminadores"] == 1187
    assert t["com_reescrita"] == 1187  # cobertura total
    assert t["reescritas"] == len(REGISTO_PERGUNTAS)
    assert t["validados"] == sum(1 for i in REGISTO_PERGUNTAS.values() if i.get("validado"))
    fonte = dados["fonte"]["reescritas"]
    assert fonte["sha256"] == sha256_de(FICHEIRO_PERGUNTAS)
    nomes = [f["nome"] for f in dados["fluxos"]]
    assert nomes == sorted(nomes), "fluxos por ordem alfabética do nome"


def test_api_perguntas_revisao_traz_o_par_clinico_leigo():
    dados = cliente.get("/api/perguntas/revisao").json()
    perg = dados["fluxos"][0]["perguntas"][0]
    for campo in (
        "cor",
        "prioridade",
        "texto",
        "texto_utente",
        "texto_utente_en",
        "sem_entrada",
        "validado",
    ):
        assert campo in perg
    assert perg["sem_entrada"] is False


def test_pagina_revisao_tem_a_seccao_das_perguntas():
    r = cliente.get("/revisao")
    assert r.status_code == 200
    assert "sel-seccao" in r.text
    assert "perguntas/revisao" in r.text
    assert 'name="robots" content="noindex' in r.text


# ------------------------------------------------ marcar_validado.py --


@pytest.fixture()
def registo_tmp(tmp_path):
    caminho = tmp_path / "perguntas_utente.json"
    dados = {
        "itens": {
            "Dor torácica?": {
                "pt": "Sente dor no peito?",
                "en": "Chest pain?",
                "validado": False,
                "validado_por": None,
                "validado_em": None,
            },
            "Sinais de choque?": {
                "pt": "Suores frios?",
                "en": "Cold sweats?",
                "validado": False,
                "validado_por": None,
                "validado_em": None,
            },
        }
    }
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return caminho, dados


def test_marcar_e_desmarcar_em_memoria(registo_tmp):
    _caminho, dados = registo_tmp
    resolvidas, falhadas = marcar_itens(
        dados, ["Dor  torácica?"], por="Dra. X", em="2026-07-18"  # espaços a mais: tolerados
    )
    assert resolvidas == ["Dor torácica?"] and falhadas == {}
    item = dados["itens"]["Dor torácica?"]
    assert item["validado"] is True
    assert item["validado_por"] == "Dra. X" and item["validado_em"] == "2026-07-18"

    marcar_itens(dados, ["Dor torácica?"], por=None, em=None, desmarcar=True)
    assert dados["itens"]["Dor torácica?"] == {
        "pt": "Sente dor no peito?",
        "en": "Chest pain?",
        "validado": False,
        "validado_por": None,
        "validado_em": None,
    }


def test_marcar_chave_errada_sugere_parecidas(registo_tmp):
    _caminho, dados = registo_tmp
    resolvidas, falhadas = marcar_itens(dados, ["Dor toracica?"], por="X", em="2026-07-18")
    assert resolvidas == []
    assert list(falhadas) == ["Dor toracica?"]
    assert "Dor torácica?" in falhadas["Dor toracica?"]
    # e nada foi marcado
    assert not any(i["validado"] for i in dados["itens"].values())


def test_gravar_no_formato_canonico(registo_tmp):
    caminho, dados = registo_tmp
    antes = caminho.read_text(encoding="utf-8")
    gravar(dados, caminho)  # sem alterações em memória
    assert caminho.read_text(encoding="utf-8") == antes
    assert antes.endswith("}\n") and '"itens"' in antes


def test_resolver_e_sugerir():
    itens = REGISTO_PERGUNTAS
    exemplo = next(iter(itens))
    assert resolver_chave(itens, "  " + exemplo + "  ") == exemplo
    assert resolver_chave(itens, "não existe de certeza???") is None
    assert len(sugerir(itens, exemplo[:-1])) >= 1


def test_cli_listar_smoke():
    res = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "scripts" / "marcar_validado.py"),
            "perguntas",
            "--listar",
            "--contem",
            "via aérea",
        ],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "por validar" in res.stdout
    assert re.search(r"\d+ itens:", res.stdout)


def test_cli_chave_errada_nao_grava_e_sai_com_1():
    antes = FICHEIRO_PERGUNTAS.read_bytes()
    res = subprocess.run(
        [
            sys.executable,
            str(RAIZ / "scripts" / "marcar_validado.py"),
            "perguntas",
            "chave que não existe",
            "--por",
            "X",
        ],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "Nada foi gravado" in res.stderr
    assert FICHEIRO_PERGUNTAS.read_bytes() == antes


# ----------------------------------------- frontend: escolha bilingue --


def test_nucleo_exporta_texto_na_lingua_e_testes_node_passam():
    js = (RAIZ / "static" / "js" / "nucleo.js").read_text(encoding="utf-8")
    assert "textoNaLingua" in js
    node = shutil.which("node")
    if node is None:
        pytest.skip("node não disponível neste ambiente")
    res = subprocess.run(
        [node, "--test", str(RAIZ / "tests" / "js" / "teste_nucleo.js")],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr


def test_app_delega_a_escolha_bilingue_no_nucleo():
    """campo() já não implementa a regra — injeta a língua e delega. Se
    alguém a reimplementar em app.js, este teste rebenta."""
    js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    corpo = js.split("function campo(", 1)[1].split("}", 1)[0]
    assert "Nucleo.textoNaLingua" in corpo
    assert 'obj[nome + "_en"]' not in corpo


# ------------------------------------------------------------- versão --


def test_versao_0_15_3():
    from app.versao import VERSAO

    assert tuple(int(x) for x in VERSAO.split(".")) >= (0, 15, 3)


def test_index_html_com_cache_busting_novo():
    # v0.16: tal como o test_v15_2 deixou de pinar o número exato do
    # cache-busting, este teste passa a fixar o que interessa (um crachá de
    # versão e os quatro recursos com ?v=) sem partir a cada entrega. O
    # número exato da versão corrente vive em test_v16.
    html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
    assert re.search(r"v0\.\d+\.\d+", html), "crachá de versão ausente do index"
    assert len(re.findall(r"\?v=\d+", html)) == 4
