"""Explicabilidade do encaminhamento (v0.13.1): a lista "porquê?".

A recomendação deixou de ser só "vá a X": cada resposta de
/api/encaminhamento passa a incluir `motivos`, a lista dos fatores que
levaram àquela decisão, pela ordem em que pesaram. A interface mostra-a
num bloco "Porquê esta recomendação?" e um clínico consegue auditar a
decisão sem ler código (ver docs/adr/0010-explicabilidade.md).

Formato de cada motivo (a mesma convenção *_en do resto do projeto,
escolhida no frontend por campo()):

    {"tipo": "espera", "texto": "…", "texto_en": "…"}

O `tipo` é estável e serve para testes e para a interface (ícones,
ordenação); o texto é para pessoas. Este módulo só FORMATA factos que o
routing já decidiu — não toma decisões nem repete lógica. Regra de ouro
herdada do resto do projeto: nunca inventar números; um motivo só entra
quando o dado existe mesmo.
"""

from __future__ import annotations

from datetime import datetime

from .cores import info_cor
from .routing_textos import _contexto_do_dia, _contexto_do_dia_en


def _motivo(tipo: str, texto: str, texto_en: str) -> dict:
    return {"tipo": tipo, "texto": texto, "texto_en": texto_en}


# ------------------------------------------------------------- a cor -- #


def cor(cor_id: str) -> dict:
    """Primeiro motivo de todos: a prioridade estimada pela triagem."""
    info = info_cor(cor_id)
    return _motivo(
        "cor",
        f"Prioridade estimada: {info['nome'].lower()} "
        f"({info['classificacao'].lower()}); {info['tempo_alvo'].lower()}.",
        f"Estimated priority: {info['nome_en'].lower()} "
        f"({info['classificacao_en'].lower()}); {info['tempo_alvo_en'].lower()}.",
    )


# ----------------------------------------------------------- política -- #


def politica_hospital(cor_id: str) -> dict:
    """Hospital direto por configuração (app/data/encaminhamento.json)."""
    nome = info_cor(cor_id)["nome"].lower()
    nome_en = info_cor(cor_id)["nome_en"].lower()
    return _motivo(
        "politica",
        f"Política de encaminhamento do SESARAM: casos classificados como "
        f"{nome} seguem "
        "diretamente para a urgência do hospital de referência "
        "(regra editável em app/data/encaminhamento.json, por validar).",
        f"SESARAM referral policy: cases classified as {nome_en} go "
        "directly to the "
        "reference hospital's emergency department (editable rule "
        "in "
        "app/data/encaminhamento.json, pending validation).",
    )


def politica_fluxograma() -> dict:
    """Amarelo com destino definido no próprio desfecho do fluxograma."""
    return _motivo(
        "politica",
        "O desfecho deste fluxograma define o atendimento urgente como "
        "destino adequado (exceção prevista nas regras clínicas).",
        "This flowchart outcome defines urgent care as the appropriate "
        "destination (an exception provided for in the clinical rules).",
    )


def politica_proximidade() -> dict:
    """Comportamento por proximidade (cor fora da política de hospital)."""
    return _motivo(
        "politica",
        "Encaminhamento por proximidade: recomenda-se a unidade adequada "
        "aberta que fica a menos tempo de si.",
        "Proximity-based referral: the suitable open unit closest to you "
        "in travel time is recommended.",
    )


def recuo_hospital() -> dict:
    """Hospital configurado sem urgência aberta nos dados: recuo seguro."""
    return _motivo(
        "recuo",
        "Nota: o hospital de referência configurado não tem urgência "
        "aberta nos dados atuais; por segurança, recomendamos a unidade "
        "adequada aberta mais próxima.",
        "Note: the configured reference hospital has no open emergency "
        "department in the current data; to be safe, we recommend the "
        "nearest suitable open unit.",
    )


# ------------------------------------------------- a unidade escolhida -- #


def unidade_aberta(u: dict) -> dict | None:
    """A unidade recomendada está aberta agora (com o horário em causa)."""
    servicos_abertos = u.get("servicos_abertos") or []
    if not servicos_abertos:
        return None
    servico = servicos_abertos[0]
    horario = (u.get("horarios") or {}).get(servico, "")
    horario_en = (u.get("horarios_en") or {}).get(servico, "")
    detalhe = f" ({horario.lower()})" if horario else ""
    detalhe_en = f" ({horario_en.lower()})" if horario_en else ""
    return _motivo(
        "aberta",
        f"{u['nome']} está aberto neste momento{detalhe}.",
        f"{u['nome']} is open right now{detalhe_en}.",
    )


def proximidade(u: dict) -> dict | None:
    """Tempo de viagem estimado (ou distância, sem estimativa)."""
    tv = u.get("tempo_viagem") or {}
    minutos = tv.get("minutos")
    km = tv.get("distancia_km", u.get("distancia_km"))
    if minutos is not None:
        return _motivo(
            "viagem",
            f"Fica a cerca de {minutos} min de carro de si ({km} km).",
            f"It is about {minutos} min by car from you ({km} km).",
        )
    if u.get("distancia_km") is not None:
        return _motivo(
            "viagem",
            f"Fica a {u['distancia_km']} km de si (sem estimativa de " "tempo por estrada).",
            f"It is {u['distancia_km']} km from you (no road-time " "estimate available).",
        )
    return None


