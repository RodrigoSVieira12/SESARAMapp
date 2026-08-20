"""Modelos de RESPOSTA dos endpoints principais (Pydantic, v0.16.2).

Até aqui os endpoints devolviam `dict`, e o /docs mostrava os pedidos
mas não os formatos de resposta — meio contrato. Estes modelos fecham a
outra metade: `/api/triagem`, `/api/encaminhamento` e
`/api/integracao/triagem` passam a declarar `response_model`, por isso a
documentação interativa mostra o schema completo do que sai, e o FastAPI
valida que a resposta real lhe obedece.

Duas decisões deliberadas, para que documentar não parta nada:

1. **`extra = "allow"` em quase tudo.** Sem isto, uma chave nova posta
   pelo routing (ou por dados novos) seria SILENCIOSAMENTE apagada da
   resposta pelo response_model — perda de dados invisível, o pior tipo
   de bug. Com `allow`, o que o código devolve a mais passa na mesma; o
   modelo documenta o que se garante, não censura o resto.
2. **Campos opcionais com omissão em vez de obrigatórios.** Um campo
   obrigatório em falta faria o FastAPI responder 500 (erro de validação
   da resposta). Como várias chaves só existem nalguns ramos (a
   `politica` não aparece no verde, a `nota` só no vermelho, o
   `tempo_espera` só quando o cache o tem), quase tudo é opcional. Os
   endpoints usam `response_model_exclude_unset=True`, por isso o
   formato no fio fica EXATAMENTE o de antes: as chaves que o routing
   não pôs continuam ausentes (e não `null`) — verificado por testes
   (tests/test_v16_2.py).

A estrutura espelha o que `routing.decidir_encaminhamento` e o
`TriageEngine` constroem; se acrescentares uma chave lá, acrescenta-a
aqui (o teste de formato apanha esquecimentos nos ramos que cobre).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .schemas import Cor


class _Flexivel(BaseModel):
    """Base comum: campos extra passam (ver o ponto 1 do cabeçalho)."""

    model_config = ConfigDict(extra="allow")


# ------------------------------------------------------------------ #
# Blocos partilhados                                                  #
# ------------------------------------------------------------------ #


class CorInfo(_Flexivel):
    """Ficha da cor de Manchester (app/core/cores.py)."""

    id: str | None = None
    nome: str | None = None
    nome_en: str | None = None
    classificacao: str | None = None
    classificacao_en: str | None = None
    tempo_alvo: str | None = None
    tempo_alvo_en: str | None = None
    hex: str | None = None
    descricao: str | None = None
    descricao_en: str | None = None


class Contacto(_Flexivel):
    nome: str | None = None
    numero: str | None = None


class Contactos(_Flexivel):
    emergencia: Contacto | None = None
    sns24: Contacto | None = None


class ItemAconselhamento(_Flexivel):
    """Um conselho da tabela: o texto clínico e, se existir e (em
    produção) estiver validada, a reescrita leiga PT/EN. O frontend só
    mostra itens com `texto_utente` (static/js/nucleo.js)."""

    texto: str | None = None
    texto_utente: str | None = None
    texto_utente_en: str | None = None
    validado: bool | None = None


class BlocoAconselhamento(_Flexivel):
    itens: list[ItemAconselhamento] = []


class PerguntaTriagem(_Flexivel):
    """A próxima pergunta de sim/não a fazer ao utente."""

    id: str | None = None
    texto: str | None = None
    texto_en: str | None = None


class ProgressoTriagem(_Flexivel):
    respondidas: int | None = None
    maximo: int | None = None


class ResultadoTriagem(_Flexivel):
    """O desfecho da triagem: a cor e o porquê (v0.14: discriminadores)."""

    cor: Cor | None = None
    motivo: str | None = None
    motivo_en: str | None = None
    prioridade: str | None = None
    discriminador: str | None = None
    nota: str | None = None
    nota_en: str | None = None
    destino: str | None = None
    cor_info: CorInfo | None = None
    aconselhamento: BlocoAconselhamento | None = None


class TriagemResponse(_Flexivel):
    """Resposta de POST /api/triagem: OU a próxima pergunta, OU o resultado."""

    tipo: str | None = None  # "pergunta" | "resultado"
    queixa: str | None = None
    pergunta: PerguntaTriagem | None = None
    progresso: ProgressoTriagem | None = None
    resultado: ResultadoTriagem | None = None


# ------------------------------------------------------------------ #
# Encaminhamento                                                      #
# ------------------------------------------------------------------ #


class TempoViagem(_Flexivel):
    """Estimativa por estrada (app/core/viagem.py): minutos + método
    (medido | rede | osrm)."""

    minutos: int | None = None
    metodo: str | None = None


class TempoEspera(_Flexivel):
    """Bloco de espera em tempo real (app/core/espera.py), quando o
    cache o tem; no hospital, `ambito` distingue a coluna da cor do
    agregado geral."""

    ambito: str | None = None
    minutos: int | None = None
    em_espera: int | None = None
    atendidos: int | None = None
    fonte: str | None = None
    atualizado_no_site: str | None = None


class UnidadeResumo(_Flexivel):
    """Uma unidade de saúde pronta a mostrar: estado, viagem e espera."""

    id: str | None = None
    nome: str | None = None
    tipo: str | None = None
    concelho: str | None = None
    ilha: str | None = None
    morada: str | None = None
    telefone: str | None = None
    lat: float | None = None
    lng: float | None = None
    notas: str | None = None
    dados_confirmados: bool | None = None
    distancia_km: float | None = None
    tempo_viagem: TempoViagem | None = None
    aberta_agora: bool | None = None
    servicos_abertos: list[str] = []
    horarios: dict[str, str] = {}
    horarios_en: dict[str, str] = {}
    proxima_abertura: str | None = None
    proxima_abertura_texto: str | None = None
    proxima_abertura_texto_en: str | None = None
    tempo_espera: TempoEspera | None = None


class EsperaInfo(_Flexivel):
    disponivel: bool | None = None
    desatualizado: bool | None = None
    obtido_em: str | None = None


class ViagemInfo(_Flexivel):
    disponivel: bool | None = None
    metodo: str | None = None
    descricao: str | None = None
    descricao_en: str | None = None


class DiaInfo(_Flexivel):
    """Contexto do dia do cálculo (útil, fim de semana, feriado)."""

    tipo: str | None = None
    feriado: str | None = None
    descricao: str | None = None
    descricao_en: str | None = None


class PoliticaInfo(_Flexivel):
    """Que política de destino se aplicou e de onde veio (v0.12.1)."""

    destino: str | None = None
    fonte: str | None = None
    aplicada: bool | None = None
    recuo: bool | None = None


class Motivo(_Flexivel):
    """Um fator da lista 'Porquê esta recomendação?' (v0.13.1)."""

    tipo: str | None = None
    texto: str | None = None
    texto_en: str | None = None


class Autocuidado(_Flexivel):
    """Bloco de autocuidado (app/data/autocuidado.json), no verde e azul."""

    titulo: str | None = None
    titulo_en: str | None = None
    intro: str | None = None
    intro_en: str | None = None
    fazer: list[str] = []
    fazer_en: list[str] = []
    evitar: list[str] = []
    evitar_en: list[str] = []
    alerta_titulo: str | None = None
    alerta_titulo_en: str | None = None
    alerta: list[str] = []
    alerta_en: list[str] = []


class EncaminhamentoResponse(_Flexivel):
    """Resposta de POST /api/encaminhamento: para onde ir e porquê."""

    cor: Cor | None = None
    cor_info: CorInfo | None = None
    ilha: str | None = None
    contactos: Contactos | None = None
    gerado_em: str | None = None
    espera_info: EsperaInfo | None = None
    viagem_info: ViagemInfo | None = None
    dia: DiaInfo | None = None
    acao: str | None = None  # ligar_112 | ir_unidade | contactar_sns24 | autocuidado
    mensagem: str | None = None
    mensagem_en: str | None = None
    unidade: UnidadeResumo | None = None
    alternativas: list[UnidadeResumo] = []
    centro_saude_proximo: UnidadeResumo | None = None
    reordenado_por_espera: bool | None = None
    politica: PoliticaInfo | None = None
    autocuidado: Autocuidado | None = None
    motivos: list[Motivo] = []


class IntegracaoTriagemResponse(_Flexivel):
    """Resposta de POST /api/integracao/triagem: triagem + encaminhamento
    num só pacote (ver docs/INTEGRACAO.md)."""

    tipo: str | None = None  # "pergunta" | "resultado"
    queixa: str | None = None
    pergunta: PerguntaTriagem | None = None
    progresso: ProgressoTriagem | None = None
    resultado: ResultadoTriagem | None = None
    encaminhamento: EncaminhamentoResponse | None = None
