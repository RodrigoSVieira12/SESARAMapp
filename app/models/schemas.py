"""Schemas dos pedidos/respostas da API (Pydantic).

O FastAPI usa isto para validar automaticamente os pedidos e para gerar
a documentação interativa em /docs. Mostra isso na apresentação do
estágio, causa sempre boa impressão.

Limites de sanidade (v0.16.2): todos os campos de texto e de lista têm
um tamanho máximo. Os tetos são folgados face aos dados reais (o maior
fluxo tem ~40 discriminadores, há 6 sinais de emergência, a interface
envia no máximo 3 alternativas, a maior mensagem tem ~700 caracteres),
por isso nenhum pedido legítimo é afetado — mas um pedido malicioso
deixa de poder custar segundos de CPU ao gerador de PDF ou memória ao
parser. São a segunda linha de defesa; a primeira é o limite de tamanho
do corpo em app/main.py, e a terceira são os cortes defensivos do
próprio gerador (app/core/pdf_clinico.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Cor = Literal["vermelho", "laranja", "amarelo", "verde", "azul"]
Resposta = Literal["sim", "nao"]

# Tipos com teto, reutilizados pelos schemas abaixo. Os ids reais têm
# ~5-40 caracteres; os textos mostrados (queixa, classificação) ~10-60;
# a maior mensagem de encaminhamento ~700.
IdCurto = Annotated[str, Field(max_length=80)]
TextoCurto = Annotated[str, Field(max_length=200)]
TextoLongo = Annotated[str, Field(max_length=2000)]


class TriagemRequest(BaseModel):
    """Pedido de triagem.

    Duas formas de usar:
    1. red_flags preenchido → resultado imediato (vermelho / 112);
    2. queixa + respostas acumuladas → próxima pergunta ou resultado.
    """

    queixa: IdCurto | None = Field(
        default=None,
        description="Id da queixa (ver GET /api/queixas). Ex.: 'dor_toracica'.",
        examples=["dor_toracica"],
    )
    red_flags: list[IdCurto] = Field(
        default_factory=list,
        max_length=20,
        description="Ids dos sinais de emergência selecionados, se existirem.",
    )
    respostas: dict[IdCurto, Resposta] = Field(
        default_factory=dict,
        max_length=200,
        description="Respostas dadas até agora: {id_pergunta: 'sim'|'nao'}.",
        examples=[{"dt_q1": "nao", "dt_q2": "sim"}],
    )


class EncaminhamentoRequest(BaseModel):
    """Pedido de encaminhamento após a triagem."""

    cor: Cor = Field(description="Cor atribuída pela triagem.")
    lat: float = Field(ge=-90, le=90, description="Latitude do utente.")
    lng: float = Field(ge=-180, le=180, description="Longitude do utente.")
    destino: Literal["hospital", "atendimento_urgente"] | None = Field(
        default=None,
        description=(
            "Opcional; só considerado no amarelo. Vem do campo 'destino' do "
            "desfecho do fluxograma (app/data/rules/*.json) e permite que "
            "certos amarelos sejam encaminhados para o atendimento urgente "
            "aberto mais próximo em vez do hospital (v0.12.1)."
        ),
    )
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

    queixa: IdCurto | None = Field(default=None, examples=["dor_abdominal"])
    red_flags: list[IdCurto] = Field(default_factory=list, max_length=20)
    respostas: dict[IdCurto, Resposta] = Field(
        default_factory=dict, max_length=200, examples=[{"ab_q1": "sim", "ab_q2": "nao"}]
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
    evoluções do frontend; o que impede abusos por essa porta é o limite de
    tamanho do corpo (app/main.py) e os cortes do gerador (v0.16.2).
    """

    model_config = {"extra": "allow"}

    cor: TextoCurto | None = None
    classificacao: TextoCurto | None = None
    cor_hex: Annotated[str, Field(max_length=30)] | None = None
    tempo_alvo: TextoCurto | None = None
    descricao_cor: Annotated[str, Field(max_length=600)] | None = None
    queixa: TextoCurto | None = None
    motivo: TextoLongo | None = None
    respostas: list[dict] = Field(default_factory=list, max_length=100)
    mensagem: TextoLongo | None = None
    unidade: dict | None = None
    alternativas: list[dict] = Field(default_factory=list, max_length=6)
    autocuidado: dict | None = None
    contactos: dict | None = None
    gerado_em: Annotated[str, Field(max_length=60)] | None = None
    lingua: Annotated[str, Field(max_length=8)] | None = "pt"
