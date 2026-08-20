# -*- coding: utf-8 -*-
"""Testes da v0.15.2 — governação do aconselhamento e redes de segurança.

Cobrem as quatro frentes desta versão:

  1. REESCRITAS COMO DADOS: app/data/aconselhamento_utente.json (editável
     pela equipa clínica) é a única fonte das frases leigas; o
     aconselhamento.json espelha-o (via aplicar_aconselhamento_utente.py,
     idempotente e sem Excel) e regista a proveniência (fonte.*).
  2. ESTADO DE VALIDAÇÃO por item (validado/validado_por/validado_em) e o
     portão de produção ONDE_IR_APENAS_VALIDADO no motor.
  3. VISTA DE REVISÃO: /api/aconselhamento/revisao e a página /revisao
     mostram também o que o filtro de segurança ESCONDE ao utente.
  4. REDES DE SEGURANÇA: o verificador apanha reescritas desatualizadas,
     edições à mão e validações incompletas; a propriedade de segurança do
     frontend está fixada em Node (tests/js/teste_nucleo.js, embrulhado
     aqui); helpers dos importadores unificados; auditoria de acessibilidade.

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

from _aconselhamento_utente import (  # noqa: E402
    FICHEIRO_REESCRITAS,
    REGISTO,
    carregar_reescritas,
)
from _manchester_comum import normalizar, sha256_de, slug  # noqa: E402
from verificar_aconselhamento import analisar  # noqa: E402

from app.core.triage_engine import FICHEIRO_ACONSELHAMENTO, TriageEngine  # noqa: E402
from app.main import app  # noqa: E402

cliente = TestClient(app)

CAMPOS_UTENTE = ("texto_utente", "texto_utente_en", "validado", "validado_por", "validado_em")


# ------------------------------------------------ reescritas como dados --


def test_reescritas_ficheiro_editavel_estrutura():
    """O ficheiro que a equipa clínica edita: pt/en não vazios e estado são."""
    dados = carregar_reescritas()
    assert dados["itens"], "sem itens nas reescritas"
    for chave, item in dados["itens"].items():
        assert item["pt"].strip() and item["en"].strip(), chave
        assert isinstance(item["validado"], bool), chave
        if item["validado"]:
            assert item["validado_por"], chave
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", item["validado_em"] or ""), chave
        # a chave é o texto clínico já normalizado (espaços colapsados)
        assert normalizar(chave) == chave, f"chave por normalizar: {chave!r}"


def test_shim_compat_mapas_derivados_do_json():
    """Os nomes históricos continuam a existir e derivam do JSON, alinhados."""
    from _aconselhamento_utente import (
        ACONSELHAMENTO_UTENTE,
        ACONSELHAMENTO_UTENTE_EN,
    )

    assert set(ACONSELHAMENTO_UTENTE) == set(ACONSELHAMENTO_UTENTE_EN) == set(REGISTO)
    exemplo = next(iter(REGISTO))
    assert ACONSELHAMENTO_UTENTE[exemplo] == REGISTO[exemplo]["pt"]
    assert ACONSELHAMENTO_UTENTE_EN[exemplo] == REGISTO[exemplo]["en"]


def test_aconselhamento_espelha_reescritas_e_fonte_em_dia():
    """Cada item com texto_utente espelha a entrada das reescritas; os sem
    texto_utente não trazem a camada do utente; o SHA gravado bate certo."""
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    assert dados["fonte"]["reescritas"]["sha256"] == sha256_de(FICHEIRO_REESCRITAS)
    for cores in dados["fluxos"].values():
        for bloco in cores.values():
            for it in bloco["itens"]:
                if it.get("texto_utente"):
                    entrada = REGISTO[normalizar(it["texto"])]
                    assert it["texto_utente"] == entrada["pt"]
                    assert it["texto_utente_en"] == entrada["en"]
                    assert it["validado"] == entrada["validado"]
                else:
                    assert not any(c in it for c in CAMPOS_UTENTE), it["texto"]


def test_aplicar_e_idempotente_e_sem_excel(tmp_path):
    """Correr o aplicar sobre o repositório não muda nada (está tudo em dia)."""
    antes = FICHEIRO_ACONSELHAMENTO.read_bytes()
    proc = subprocess.run(
        [sys.executable, "scripts/aplicar_aconselhamento_utente.py"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Sem alterações." in proc.stdout
    assert FICHEIRO_ACONSELHAMENTO.read_bytes() == antes


# ------------------------------------------- helpers comuns (importadores) --


def test_slug_e_normalizar_canonicos():
    assert slug("T.C.E \u2013 Trauma Crânio Encefálico (P)") == "t_c_e_trauma_cranio_encefalico"
    assert slug("Dor Torácica") == "dor_toracica"
    assert normalizar("  Dor\xa0 torácica \n forte  ") == "Dor torácica forte"
    assert normalizar(None) == "" and normalizar(float("nan")) == ""


def test_importadores_usam_o_modulo_comum():
    """Sem cópias locais: os dois importadores importam slug/cores do comum.

    (Verificação ao nível do texto-fonte de propósito: importar os módulos
    aqui obrigaria a ter pandas no CI, que só os scripts offline usam.)
    """
    for nome in ("importar_manchester.py", "importar_aconselhamento.py"):
        fonte = (RAIZ / "scripts" / nome).read_text(encoding="utf-8")
        assert "from _manchester_comum import" in fonte, nome
        assert "def slug(" not in fonte, f"{nome} ainda define slug() local"
        assert not re.search(
            r"^COR_DA_PRIORIDADE\s*=", fonte, re.M
        ), f"{nome} ainda define o mapa de cores local"


# --------------------------------------------------- verificador (redes) --


def _fixture(tmp_path, registo, itens, sha_certo=True):
    """Escreve um par (reescritas, aconselhamento) de brincar e devolve os
    caminhos + registo, prontos a passar ao analisar()."""
    reescritas = tmp_path / "aconselhamento_utente.json"
    reescritas.write_text(json.dumps({"itens": registo}, ensure_ascii=False), encoding="utf-8")
    sha = sha256_de(reescritas) if sha_certo else "0" * 64
    acons = tmp_path / "aconselhamento.json"
    acons.write_text(
        json.dumps(
            {
                "descricao": "fixture",
                "fonte": {"tabela": None, "reescritas": {"ficheiro": "x", "sha256": sha}},
                "fluxos": {"febre": {"verde": {"itens": itens}}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    inexistente = tmp_path / "sem_autocuidado.json"
    return dict(
        ficheiro=acons,
        ficheiro_reescritas=reescritas,
        registo=registo,
        ficheiro_autocuidado=inexistente,
    )


def _entrada(pt="Beba água.", en="Drink water.", **extra):
    base = {"pt": pt, "en": en, "validado": False, "validado_por": None, "validado_em": None}
    base.update(extra)
    return base


def _item(texto="Hidratar", entrada=None):
    it = {"texto": texto}
    if entrada:
        it |= {
            "texto_utente": entrada["pt"],
            "texto_utente_en": entrada["en"],
            "validado": entrada["validado"],
            "validado_por": entrada["validado_por"],
            "validado_em": entrada["validado_em"],
        }
    return it


def test_verificador_aceita_fixture_em_dia(tmp_path):
    registo = {"Hidratar": _entrada()}
    kwargs = _fixture(tmp_path, registo, [_item("Hidratar", registo["Hidratar"])])
    erros, _avisos = analisar(**kwargs)
    assert erros == []


def test_verificador_apanha_reescritas_desatualizadas(tmp_path):
    registo = {"Hidratar": _entrada()}
    kwargs = _fixture(tmp_path, registo, [_item("Hidratar", registo["Hidratar"])], sha_certo=False)
    erros, _ = analisar(**kwargs)
    assert any("aplicar_aconselhamento_utente" in e and "desatualizado" in e for e in erros)


def test_verificador_apanha_edicao_a_mao_do_gerado(tmp_path):
    registo = {"Hidratar": _entrada()}
    item = _item("Hidratar", registo["Hidratar"])
    item["texto_utente"] = "frase mexida à mão"
    erros, _ = analisar(**_fixture(tmp_path, registo, [item]))
    assert any("divergem" in e for e in erros)


def test_verificador_apanha_validacao_incompleta(tmp_path):
    registo = {"Hidratar": _entrada(validado=True)}  # sem por/em
    erros, _ = analisar(**_fixture(tmp_path, registo, [_item("Hidratar", registo["Hidratar"])]))
    assert any("validado=true" in e for e in erros)


def test_verificador_apanha_chave_orfa(tmp_path):
    registo = {"Hidratar": _entrada(), "Chave que já não existe na tabela": _entrada("x.", "x.")}
    erros, _ = analisar(**_fixture(tmp_path, registo, [_item("Hidratar", registo["Hidratar"])]))
    assert any("órfã" in e for e in erros)


def test_verificador_repo_real_sem_erros():
    erros, _avisos = analisar()
    assert erros == [], erros


# ------------------------------------- estado de validação e portão (motor) --


def _acons_de_teste(tmp_path) -> Path:
    f = tmp_path / "aconselhamento.json"
    f.write_text(
        json.dumps(
            {
                "fluxos": {
                    "dor_toracica": {
                        "vermelho": {
                            "itens": [
                                {
                                    "texto": "A clínico",
                                    "texto_utente": "validado ok",
                                    "texto_utente_en": "validated ok",
                                    "validado": True,
                                    "validado_por": "Dra. Exemplo",
                                    "validado_em": "2026-07-01",
                                },
                                {
                                    "texto": "B clínico",
                                    "texto_utente": "ainda por validar",
                                    "texto_utente_en": "still pending",
                                    "validado": False,
                                    "validado_por": None,
                                    "validado_em": None,
                                },
                            ]
                        }
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return f


def test_portao_apenas_validado_ligado(tmp_path, monkeypatch):
    monkeypatch.setenv("ONDE_IR_APENAS_VALIDADO", "1")
    motor = TriageEngine(ficheiro_aconselhamento=_acons_de_teste(tmp_path))
    itens = motor.aconselhamento["dor_toracica"]["vermelho"]["itens"]
    validado = next(i for i in itens if i["texto"] == "A clínico")
    pendente = next(i for i in itens if i["texto"] == "B clínico")
    assert validado["texto_utente"] == "validado ok"
    assert "texto_utente" not in pendente and "texto_utente_en" not in pendente
    assert pendente["texto"] == "B clínico"  # o clínico segue para integradores


def test_portao_desligado_por_omissao(tmp_path, monkeypatch):
    monkeypatch.delenv("ONDE_IR_APENAS_VALIDADO", raising=False)
    motor = TriageEngine(ficheiro_aconselhamento=_acons_de_teste(tmp_path))
    itens = motor.aconselhamento["dor_toracica"]["vermelho"]["itens"]
    assert all(i.get("texto_utente") for i in itens)


# ----------------------------------------------------- vista de revisão --


def test_api_revisao_estrutura_e_totais():
    r = cliente.get("/api/aconselhamento/revisao")
    assert r.status_code == 200
    d = r.json()
    assert d["erro"] is None
    # os totais têm de bater com o ficheiro real
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    itens = [it for cores in dados["fluxos"].values() for b in cores.values() for it in b["itens"]]
    assert d["totais"]["itens"] == len(itens)
    assert d["totais"]["mostrados_ao_utente"] == sum(1 for it in itens if it.get("texto_utente"))
    assert d["totais"]["ocultos"] == d["totais"]["itens"] - d["totais"]["mostrados_ao_utente"]
    assert d["fonte"]["reescritas"]["sha256"] == sha256_de(FICHEIRO_REESCRITAS)
    # nomes legíveis (não os ids) e ordenados
    nomes = [f["nome"] for f in d["fluxos"]]
    assert nomes == sorted(nomes, key=str.lower)
    assert any(" " in n for n in nomes)


def test_api_revisao_mostra_tambem_o_que_esta_oculto():
    d = cliente.get("/api/aconselhamento/revisao").json()
    ocultos = [
        it
        for f in d["fluxos"]
        for c in f["cores"]
        for it in c["itens"]
        if not it["mostrado_ao_utente"]
    ]
    assert ocultos, "a vista de revisão tem de expor os itens escondidos"
    assert all(it["texto"] and not it["texto_utente"] for it in ocultos)


def test_pagina_revisao_servida_e_interna():
    r = cliente.get("/revisao")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "noindex" in r.text  # ferramenta interna, fora dos motores de busca
    assert "aconselhamento/revisao" in r.text


# ------------------------------------------- frontend: núcleo testável --


def test_nucleo_carregado_antes_do_app_e_cache_atualizada():
    # Desde a v0.15.3 este teste deixou de pinar a versão exata do
    # cache-busting (?v=NN) — isso obrigava a editar testes antigos a cada
    # entrega. O que interessa fixar é a ORDEM (nucleo antes de app) e que
    # os três recursos têm ?v=; o número em si vive em test_v15_3.
    html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
    pos_nucleo = html.find("js/nucleo.js?v=")
    pos_app = html.find("js/app.js?v=")
    assert 0 < pos_nucleo < pos_app, "nucleo.js tem de carregar antes do app.js"
    assert "style.css?v=" in html and "textos.js?v=" in html


def test_app_delega_o_filtro_no_nucleo():
    js = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "Nucleo.conselhosParaMostrar" in js
    # a filtragem manual antiga saiu do app.js (vive — testada — no núcleo)
    assert "it.texto_utente) continue" not in js


def test_propriedade_de_seguranca_fixada_em_node():
    node = shutil.which("node")
    if not node:
        pytest.skip("node não disponível neste ambiente (o CI corre-o)")
    proc = subprocess.run(
        [node, "--test", "tests/js/teste_nucleo.js"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ------------------------------------------------------- acessibilidade --


def test_racio_de_contraste_wcag():
    from auditar_acessibilidade import racio_contraste

    assert round(racio_contraste("#000000", "#ffffff"), 1) == 21.0
    assert racio_contraste("#ffffff", "#ffffff") == 1.0


def test_auditoria_acessibilidade_passa():
    proc = subprocess.run(
        [sys.executable, "scripts/auditar_acessibilidade.py"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout


# ------------------------------------------------------------- versão --


def test_versao_0_15_2():
    # Mínimo em vez de igualdade exata, pela mesma razão do teste do
    # index.html: os testes de uma versão não devem partir na seguinte.
    from app.versao import VERSAO

    assert tuple(int(x) for x in VERSAO.split(".")) >= (0, 15, 2)
