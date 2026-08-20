"""Textos do encaminhamento: frases PT/EN mostradas ao utente.

Extraído de app/core/routing.py na v0.13.1 para manter a responsabilidade
única de cada módulo (ver docs/adr/0010-divisao-routing.md):
- routing.py DECIDE (política, candidatas, escolha da unidade);
- routing_textos.py FORMATA (horários, chegada, próxima abertura,
  contexto do dia — nas duas línguas);
- motivos.py EXPLICA (a lista "porquê esta recomendação?", v0.13.1).

Nada aqui toma decisões: são funções puras de texto, fáceis de rever na
sessão de validação clínica e de testar isoladamente. Os nomes com
underscore mantêm-se por compatibilidade (o routing reexporta-os e os
testes históricos usam-nos).
"""

from __future__ import annotations

from datetime import datetime

from . import feriados

# Nota mostrada no Porto Santo nas cores mais graves (regra da ilha).
NOTA_TRANSFERENCIA_PORTO_SANTO = (
    " Em situações muito graves, a transferência para o Hospital "
    "Dr. Nélio Mendonça é organizada pelos serviços de emergência, "
    "se necessário por via aérea."
)

NOTA_TRANSFERENCIA_PORTO_SANTO_EN = (
    " In very serious situations, the transfer to Hospital "
    "Dr. Nélio Mendonça is arranged by the emergency services, "
    "by air if necessary."
)

_DIAS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _texto_proxima_abertura(abre: datetime, agora: datetime) -> str:
    """Ex.: "abre hoje às 14:00", "abre segunda-feira às 08:00",
    "abre a 28 de dezembro (segunda-feira) às 08:00"."""
    dias_de_diferenca = (abre.date() - agora.date()).days
    hora = abre.strftime("%H:%M")
    if dias_de_diferenca == 0:
        return f"abre hoje às {hora}"
    if dias_de_diferenca == 1:
        return f"abre amanhã às {hora}"
    nome_dia = feriados.DIAS_SEMANA[abre.weekday()]
    if dias_de_diferenca < 7:
        return f"abre {nome_dia} às {hora}"
    return f"abre a {feriados.data_legivel(abre.date())} ({nome_dia}) às {hora}"


def _texto_proxima_abertura_en(abre: datetime, quando: datetime) -> str:
    """Versão inglesa de "abre segunda-feira às 08:00" (para o modo EN)."""
    hora = f"{abre.hour:02d}:{abre.minute:02d}"
    if abre.date() == quando.date():
        return f"opens today at {hora}"
    if (abre.date() - quando.date()).days == 1:
        return f"opens tomorrow at {hora}"
    return f"opens on {_DIAS_EN[abre.weekday()]} at {hora}"


# Tradução dos textos de horário das unidades (que vivem em unidades.json em
# português). São formulaicos, por isso uma substituição de vocabulário chega,
# em vez de guardar um texto_en por serviço em dezenas de unidades. As horas
# (08:00-17:00) mantêm-se. Ordem importa: termos mais longos primeiro.
_HORARIO_SUBS = [
    ("Dias úteis", "Weekdays"),
    ("Segundas-Feiras", "Mondays"),
    ("Sábados", "Saturdays"),
    ("Sábado", "Saturday"),
    ("Segundas", "Mondays"),
    ("Terças", "Tuesdays"),
    ("Quartas", "Wednesdays"),
    ("Quintas", "Thursdays"),
    ("Sextas", "Fridays"),
    ("enfermagem, com marcação prévia", "nursing, by prior appointment"),
    ("com marcação prévia", "by prior appointment"),
    ("enfermagem", "nursing"),
    ("Urgência aberta 24 horas", "Open 24 hours"),
    (" e ", " and "),
    (" a ", " to "),
    ("das ", ""),
    (" às ", " to "),
]


def _horario_en(texto: str) -> str:
    """Versão inglesa de um texto de horário (ex.: "Dias úteis, 08:00-20:00")."""
    resultado = texto
    for pt, en in _HORARIO_SUBS:
        resultado = resultado.replace(pt, en)
    return resultado


def _descricao_dia_en(dia, concelho: str | None = None) -> str:
    """Versão inglesa de descricao_do_dia (ex.: "Wednesday", "Saturday, holiday: …").
    Com `concelho`, inclui o feriado municipal desse concelho (o nome
    fica em português, como nos feriados nacionais no modo EN)."""
    nome_semana = _DIAS_EN[dia.weekday()]
    nome_feriado = feriados.feriado_em(dia, concelho)
    if nome_feriado:
        return f"{nome_semana}, holiday: {nome_feriado}"
    return nome_semana


def _texto_chegada(u: dict) -> str:
    """ "2.1 km, ~9 min de carro" — ou só os km, sem estimativa. Com uma
    medição (v0.11.3) há distância POR ESTRADA, e é essa que se mostra."""
    tv = u.get("tempo_viagem") or {}
    minutos = tv.get("minutos")
    if minutos is None:
        return f"{u['distancia_km']} km"
    km_estrada = tv.get("distancia_km")
    if km_estrada is not None:
        return f"{km_estrada} km por estrada, ~{minutos} min de carro"
    return f"{u['distancia_km']} km, ~{minutos} min de carro"


def _texto_chegada_en(u: dict) -> str:
    tv = u.get("tempo_viagem") or {}
    minutos = tv.get("minutos")
    if minutos is None:
        return f"{u['distancia_km']} km"
    km_estrada = tv.get("distancia_km")
    if km_estrada is not None:
        return f"{km_estrada} km by road, ~{minutos} min by car"
    return f"{u['distancia_km']} km, ~{minutos} min by car"


def _contexto_do_dia(quando: datetime, concelho: str | None = None) -> str:
    """Início de frase que explica PORQUÊ os centros estão fechados.
    Com `concelho`, reconhece também o feriado municipal desse concelho."""
    dia = quando.date()
    tipo = feriados.tipo_de_dia(dia, concelho)
    if tipo == "feriado":
        return f"Hoje é feriado ({feriados.feriado_em(dia, concelho)}) e "
    if tipo == "sabado":
        return "É sábado e "
    if tipo == "domingo":
        return "É domingo e "
    return "A esta hora, "


def _contexto_do_dia_en(quando: datetime, concelho: str | None = None) -> str:
    """Versão inglesa de _contexto_do_dia."""
    dia = quando.date()
    tipo = feriados.tipo_de_dia(dia, concelho)
    if tipo == "feriado":
        return f"Today is a public holiday ({feriados.feriado_em(dia, concelho)}) and "
    if tipo == "sabado":
        return "It's Saturday and "
    if tipo == "domingo":
        return "It's Sunday and "
    return "At this time, "
