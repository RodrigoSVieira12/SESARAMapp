"""Sugestão de queixas a partir de texto livre — sem inteligência artificial.

O utente escreve o que sente ("dói-me a barriga", "my head hurts") e este
módulo sugere as queixas mais prováveis, usando apenas:

  1. o nome e a descrição de cada fluxo (app/data/rules/*.json);
  2. um dicionário de sinónimos editável (app/data/sinonimos.json).

É a versão transparente e validável do que produtos comerciais fazem com
NLP: aqui, cada correspondência pode ser explicada e a equipa clínica pode
alargar o dicionário sem programar. Acentos e maiúsculas são ignorados.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

_FICHEIRO = Path(__file__).resolve().parents[1] / "data" / "sinonimos.json"

SINONIMOS: dict[str, list[str]] = json.loads(
    _FICHEIRO.read_text(encoding="utf-8")
)["sinonimos"]


def normalizar(texto: str) -> str:
    """Minúsculas e sem acentos: "Cólica" → "colica"."""
    minusculas = unicodedata.normalize("NFKD", str(texto).lower())
    return "".join(c for c in minusculas if not unicodedata.combining(c))


def _palavras(texto: str) -> list[str]:
    """Palavras com 3+ letras (ignora "de", "a", "o", "my", …)."""
    return [p for p in re.split(r"[^a-z0-9]+", texto) if len(p) >= 3]


def sugerir(texto: str, queixas: list[dict], maximo: int = 5) -> list[dict]:
    """Queixas ordenadas por relevância para o texto (lista vazia se nada bater).

    Pontuação simples e explicável:
      +3 quando uma expressão de várias palavras aparece inteira no texto;
      +2 quando um termo de uma palavra aparece inteiro no texto;
      +1 por cada palavra do texto que começa um termo (prefixo).
    """
    consulta = normalizar(texto)
    palavras = _palavras(consulta)
    if not consulta.strip():
        return []

    pontuadas: list[tuple[int, dict]] = []
    for queixa in queixas:
        termos = [
            queixa.get("nome", ""),
            queixa.get("descricao", ""),
            queixa.get("nome_en", ""),
            queixa.get("descricao_en", ""),
            *SINONIMOS.get(queixa["id"], []),
        ]
        termos_norm = [normalizar(t) for t in termos if t]

        pontos = 0
        for termo in termos_norm:
            if termo and termo in consulta:
                pontos += 3 if " " in termo else 2
        for palavra in palavras:
            if any(
                parte.startswith(palavra)
                for termo in termos_norm
                for parte in termo.split()
            ):
                pontos += 1

        if pontos:
            pontuadas.append((pontos, queixa))

    pontuadas.sort(key=lambda par: -par[0])
    return [queixa for _, queixa in pontuadas[:maximo]]