def espera_atual(u: dict) -> dict | None:
    """Tempo de espera real da unidade (SESARAM), quando existe."""
    te = u.get("tempo_espera") or {}
    minutos = te.get("minutos")
    if minutos is None:
        return None
    if te.get("cor"):
        return _motivo(
            "espera",
            f"Tempo de espera atual para a sua cor: cerca de {minutos} min "
            "(dados públicos do SESARAM).",
            f"Current waiting time for your colour: about {minutos} min " "(SESARAM public data).",
        )
    return _motivo(
        "espera",
        f"Tempo de espera atual: cerca de {minutos} min " "(dados públicos do SESARAM).",
        f"Current waiting time: about {minutos} min " "(SESARAM public data).",
    )


def troca_por_espera(troca: dict, principal: dict) -> dict:
    """A regra experimental preferiu uma unidade um pouco mais longe."""
    preterida = troca["preterida"]
    return _motivo(
        "troca",
        f"{preterida['nome']} fica mais perto ({preterida['distancia_km']} km), "
        f"mas estimamos ~{troca['total_preterida_min']} min no total aí "
        f"(viagem + espera) contra ~{troca['total_escolhida_min']} min em "
        f"{principal['nome']} (regra experimental, por validar).",
        f"{preterida['nome']} is closer ({preterida['distancia_km']} km), "
        f"but we estimate ~{troca['total_preterida_min']} min in total there "
        f"(travel + wait) versus ~{troca['total_escolhida_min']} min at "
        f"{principal['nome']} (experimental rule, pending validation).",
    )


# ----------------------------------------------------- contexto do dia -- #


def emergencia_112() -> dict:
    return _motivo(
        "emergencia",
        "Situação de emergência: a resposta certa é o 112, que ativa os "
        "meios adequados e transporta para o hospital.",
        "Emergency situation: the right response is 112, which dispatches "
        "the appropriate resources and transports you to hospital.",
    )


def ilha_porto_santo() -> dict:
    return _motivo(
        "ilha",
        "Regra da ilha: no Porto Santo a recomendação é sempre a unidade "
        "local; a orientação nunca atravessa o mar.",
        "Island rule: on Porto Santo the recommendation is always the "
        "local unit; guidance never crosses the sea.",
    )


def centros_fechados(quando: datetime, concelho: str | None = None) -> dict:
    """Fim de semana, feriado ou noite: porque não há consulta aberta.
    Com `concelho`, reconhece o feriado municipal desse concelho."""
    return _motivo(
        "dia",
        _contexto_do_dia(quando, concelho) + "os centros de saúde estão fechados.",
        _contexto_do_dia_en(quando, concelho) + "the health centres are closed.",
    )


def verde_evitar_urgencia() -> dict:
    return _motivo(
        "adequacao",
        "Situação pouco urgente: o local adequado é um centro de saúde; "
        "evitar a urgência hospitalar liberta-a para os casos graves e "
        "poupa-lhe horas de espera.",
        "Less urgent situation: the right place is a health centre; "
        "avoiding the hospital emergency department frees it up for "
        "serious cases and saves you hours of waiting.",
    )


def verde_duas_opcoes() -> dict:
    return _motivo(
        "opcoes",
        "Numa situação pouco urgente, vigiar em casa com o apoio do "
        "SNS 24 é uma alternativa razoável a deslocar-se hoje.",
        "In a non-urgent situation, watching and waiting at home with "
        "SNS 24 support is a reasonable alternative to travelling today.",
    )


def sem_urgencias_abertas() -> dict:
    return _motivo(
        "indisponivel",
        "Não foi possível encontrar uma urgência aberta perto de si nos "
        "dados atuais; por segurança, a orientação é ligar 112.",
        "We could not find an open emergency unit near you in the current "
        "data; to be safe, the guidance is to call 112.",
    )


def sem_unidades_abertas() -> dict:
    return _motivo(
        "indisponivel",
        "Não encontrámos unidades adequadas abertas perto de si; o "
        "caminho seguro é o aconselhamento pelo SNS 24.",
        "We could not find suitable open units near you; the safe path "
        "is advice through SNS 24.",
    )


def azul_autocuidado() -> dict:
    return _motivo(
        "adequacao",
        "Situação não urgente: o autocuidado em casa é adequado, com o "
        "SNS 24 e o seu centro de saúde como contactos de apoio.",
        "Non-urgent situation: self-care at home is appropriate, with "
        "SNS 24 and your health centre as support contacts.",
    )


def compilar(*itens: dict | None) -> list[dict]:
    """Junta os motivos pela ordem dada, ignorando os None (dados em
    falta) e duplicados exatos. Mantém a lista curta e sem buracos."""
    vistos: list[dict] = []
    for item in itens:
        if item is not None and item not in vistos:
            vistos.append(item)
    return vistos
