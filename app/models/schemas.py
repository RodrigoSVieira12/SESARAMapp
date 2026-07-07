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


class IntegracaoTriagemRequest(BaseModel):
    """Pedido combinado (triagem + encaminhamento) numa só chamada.

    Pensado para consumo por sistemas externos. O chamador envia a queixa e
    TODAS as respostas que tem; a API devolve, num só pacote:
    - se faltarem respostas → a próxima pergunta ('tipo': 'pergunta');
    - se a cor já foi determinada → o resultado e, quando lat/lng forem
      dados, também o encaminhamento ('tipo': 'resultado').
    É stateless: nada é guardado no servidor.
    """

    queixa: str | None = Field(default=None, examples=["dor_abdominal"])
    red_flags: list[str] = Field(default_factory=list)
    respostas: dict[str, Resposta] = Field(
        default_factory=dict, examples=[{"ab_q1": "sim", "ab_q2": "nao"}]
    )
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    quando: datetime | None = Field(default=None)


class ResumoPdfRequest(BaseModel):
    """Dados para gerar o PDF de orientação.

    Reflete o que o utente viu no ecrã de resultado/encaminhamento. Todos os
    campos são opcionais e o gerador desenha defensivamente o que existir —
    assim o frontend envia simplesmente o estado atual, sem transformações.
    O modelo aceita campos extra (não os rejeita) para o tornar tolerante a
    evoluções do frontend.
    """

    model_config = {"extra": "allow"}

    cor: str | None = None
    classificacao: str | None = None
    cor_hex: str | None = None
    tempo_alvo: str | None = None
    descricao_cor: str | None = None
    queixa: str | None = None
    motivo: str | None = None
    respostas: list[dict] = Field(default_factory=list)
    mensagem: str | None = None
    unidade: dict | None = None
    alternativas: list[dict] = Field(default_factory=list)
    autocuidado: dict | None = None
    contactos: dict | None = None
    gerado_em: str | None = None
    lingua: str | None = "pt"
