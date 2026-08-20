# -*- coding: utf-8 -*-
"""Reescritas do aconselhamento em linguagem do utente — CARREGADOR (v0.15.2).

Até à v0.15.1, as frases leigas (PT e EN) viviam aqui, em dois dicionários
Python. Isso contrariava a filosofia do projeto ("regras como dados, a equipa
clínica edita sem tocar em código"): a coisa que a equipa clínica mais vai
querer corrigir — as frases mostradas ao doente — obrigava a editar um `.py`.

Desde a v0.15.2 os textos vivem em `app/data/aconselhamento_utente.json`,
editável como qualquer outro ficheiro de dados, com o par PT/EN lado a lado e
o estado de validação clínica por item (`validado`, `validado_por`,
`validado_em`). Este módulo passou a ser só o carregador desse ficheiro, e
mantém os dois nomes históricos (`ACONSELHAMENTO_UTENTE`,
`ACONSELHAMENTO_UTENTE_EN`) para o importador, o verificador e os testes
continuarem a funcionar sem alterações.

A POLÍTICA DE SEGURANÇA não mudou e está documentada no próprio ficheiro
(campo "politica") e em docs/GUIA_DOS_DADOS.md: só itens com versão leiga
segura têm entrada; itens só-profissionais ficam de fora de propósito e o
frontend nunca recua para o texto clínico.

Depois de editar o JSON, aplicar às regras SEM precisar do Excel:

    python scripts/aplicar_aconselhamento_utente.py
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO_REESCRITAS = RAIZ / "app" / "data" / "aconselhamento_utente.json"


def carregar_reescritas(caminho: Path = FICHEIRO_REESCRITAS) -> dict:
    """Lê e valida (estruturalmente) o ficheiro editável das reescritas.

    Falha com uma mensagem clara se o ficheiro estiver ausente ou partido —
    aqui NÃO há tolerância: os scripts que dependem disto (importar, aplicar,
    verificar) não fazem sentido sem as reescritas, e falhar cedo é melhor do
    que gerar um aconselhamento.json vazio em silêncio. (O servidor nunca lê
    este ficheiro; a tolerância do arranque vive no motor, como sempre.)
    """
    if not caminho.exists():
        raise RuntimeError(f"reescritas do aconselhamento não encontradas: {caminho}")
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"aconselhamento_utente.json inválido ({caminho}): {exc}") from exc
    itens = dados.get("itens")
    if not isinstance(itens, dict) or not itens:
        raise RuntimeError("aconselhamento_utente.json sem o objeto 'itens' (ou vazio).")
    for chave, item in itens.items():
        if not isinstance(item, dict) or not item.get("pt") or not item.get("en"):
            raise RuntimeError(
                "aconselhamento_utente.json: cada item precisa de 'pt' e 'en' "
                f"não vazios (item em falta ou incompleto: {chave!r})"
            )
    return dados


# Registo completo por chave clínica: {"pt", "en", "validado", ...}.
REGISTO: dict[str, dict] = carregar_reescritas()["itens"]

# Nomes históricos (v0.15.0/v0.15.1), ainda usados pelo importador, pelo
# verificador e pelos testes: os mesmos mapas, agora derivados do JSON.
ACONSELHAMENTO_UTENTE: dict[str, str] = {c: i["pt"] for c, i in REGISTO.items()}
ACONSELHAMENTO_UTENTE_EN: dict[str, str] = {c: i["en"] for c, i in REGISTO.items()}
