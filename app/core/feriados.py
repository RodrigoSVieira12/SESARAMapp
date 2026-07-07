"""Feriados observados na Região Autónoma da Madeira.

Inclui os feriados nacionais obrigatórios e os dois feriados regionais
da RAM (1 de julho e 26 de dezembro). Os feriados móveis (Sexta-feira
Santa e Corpo de Deus) são calculados a partir da data da Páscoa, pelo
algoritmo de Butcher (calendário gregoriano).

NÃO incluído (documentado no README):
- Feriados municipais (variam por concelho, ex.: 21 de agosto no Funchal).
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
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]

MESES = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
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


def feriado_em(dia: date) -> str | None:
    """Nome do feriado nesse dia, ou None se não for feriado."""
    return feriados(dia.year).get(dia)


def tipo_de_dia(dia: date) -> str:
    """"feriado" | "sabado" | "domingo" | "dia_util".

    Um feriado que calha ao fim de semana conta como "feriado" (para
    efeitos de horários dá no mesmo: usa-se a chave "feriado", que por
    omissão está fechada, tal como o fim de semana).
    """
    if feriado_em(dia):
        return "feriado"
    if dia.weekday() == 5:
        return "sabado"
    if dia.weekday() == 6:
        return "domingo"
    return "dia_util"


def descricao_do_dia(dia: date) -> str:
    """Descrição legível para o utente, ex.:
    "sábado", "quarta-feira, feriado: Dia da Região Autónoma da Madeira".
    """
    nome_semana = DIAS_SEMANA[dia.weekday()]
    nome_feriado = feriado_em(dia)
    if nome_feriado:
        return f"{nome_semana}, feriado: {nome_feriado}"
    return nome_semana


def data_legivel(dia: date) -> str:
    """Ex.: "4 de julho"."""
    return f"{dia.day} de {MESES[dia.month]}"
