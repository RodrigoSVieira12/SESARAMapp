# -*- coding: utf-8 -*-
"""Reescritas das perguntas em linguagem do utente — CARREGADOR (v0.15.3).

Até à v0.15.2, as perguntas leigas (PT e EN) viviam aqui, num dicionário
Python com ~190 entradas. Era a última grande fatia de conteúdo clínico
dentro de código: a equipa clínica conseguia editar as regras e (desde a
v0.15.2) o aconselhamento sem tocar em Python, mas para corrigir uma
pergunta reescrita tinha de mexer num `.py`.

Desde a v0.15.3 os textos vivem em `app/data/perguntas_utente.json`,
editável como qualquer outro ficheiro de dados, com o par PT/EN lado a lado
e o estado de validação clínica por item (`validado`, `validado_por`,
`validado_em`) — exatamente o mesmo padrão de
`app/data/aconselhamento_utente.json`. Este módulo passou a ser só o
carregador desse ficheiro, e mantém o nome histórico (`PERGUNTAS_UTENTE`,
dict chave→(pt, en)) para o importador da tabela e os testes continuarem a
funcionar sem alterações.

A POLÍTICA aqui é diferente da do aconselhamento, e está documentada no
próprio ficheiro (campo "politica"): para as perguntas, o recuo para o
texto clínico oficial É SEGURO (é a pergunta validada de Manchester), por
isso a reescrita é uma camada de legibilidade — nunca esconde nada nem
altera a lógica. Em produção, o portão ONDE_IR_APENAS_VALIDADO=1 faz o
utente ver a pergunta clínica oficial em vez de qualquer reescrita ainda
não validada.

Depois de editar as FRASES do JSON, aplicar às regras SEM precisar do
Excel:

    python scripts/aplicar_perguntas_utente.py

Marcar itens como validados NÃO precisa de aplicar nada: o estado vive só
neste ficheiro e o motor lê-o no arranque (ver triage_engine).
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO_PERGUNTAS = RAIZ / "app" / "data" / "perguntas_utente.json"


def carregar_perguntas(caminho: Path = FICHEIRO_PERGUNTAS) -> dict:
    """Lê e valida (estruturalmente) o ficheiro editável das perguntas.

    Tal como no aconselhamento, aqui NÃO há tolerância: os scripts que
    dependem disto (importar, aplicar, verificar) não fazem sentido sem as
    reescritas, e falhar cedo é melhor do que gerar regras sem a camada do
    utente em silêncio. (O servidor é outra história: o motor arranca sem
    este ficheiro — as perguntas clínicas chegam sempre — e só o portão de
    produção o lê, com tolerância própria.)
    """
    if not caminho.exists():
        raise RuntimeError(f"reescritas das perguntas não encontradas: {caminho}")
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"perguntas_utente.json inválido ({caminho}): {exc}") from exc
    itens = dados.get("itens")
    if not isinstance(itens, dict) or not itens:
        raise RuntimeError("perguntas_utente.json sem o objeto 'itens' (ou vazio).")
    for chave, item in itens.items():
        if not isinstance(item, dict) or not item.get("pt") or not item.get("en"):
            raise RuntimeError(
                "perguntas_utente.json: cada item precisa de 'pt' e 'en' "
                f"não vazios (item em falta ou incompleto: {chave!r})"
            )
    return dados


# Registo completo por texto clínico: {"pt", "en", "validado", ...}.
REGISTO_PERGUNTAS: dict[str, dict] = carregar_perguntas()["itens"]

# Nome histórico (v0.14.1—v0.15.2), ainda usado pelo importador da tabela e
# pelos testes: o mesmo mapa chave→(pt, en), agora derivado do JSON.
PERGUNTAS_UTENTE: dict[str, tuple[str, str]] = {
    c: (i["pt"], i["en"]) for c, i in REGISTO_PERGUNTAS.items()
}
