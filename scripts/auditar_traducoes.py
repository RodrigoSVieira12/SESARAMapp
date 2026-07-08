#!/usr/bin/env python3
"""Auditoria de traduções (PT -> EN).

O que faz: percorre os textos da interface (static/js/textos.js) e os
conteúdos clínicos (app/data/rules/*.json, app/data/autocuidado.json) e diz
o que ainda NÃO está traduzido para inglês. Não traduz nada — apenas aponta,
para que uma pessoa (idealmente com competência clínica, no caso das regras)
traduza à mão. Traduzir conteúdo clínico por máquina seria arriscado.

Correr:  python scripts/auditar_traducoes.py

Devolve código de saída 0 se estiver tudo traduzido, 1 se faltar algo — útil
para integrar num CI mais tarde.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEXTOS = RAIZ / "static" / "js" / "textos.js"
RULES = RAIZ / "app" / "data" / "rules"
AUTOCUIDADO = RAIZ / "app" / "data" / "autocuidado.json"

# Campos de dados que são mostrados ao utente e devem ter versão _en.
# 'descricao' fica de fora de propósito: em alguns ficheiros é uma nota
# interna de desenvolvimento, não texto para o utente.
CAMPOS_TRADUZIVEIS = {
    "nome", "texto", "ajuda", "titulo", "intro", "alerta_titulo",
    "fazer", "evitar", "alerta", "mensagem",
}


def auditar_interface() -> list[str]:
    """Compara as chaves e os textos dos blocos pt e en em textos.js."""
    if not TEXTOS.exists():
        return [f"(ficheiro não encontrado: {TEXTOS})"]
    bloco = None
    chaves: dict[str, set[str]] = {"pt": set(), "en": set()}
    valores: dict[str, dict[str, str]] = {"pt": {}, "en": {}}
    for linha in TEXTOS.read_text(encoding="utf-8").splitlines():
        cabecalho = re.match(r"^  (pt|en)\s*:\s*\{", linha)
        if cabecalho:
            bloco = cabecalho.group(1)
            continue
        if bloco and re.match(r"^  \}", linha):
            bloco = None
            continue
        if bloco:
            m = re.match(r'^    (\w+)\s*:\s*(.*)$', linha)
            if m:
                chave, resto = m.group(1), m.group(2)
                chaves[bloco].add(chave)
                s = re.match(r'^"(.*)",?\s*$', resto)  # só valores string numa linha
                if s:
                    valores[bloco][chave] = s.group(1)

    problemas = []
    faltam = sorted(chaves["pt"] - chaves["en"])
    for chave in faltam:
        problemas.append(f"[interface] chave sem versão EN: {chave}")
    iguais = sorted(
        k for k in chaves["pt"] & chaves["en"]
        if k in valores["pt"] and k in valores["en"]
        and valores["pt"][k] == valores["en"][k]
        and valores["pt"][k].strip()  # ignora strings vazias
    )
    for chave in iguais:
        problemas.append(f"[interface] EN igual ao PT (provável cópia por traduzir): {chave}")
    return problemas


def _percorrer(no, caminho: str, problemas: list[str]) -> None:
    """Procura recursivamente campos traduzíveis sem o par _en."""
    if isinstance(no, dict):
        for campo in CAMPOS_TRADUZIVEIS:
            if campo in no and no[campo] not in (None, "", []):
                par = f"{campo}_en"
                if par not in no or no[par] in (None, "", []):
                    problemas.append(f"{caminho}: campo '{campo}' sem '{par}'")
        for chave, valor in no.items():
            if isinstance(valor, (dict, list)):
                _percorrer(valor, f"{caminho}.{chave}", problemas)
    elif isinstance(no, list):
        for i, item in enumerate(no):
            _percorrer(item, f"{caminho}[{i}]", problemas)


def auditar_conteudo() -> list[str]:
    problemas: list[str] = []
    ficheiros = sorted(RULES.glob("*.json")) if RULES.exists() else []
    if AUTOCUIDADO.exists():
        ficheiros.append(AUTOCUIDADO)
    for f in ficheiros:
        try:
            dados = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problemas.append(f"[{f.name}] JSON inválido: {e}")
            continue
        _percorrer(dados, f"[{f.name}]", problemas)
    return problemas


def main() -> int:
    interface = auditar_interface()
    conteudo = auditar_conteudo()

    print("=" * 60)
    print("AUDITORIA DE TRADUÇÕES (PT -> EN)")
    print("=" * 60)

    print("\nInterface (static/js/textos.js):")
    if interface:
        for p in interface:
            print("  -", p)
    else:
        print("  Tudo traduzido.")

    print("\nConteúdo clínico (regras + autocuidado):")
    if conteudo:
        for p in conteudo:
            print("  -", p)
    else:
        print("  Tudo traduzido.")

    total = len(interface) + len(conteudo)
    print("\n" + "-" * 60)
    if total == 0:
        print("Tudo traduzido. Nada a fazer.")
        return 0
    print(f"Em falta: {total} item(s). Traduzir à mão e voltar a correr.")
    print("Lembrete: o conteúdo clínico deve ser traduzido por alguém com")
    print("competência clínica, não por tradução automática.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
