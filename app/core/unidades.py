"""Repositório das unidades de saúde da RAM.

Os dados vivem em app/data/unidades.json. Este módulo só os carrega
(uma vez) e oferece funções de consulta. Se um dia isto passar para
SQLite ou para uma API interna do SESARAM, só este ficheiro muda.
"""

from __future__ import annotations

import json
from pathlib import Path

CAMINHO_UNIDADES = Path(__file__).resolve().parent.parent / "data" / "unidades.json"

_cache: list[dict] | None = None


def todas(recarregar: bool = False) -> list[dict]:
    """Todas as unidades. Usa cache em memória (o ficheiro raramente muda)."""
    global _cache
    if _cache is None or recarregar:
        _cache = json.loads(CAMINHO_UNIDADES.read_text(encoding="utf-8"))
    return _cache


def por_id(unidade_id: str) -> dict | None:
    return next((u for u in todas() if u["id"] == unidade_id), None)


def concelhos() -> list[str]:
    return sorted({u["concelho"] for u in todas()})


def com_servicos(nomes_servicos: list[str]) -> list[dict]:
    """Unidades que oferecem pelo menos um dos serviços pedidos."""
    return [
        u for u in todas()
        if any(s in u.get("servicos", {}) for s in nomes_servicos)
    ]
