"""Schemas dos pedidos/respostas da API (Pydantic).

O FastAPI usa isto para validar automaticamente os pedidos e para gerar
a documentação interativa em /docs. Mostra isso na apresentação do
estágio, causa sempre boa impressão.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Cor = Literal["vermelho", "laranja", "amarelo", "verde", "azul"]
Resposta = Literal["sim", "nao"]


class TriagemRequest(BaseModel):
    """Pedido de triagem.

    Duas formas de usar:
    1. red_flags preenchido → resultado imediato (vermelho / 112);
    2. queixa + respostas acumuladas → próxima pergunta ou resultado.
    """

    queixa: str | None = Field(
        default=None,
        description="Id da queixa (ver GET /api/queixas). Ex.: 'dor_toracica'.",
        examples=["dor_toracica"],
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Ids dos sinais de emergência selecionados, se existirem.",
    )
    respostas: dict[str, Resposta] = Field(
        default_factory=dict,
        description="Respostas dadas até agora: {id_pergunta: 'sim'|'nao'}.",
        examples=[{"dt_q1": "nao", "dt_q2": "sim"}],
    )


class EncaminhamentoRequest(BaseModel):
    """Pedido de encaminhamento após a triagem."""

    cor: Cor = Field(description="Cor atribuída pela triagem.")
    lat: float = Field(ge=-90, le=90, description="Latitude do utente.")
    lng: float = Field(ge=-180, le=180, description="Longitude do utente.")
    quando: datetime | None = Field(
        default=None,
        description=(
            "Opcional: simular a hora do cálculo (ISO 8601, ex.: "
            "'2026-06-29T03:00:00'). Útil para demonstrações e testes; "
            "se omitido, usa-se a hora atual na Madeira."
        ),
    )
