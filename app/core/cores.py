"""Cores da Triagem de Manchester (usada nas urgências em Portugal).

Cada cor tem um tempo-alvo de observação inicial. Estes valores são os
tempos de referência do protocolo; servem para informar o utente do que
esperar, não são uma promessa do serviço.
"""

CORES: dict[str, dict] = {
    "vermelho": {
        "id": "vermelho",
        "nome": "Vermelho",
        "nome_en": "Red",
        "classificacao": "Emergente",
        "classificacao_en": "Immediate",
        "tempo_alvo": "Atendimento imediato",
        "tempo_alvo_en": "Immediate care",
        "hex": "#D32F2F",
        "descricao": "Situação com risco de vida. Ligue 112 sem perder tempo.",
        "descricao_en": "Life-threatening situation. Call 112 without delay.",
    },
    "laranja": {
        "id": "laranja",
        "nome": "Laranja",
        "nome_en": "Orange",
        "classificacao": "Muito urgente",
        "classificacao_en": "Very urgent",
        "tempo_alvo": "Observação em cerca de 10 minutos",
        "tempo_alvo_en": "Assessment within about 10 minutes",
        "hex": "#EF6C00",
        "descricao": "Situação muito urgente. Dirija-se já a uma urgência.",
        "descricao_en": "Very urgent situation. Go to an emergency department now.",
    },
    "amarelo": {
        "id": "amarelo",
        "nome": "Amarelo",
        "nome_en": "Yellow",
        "classificacao": "Urgente",
        "classificacao_en": "Urgent",
        "tempo_alvo": "Observação em cerca de 60 minutos",
        "tempo_alvo_en": "Assessment within about 60 minutes",
        "hex": "#F9A825",
        "descricao": "Situação urgente. Deve ser observado hoje, numa urgência ou atendimento urgente.",
        "descricao_en": "Urgent situation. You should be seen today, at an emergency department or urgent care unit.",
    },
    "verde": {
        "id": "verde",
        "nome": "Verde",
        "nome_en": "Green",
        "classificacao": "Pouco urgente",
        "classificacao_en": "Less urgent",
        "tempo_alvo": "Observação em cerca de 120 minutos",
        "tempo_alvo_en": "Assessment within about 120 minutes",
        "hex": "#2E7D32",
        "descricao": "Situação pouco urgente. O centro de saúde é normalmente a melhor opção.",
        "descricao_en": "Less urgent situation. A health centre is usually the best option.",
    },
    "azul": {
        "id": "azul",
        "nome": "Azul",
        "nome_en": "Blue",
        "classificacao": "Não urgente",
        "classificacao_en": "Non-urgent",
        "tempo_alvo": "Observação em cerca de 240 minutos",
        "tempo_alvo_en": "Assessment within about 240 minutes",
        "hex": "#1565C0",
        "descricao": "Situação não urgente. Autocuidado e aconselhamento são normalmente suficientes.",
        "descricao_en": "Non-urgent situation. Self-care and advice are usually enough.",
    },
}

CONTACTOS = {
    "emergencia": {"nome": "Emergência médica", "numero": "112"},
    "sns24": {"nome": "SNS 24 (aconselhamento)", "numero": "808 24 24 24"},
}


def info_cor(cor: str) -> dict:
    if cor not in CORES:
        raise KeyError(f"Cor de triagem desconhecida: {cor!r}")
    return CORES[cor]
