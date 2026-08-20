"""Horários de funcionamento das unidades.

Formatos suportados (campo "servicos" de cada unidade em unidades.json):

  {"tipo": "24h", "texto": "Aberto 24 horas"}

  {"tipo": "semanal",
   "texto": "Dias úteis, das 08:00 às 20:00",
   "horas": {"seg": ["08:00-20:00"], "ter": [...], ..., "dom": [],
             "feriado": []}}

Feriados: num feriado (nacional ou regional da RAM, ver feriados.py)
usa-se a chave "feriado" em vez do dia da semana. Se a chave não existir,
assume-se FECHADO — é o comportamento típico dos centros de saúde e o
lado seguro do erro. Para um serviço que abre em feriados com horário
próprio, acrescentar por exemplo "feriado": ["09:00-13:00"].

Feriados municipais (v0.14.2): quando se passa o `concelho` da unidade,
o feriado municipal desse concelho também usa a chave "feriado". Como
as urgências e o atendimento urgente são "24h" (sempre abertos) e as
consultas não têm chave "feriado" (fecham), o efeito é o esperado: no
feriado municipal fecham as consultas do concelho, mas a urgência
mantém-se aberta — igual aos feriados nacionais.

Limitação assumida (documentada): faixas horárias não podem atravessar a
meia-noite. Para "até à meia-noite" usar "08:00-23:59".
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from . import feriados

# weekday() do Python: 0 = segunda ... 6 = domingo
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def _minutos(hhmm: str) -> int:
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def _normalizar(faixa: str) -> str:
    """Tolerar travessões tipográficos escritos por engano no JSON."""
    return faixa.replace("\u2013", "-").replace("\u2014", "-")


def _chave_do_dia(dia, concelho: str | None = None) -> str:
    """Chave do dicionário "horas" a usar nessa data ("seg".."dom" ou
    "feriado"). Com `concelho`, um feriado municipal desse concelho
    também devolve "feriado" (ver feriados.py)."""
    if feriados.feriado_em(dia, concelho):
        return "feriado"
    return DIAS[dia.weekday()]


def _faixas_do_dia(horario: dict, dia, concelho: str | None = None) -> list[tuple[int, int]]:
    """Faixas (início, fim) em minutos para essa data, já ordenadas."""
    brutas = horario.get("horas", {}).get(_chave_do_dia(dia, concelho), [])
    faixas = []
    for faixa in brutas:
        inicio, fim = _normalizar(faixa).split("-")
        faixas.append((_minutos(inicio), _minutos(fim)))
    return sorted(faixas)


def esta_aberto(horario: dict, quando: datetime, concelho: str | None = None) -> bool:
    """Devolve True se o serviço está aberto no instante `quando`.

    `concelho` (opcional) é o concelho da unidade: quando dado, um
    feriado municipal desse concelho fecha os serviços não-24h, tal como
    um feriado nacional (ver feriados.py e _chave_do_dia)."""
    tipo = horario.get("tipo")

    if tipo == "24h":
        return True

    if tipo == "semanal":
        agora = quando.hour * 60 + quando.minute
        return any(
            inicio <= agora < fim
            for inicio, fim in _faixas_do_dia(horario, quando.date(), concelho)
        )

    # Tipo desconhecido: por segurança, considerar fechado.
    return False


def proxima_abertura(
    horario: dict, quando: datetime, max_dias: int = 21, concelho: str | None = None
) -> datetime | None:
    """Próximo instante de abertura estritamente depois de `quando`.

    Devolve None para serviços 24h (nunca fecham) e quando não há
    nenhuma abertura nos próximos `max_dias` dias (horário vazio).
    O resultado tem o mesmo tzinfo de `quando` (ou nenhum, se for naive).
    Com `concelho`, os feriados municipais desse concelho são saltados
    (a unidade não reabre num feriado municipal), tal como os nacionais.
    """
    if horario.get("tipo") != "semanal":
        return None

    agora = quando.hour * 60 + quando.minute
    for delta in range(0, max_dias + 1):
        dia = (quando + timedelta(days=delta)).date()
        for inicio, _fim in _faixas_do_dia(horario, dia, concelho):
            if delta == 0 and inicio <= agora:
                continue  # essa abertura já passou (ou é agora mesmo)
            return datetime.combine(dia, time(inicio // 60, inicio % 60), tzinfo=quando.tzinfo)
    return None
