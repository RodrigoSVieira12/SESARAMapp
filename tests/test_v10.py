"""Testes das alterações introduzidas desde a v0.9 (série v0.10).

Cobrem coisas concretas que mudaram, não enchem:
- v0.10.2: PDF de orientação passou a caber SEMPRE numa página.
- v0.10.3: os textos gerados pelo backend (mensagem de encaminhamento,
  descrição do dia, horários das unidades) passaram a ter versão inglesa,
  e os 6 fluxogramas que faltavam foram traduzidos.
- a auditoria de traduções deixou de encontrar lacunas.

Estes testes falham se alguém: partir a tradução do backend, acrescentar um
fluxograma/pergunta sem inglês, ou fizer o PDF transbordar para 2 páginas.
"""

from __future__ import annotations

import re
from datetime import datetime

from app.core import routing
from app.core.pdf_clinico import gerar_pdf

# Câmara de Lobos, sábado 15:00 (força fim de semana: exercita _contexto_do_dia).
_LAT, _LNG = 32.6510, -16.9770
_SABADO = datetime(2026, 7, 4, 15, 0)


def _num_paginas(pdf: bytes) -> int:
    """Conta páginas de um PDF do reportlab (robusto: /Type /Page, não /Pages)."""
    return len(re.findall(rb"/Type\s*/Page(?![s])", pdf))


# --------------------------------------------------------------------- #
# v0.10.3 — tradução dos textos gerados pelo backend                      #
# --------------------------------------------------------------------- #

def test_encaminhamento_tem_mensagem_en_em_todas_as_cores():
    for cor in ("vermelho", "laranja", "amarelo", "verde", "azul"):
        d = routing.decidir_encaminhamento(cor, _LAT, _LNG, quando=_SABADO)
        assert d.get("mensagem_en"), f"{cor}: falta mensagem_en"
        assert d["mensagem_en"] != d["mensagem"], f"{cor}: EN igual ao PT"
        # o inglês não deve conter frases portuguesas típicas
        assert "Dirija-se" not in d["mensagem_en"]
        assert "Ligue" not in d["mensagem_en"]


def test_mensagem_pt_continua_em_portugues():
    # Garante que não trocámos a língua por engano.
    d = routing.decidir_encaminhamento("vermelho", _LAT, _LNG, quando=_SABADO)
    assert "112" in d["mensagem"]
    assert d["mensagem"].startswith("Ligue")


def test_dia_tem_descricao_en():
    d = routing.decidir_encaminhamento("verde", _LAT, _LNG, quando=_SABADO)
    assert d["dia"]["descricao_en"] == "Saturday"
    assert d["dia"]["descricao"] != d["dia"]["descricao_en"]


def test_unidade_tem_horarios_en_traduzidos():
    d = routing.decidir_encaminhamento("verde", _LAT, _LNG, quando=_SABADO)
    unidade = d.get("unidade") or {}
    horarios_en = unidade.get("horarios_en") or {}
    assert horarios_en, "unidade sem horarios_en"
    juntos = " ".join(horarios_en.values())
    # não devem sobrar palavras portuguesas dos horários
    assert "Dias úteis" not in juntos
    assert "Urgência" not in juntos


def test_horario_en_traduz_padroes_conhecidos():
    assert routing._horario_en("Urgência aberta 24 horas") == "Open 24 hours"
    assert routing._horario_en("Dias úteis, 08:00-20:00") == "Weekdays, 08:00-20:00"
    assert (
        routing._horario_en("Segundas-Feiras 08:30-17:00, Terças a Sextas 08:30-16:30")
        == "Mondays 08:30-17:00, Tuesdays to Fridays 08:30-16:30"
    )
    # as horas nunca são alteradas
    assert "08:00-20:00" in routing._horario_en("Dias úteis, 08:00-20:00")


# --------------------------------------------------------------------- #
# v0.10.3 — conteúdo clínico e interface totalmente traduzidos            #
# --------------------------------------------------------------------- #

def test_conteudo_clinico_sem_lacunas_de_traducao():
    # importa a própria ferramenta de auditoria e exige zero lacunas
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parent.parent / "scripts" / "auditar_traducoes.py"
    spec = importlib.util.spec_from_file_location("auditar_traducoes", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.auditar_conteudo() == [], "há conteúdo clínico por traduzir"
    assert mod.auditar_interface() == [], "há textos de interface por traduzir"


def test_todos_os_fluxogramas_tem_texto_en():
    # explícito (além da auditoria): cada pergunta de cada fluxo tem texto_en
    import json
    from pathlib import Path

    rules = Path(__file__).resolve().parent.parent / "app" / "data" / "rules"
    for f in rules.glob("*.json"):
        if f.name == "red_flags.json":
            continue
        dados = json.loads(f.read_text(encoding="utf-8"))
        for p in dados.get("perguntas", []):
            assert "texto_en" in p, f"{f.name}:{p.get('id')} sem texto_en"


# --------------------------------------------------------------------- #
# v0.10.2 — o PDF de orientação cabe sempre numa página                   #
# --------------------------------------------------------------------- #

_PDF_LONGO = {
    "cor": "verde",
    "classificacao": "Pouco urgente",
    "cor_hex": "#2E7D32",
    "tempo_alvo": "Observação em cerca de 120 minutos",
    "queixa": "Febre",
    "mensagem": "Dirija-se ao Centro de Saúde de Câmara de Lobos. " * 3,
    "unidade": {
        "nome": "Centro de Saúde de Câmara de Lobos",
        "morada": "Rua Padre Eduardo Clemente Nunes Pereira, 9300 Câmara de Lobos",
        "telefone": "291 009 250",
        "horarios": {
            "consulta_aberta": "Dias úteis, 08:00-20:00",
            "atendimento_urgente": "Urgência aberta 24 horas",
        },
    },
    "autocuidado": {
        "alerta_titulo": "Procure ajuda se:",
        "alerta": [
            "Os sintomas piorarem ou surgirem sintomas novos",
            "Não houver melhoria em 24 a 48 horas",
            "Aparecer falta de ar",
            "Aparecer confusão ou dificuldade em acordar",
        ],
    },
}


def test_pdf_cabe_numa_pagina_caso_longo():
    assert _num_paginas(gerar_pdf(_PDF_LONGO)) == 1


def test_pdf_cabe_numa_pagina_caso_minimo():
    assert _num_paginas(gerar_pdf({"cor": "azul"})) == 1


def test_pdf_ingles_tambem_cabe_numa_pagina():
    payload = dict(_PDF_LONGO, lingua="en")
    assert _num_paginas(gerar_pdf(payload)) == 1
