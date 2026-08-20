# -*- coding: utf-8 -*-
"""Helpers partilhados pelos importadores da tabela de Manchester (v0.15.2).

Antes da v0.15.2, `importar_manchester.py` e `importar_aconselhamento.py`
definiam cada um a sua cópia de `slug()`, `normalizar()` e do mapa
prioridade→cor. Duas cópias que TÊM de andar sincronizadas: se o `slug()`
mudasse num e não no outro, o mapeamento fluxo↔aconselhamento partia-se em
silêncio (o aconselhamento apontaria para ids de fluxo que já não existem).
Este módulo passa a ser a única definição; os importadores e o verificador
importam daqui.

Regra de manutenção: mudar aqui é mudar o CONTRATO de identificação dos
fluxos e das chaves de texto. Depois de qualquer alteração, voltar a correr
os dois importadores e o `verificar_aconselhamento.py` (o CI também apanha).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

# P1-P5 -> cores de Manchester (igual a app/core/cores.py).
COR_DA_PRIORIDADE = {
    "P1": "vermelho",
    "P2": "laranja",
    "P3": "amarelo",
    "P4": "verde",
    "P5": "azul",
}
PRIORIDADES_VALIDAS = set(COR_DA_PRIORIDADE)


def normalizar(s) -> str:
    """Colapsa espaços (incl. \\xa0) num só e remove as pontas.

    É a forma canónica das CHAVES de texto clínico: o importador produz as
    chaves assim, e o mapeamento das reescritas leigas
    (app/data/aconselhamento_utente.json) usa exatamente a mesma forma.
    Aceita None/NaN do pandas e devolve "" nesses casos.
    """
    if s is None:
        return ""
    # NaN do pandas sem importar pandas aqui (float("nan") != float("nan")).
    if isinstance(s, float) and s != s:
        return ""
    return re.sub(r"\s+", " ", str(s).replace("\xa0", " ")).strip()


def slug(nome: str) -> str:
    """Nome do motivo -> id do fluxo (o stem do ficheiro em app/data/rules/).

    Mapa 1:1 confirmado na importação: 56 motivos <-> 56 ficheiros de regras.
    """
    n = nome.replace("(P)", "").replace("\u2013", "-")
    n = "".join(c for c in unicodedata.normalize("NFKD", n) if not unicodedata.combining(c))
    n = re.sub(r"[^a-z0-9]+", "_", n.lower())
    return re.sub(r"_+", "_", n).strip("_")


def sha256_de(caminho: Path) -> str:
    """SHA-256 (hex) de um ficheiro, para registar a proveniência dos dados.

    Usado no bloco `fonte` do aconselhamento.json: permite saber, mais tarde,
    de que versão exata da tabela/das reescritas os dados vieram — e ao
    verificador detetar que as reescritas mudaram sem o JSON ter sido
    regenerado.
    """
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            h.update(bloco)
    return h.hexdigest()
