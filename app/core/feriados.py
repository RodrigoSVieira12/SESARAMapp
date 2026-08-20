"""Feriados observados na Região Autónoma da Madeira.

Inclui os feriados nacionais obrigatórios e os dois feriados regionais
da RAM (1 de julho e 26 de dezembro). Os feriados móveis (Sexta-feira
Santa e Corpo de Deus) são calculados a partir da data da Páscoa, pelo
algoritmo de Butcher (calendário gregoriano).

Feriados MUNICIPAIS (v0.14.2): cada um dos 11 concelhos tem o seu
feriado municipal e ele só se aplica às unidades DESSE concelho — ver
FERIADOS_MUNICIPAIS e feriado_municipal_em(). Ao contrário dos feriados
nacionais/regionais, um feriado municipal nunca vale "para toda a
região": as funções que os têm em conta pedem sempre o `concelho`. Tal
como nos feriados nacionais, as unidades com urgência / atendimento
urgente (horário 24h) NÃO fecham nesses dias — só as consultas e o
atendimento não-24h ficam fechados, porque o horário reutiliza a mesma
chave "feriado" (ver horarios.py). Detalhe importante dos dados: o
Centro de Saúde do Santo da Serra tem concelho "Machico" em
unidades.json, por isso fecha no feriado de Machico (8 de maio) e não no
de Santa Cruz — comportamento pretendido.

NÃO incluído (documentado no README):
- Tolerâncias de ponto (Carnaval, 24 e 31 de dezembro), que não são
  feriados oficiais mas podem afetar horários. A confirmar com o SESARAM
  se os centros de saúde encerram nesses dias.

Como o resto do projeto, isto é lógica determinística e testável: ver
tests/test_feriados_e_dias.py, que verifica datas de Páscoa conhecidas.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

DIAS_SEMANA = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]

MESES = [
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Butcher, calendário gregoriano)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 (nome do algoritmo)
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


@lru_cache(maxsize=16)
def feriados(ano: int) -> dict[date, str]:
    """Feriados do ano: {data: nome}. Nacionais + regionais da RAM."""
    p = pascoa(ano)
    lista = {
        date(ano, 1, 1): "Ano Novo",
        p - timedelta(days=2): "Sexta-feira Santa",
        p: "Domingo de Páscoa",
        date(ano, 4, 25): "Dia da Liberdade",
        date(ano, 5, 1): "Dia do Trabalhador",
        p + timedelta(days=60): "Corpo de Deus",
        date(ano, 6, 10): "Dia de Portugal",
        date(ano, 7, 1): "Dia da Região Autónoma da Madeira",
        date(ano, 8, 15): "Assunção de Nossa Senhora",
        date(ano, 10, 5): "Implantação da República",
        date(ano, 11, 1): "Dia de Todos os Santos",
        date(ano, 12, 1): "Restauração da Independência",
        date(ano, 12, 8): "Imaculada Conceição",
        date(ano, 12, 25): "Natal",
        date(ano, 12, 26): "Primeira Oitava (feriado regional)",
    }
    return lista


# Feriados municipais dos 11 concelhos da RAM: concelho -> (mês, dia,
# nome). Aplicam-se SÓ às unidades desse concelho (o `concelho` de cada
# unidade em app/data/unidades.json). As datas são fixas (não móveis).
# O nome é guardado por extenso para controlar a preposição de cada
# concelho ("do Funchal", "da Calheta", "de Machico", …).
FERIADOS_MUNICIPAIS: dict[str, tuple[int, int, str]] = {
    "Funchal": (8, 21, "Feriado Municipal do Funchal"),
    "Santa Cruz": (1, 15, "Feriado Municipal de Santa Cruz"),
    "Machico": (5, 8, "Feriado Municipal de Machico"),
    "Santana": (5, 25, "Feriado Municipal de Santana"),
    "Calheta": (6, 24, "Feriado Municipal da Calheta"),
    "Ponta do Sol": (9, 8, "Feriado Municipal da Ponta do Sol"),
    "Ribeira Brava": (6, 29, "Feriado Municipal da Ribeira Brava"),
    "Câmara de Lobos": (10, 4, "Feriado Municipal de Câmara de Lobos"),
    "São Vicente": (1, 22, "Feriado Municipal de São Vicente"),
    "Porto Moniz": (7, 22, "Feriado Municipal do Porto Moniz"),
    "Porto Santo": (6, 24, "Feriado Municipal do Porto Santo"),
}


def feriado_municipal_em(dia: date, concelho: str | None) -> str | None:
    """Nome do feriado municipal desse concelho nesse dia, ou None.

    Só devolve algo quando `concelho` é dado E a data bate certo com o
    feriado municipal desse concelho. Sem concelho (ou concelho sem
    feriado na tabela), devolve None — os feriados municipais nunca se
    aplicam "a toda a região".
    """
    if not concelho:
        return None
    entrada = FERIADOS_MUNICIPAIS.get(concelho)
    if entrada is None:
        return None
    mes, dia_mes, nome = entrada
    if dia.month == mes and dia.day == dia_mes:
        return nome
    return None


def feriado_em(dia: date, concelho: str | None = None) -> str | None:
    """Nome do feriado nesse dia, ou None se não for feriado.

    Com `concelho`, inclui também o feriado municipal desse concelho. Se
    um feriado nacional/regional e um municipal calharem no mesmo dia, o
    nacional/regional tem precedência no nome (o resultado — fechado — é
    o mesmo).
    """
    nacional = feriados(dia.year).get(dia)
    if nacional is not None:
        return nacional
    return feriado_municipal_em(dia, concelho)


def tipo_de_dia(dia: date, concelho: str | None = None) -> str:
    """ "feriado" | "sabado" | "domingo" | "dia_util".

    Um feriado que calha ao fim de semana conta como "feriado" (para
    efeitos de horários dá no mesmo: usa-se a chave "feriado", que por
    omissão está fechada, tal como o fim de semana). Com `concelho`, um
    feriado municipal desse concelho também conta como "feriado".
    """
    if feriado_em(dia, concelho):
        return "feriado"
    if dia.weekday() == 5:
        return "sabado"
    if dia.weekday() == 6:
        return "domingo"
    return "dia_util"


def descricao_do_dia(dia: date, concelho: str | None = None) -> str:
    """Descrição legível para o utente, ex.:
    "sábado", "quarta-feira, feriado: Dia da Região Autónoma da Madeira".
    Com `concelho`, um feriado municipal desse concelho aparece na
    descrição (ex.: "quinta-feira, feriado: Feriado Municipal do Funchal").
    """
    nome_semana = DIAS_SEMANA[dia.weekday()]
    nome_feriado = feriado_em(dia, concelho)
    if nome_feriado:
        return f"{nome_semana}, feriado: {nome_feriado}"
    return nome_semana


def data_legivel(dia: date) -> str:
    """Ex.: "4 de julho"."""
    return f"{dia.day} de {MESES[dia.month]}"
