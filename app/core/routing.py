"""Encaminhamento: dada a cor de triagem, a localização do utente e a
hora atual, decidir PARA ONDE o utente deve ir.

Separar isto do motor de triagem é deliberado:
- a triagem responde "quão urgente é?" (decisão clínica);
- o encaminhamento responde "onde e quando?" (decisão logística:
  proximidade, horários — com fins de semana e feriados —, e a ILHA
  onde o utente está).

Decisões desta versão (todas a validar clinicamente com o SESARAM):
1. Vermelho, laranja e amarelo consideram QUALQUER urgência aberta
   (hospitalar ou atendimento urgente 24h dos centros de saúde). Assim,
   um laranja na Calheta é orientado para a urgência aberta da Calheta
   em vez de atravessar a ilha. Para laranja, o hospital aparece sempre
   também (como principal ou como alternativa).
2. Regra da ilha: as recomendações nunca atravessam o mar. No Porto
   Santo, todas as cores apontam para a unidade local; nas cores mais
   graves acrescenta-se a nota de que a transferência para o hospital,
   se necessária, é organizada pelos serviços de emergência.
3. (v0.11) "Mais próxima" passou a significar mais próxima EM TEMPO DE
   VIAGEM, não em linha reta: as candidatas são ordenadas pela
   estimativa por estrada (app/core/viagem.py), com a distância como
   desempate. Na Madeira isto muda decisões reais — do Curral das
   Freiras, a unidade "mais perto" no mapa fica do outro lado da serra.
4. No verde, a mensagem depende do dia e da hora:
   - com consulta aberta num centro de saúde → recomenda-se essa;
   - ao fim de semana, feriado ou à noite (só atendimentos urgentes
     abertos) → apresentam-se DUAS opções razoáveis: vigiar em casa com
     o apoio do SNS 24, ou ser observado hoje no atendimento urgente;
   - em qualquer caso o verde e o azul incluem um bloco de autocuidado
     (ver TEXTOS_AUTOCUIDADO), porque "esperar em casa" é muitas vezes
     uma opção legítima numa situação pouco urgente.
5. Em caso de dúvida, o sistema erra por excesso de urgência.
"""

from __future__ import annotations

from datetime import datetime

from . import espera, feriados, geo, horarios, unidades, viagem
from .cores import CONTACTOS, info_cor

try:
    from zoneinfo import ZoneInfo

    FUSO_MADEIRA = ZoneInfo("Atlantic/Madeira")
except Exception:  # pragma: no cover - ex.: Windows sem o pacote tzdata
    FUSO_MADEIRA = None


def agora_na_madeira() -> datetime:
    if FUSO_MADEIRA is not None:
        return datetime.now(FUSO_MADEIRA)
    return datetime.now()


# Que tipos de serviço servem cada cor. NOTA CLÍNICA: mapeamento a
# validar pela equipa do SESARAM (ver docstring, ponto 1).
SERVICOS_POR_COR: dict[str, list[str]] = {
    "vermelho": ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"],
    "laranja": ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"],
    "amarelo": ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"],
    "verde": ["atendimento_urgente", "consulta_aberta"],
    "azul": ["consulta_aberta", "atendimento_urgente"],
}

SERVICOS_URGENCIA = ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"]
SERVICOS_HOSPITALARES = ["urgencia_polivalente", "urgencia_basica"]

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

# Textos fixos mostrados ao utente no verde e no azul. Estão aqui, num
# só sítio, para poderem ser revistos na sessão de validação clínica
# (o scripts/gerar_validacao_clinica.py inclui-os no documento).
# Textos de autocuidado: vivem em app/data/autocuidado.json para poderem
# ser revistos e corrigidos pela equipa clínica sem tocar em Python, tal
# como as regras de triagem. Estrutura por cor: titulo, intro, fazer[],
# evitar[], alerta_titulo, alerta[] — e as variantes *_en em inglês.
import json as _json
from pathlib import Path as _Path

_FICHEIRO_AUTOCUIDADO = _Path(__file__).resolve().parents[1] / "data" / "autocuidado.json"

TEXTOS_AUTOCUIDADO: dict[str, dict] = _json.loads(
    _FICHEIRO_AUTOCUIDADO.read_text(encoding="utf-8")
)["cores"]


def _ilha_do_utente(lat: float, lng: float) -> str:
    """Ilha estimada: a da unidade mais próxima do utente."""
    ordenadas = geo.ordenar_por_distancia(unidades.todas(), lat, lng)
    return ordenadas[0].get("ilha", "madeira") if ordenadas else "madeira"


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


def _resumo_unidade(
    unidade: dict,
    procurados: list[str],
    quando: datetime,
    esperas: dict | None = None,
    cor: str | None = None,
    tempo_viagem: dict | None = None,
) -> dict:
    """Versão da unidade pronta a enviar ao frontend."""
    correspondentes = [s for s in procurados if s in unidade["servicos"]]
    abertos = [
        s for s in correspondentes
        if horarios.esta_aberto(unidade["servicos"][s], quando)
    ]
    resumo = {
        "id": unidade["id"],
        "nome": unidade["nome"],
        "tipo": unidade["tipo"],
        "concelho": unidade["concelho"],
        "ilha": unidade.get("ilha", "madeira"),
        "morada": unidade.get("morada"),
        "telefone": unidade.get("telefone"),
        "lat": unidade["lat"],
        "lng": unidade["lng"],
        "notas": unidade.get("notas"),
        "dados_confirmados": unidade.get("dados_confirmados", False),
        "distancia_km": unidade["distancia_km"],
        # Estimativa por estrada (v0.11): {"minutos": int, "metodo": ...}
        # ou None (ex.: unidade noutra ilha, só possível na rede de
        # segurança de _elegiveis_na_ilha).
        "tempo_viagem": tempo_viagem,
        "aberta_agora": bool(abertos),
        "servicos_abertos": abertos,
        "horarios": {
            s: unidade["servicos"][s].get("texto", "") for s in correspondentes
        },
        "horarios_en": {
            s: _horario_en(unidade["servicos"][s].get("texto", "")) for s in correspondentes
        },
    }

    # Se está fechada, dizer quando reabre (o mais cedo entre os
    # serviços procurados) — evita o efeito "assume que é dia útil".
    if not abertos:
        aberturas = [
            horarios.proxima_abertura(unidade["servicos"][s], quando)
            for s in correspondentes
        ]
        aberturas = [a for a in aberturas if a is not None]
        if aberturas:
            abre = min(aberturas)
            resumo["proxima_abertura"] = abre.isoformat(timespec="minutes")
            resumo["proxima_abertura_texto"] = _texto_proxima_abertura(abre, quando)
            resumo["proxima_abertura_texto_en"] = _texto_proxima_abertura_en(abre, quando)

    # Tempo de espera em tempo real (SEISRAM), quando o cache o tiver.
    # No hospital, a coluna é a da própria cor do utente.
    if esperas:
        tempo_espera = espera.para_unidade(esperas, unidade["id"], cor)
        if tempo_espera:
            resumo["tempo_espera"] = tempo_espera
    return resumo


_DIAS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


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


def _descricao_dia_en(dia) -> str:
    """Versão inglesa de descricao_do_dia (ex.: "Wednesday", "Saturday, holiday: …")."""
    nome_semana = _DIAS_EN[dia.weekday()]
    nome_feriado = feriados.feriado_em(dia)
    if nome_feriado:
        return f"{nome_semana}, holiday: {nome_feriado}"
    return nome_semana


def _elegiveis_na_ilha(procurados: list[str], ilha: str) -> list[dict]:
    na_ilha = [
        u for u in unidades.com_servicos(procurados)
        if u.get("ilha", "madeira") == ilha
    ]
    # Rede de segurança: se a ilha não tiver nenhuma unidade com estes
    # serviços, é melhor sugerir algo do que nada.
    return na_ilha or unidades.com_servicos(procurados)


def _chave_ordenacao(resumo: dict) -> tuple:
    """Ordena por tempo de viagem estimado; sem estimativa, vai para o
    fim e ordena por distância (mantém determinismo e o comportamento
    antigo como recuo)."""
    minutos = (resumo.get("tempo_viagem") or {}).get("minutos")
    if minutos is None:
        return (1, 0.0, resumo["distancia_km"])
    return (0, float(minutos), resumo["distancia_km"])


def _candidatas(
    servicos: list[str],
    lat: float,
    lng: float,
    quando: datetime,
    ilha: str,
    esperas: dict | None = None,
    cor: str | None = None,
) -> list[dict]:
    elegiveis = _elegiveis_na_ilha(servicos, ilha)
    ordenadas = geo.ordenar_por_distancia(elegiveis, lat, lng)
    # v0.11: um cálculo de viagem para a lista toda (com OSRM ligado é
    # um único pedido), e a ordem passa a ser por TEMPO, não por km.
    tempos = viagem.tempos_para_unidades(lat, lng, ordenadas)
    resumos = [
        _resumo_unidade(u, servicos, quando, esperas, cor, tempos.get(u["id"]))
        for u in ordenadas
    ]
    resumos.sort(key=_chave_ordenacao)
    return resumos


def _texto_chegada(u: dict) -> str:
    """"2.1 km, ~9 min de carro" — ou só os km, sem estimativa. Com uma
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


def _primeira_aberta(candidatas: list[dict]) -> dict | None:
    return next((c for c in candidatas if c["aberta_agora"]), None)


def _contexto_do_dia(quando: datetime) -> str:
    """Início de frase que explica PORQUÊ os centros estão fechados."""
    dia = quando.date()
    tipo = feriados.tipo_de_dia(dia)
    if tipo == "feriado":
        return f"Hoje é feriado ({feriados.feriado_em(dia)}) e "
    if tipo == "sabado":
        return "É sábado e "
    if tipo == "domingo":
        return "É domingo e "
    return "A esta hora, "


def _contexto_do_dia_en(quando: datetime) -> str:
    """Versão inglesa de _contexto_do_dia."""
    dia = quando.date()
    tipo = feriados.tipo_de_dia(dia)
    if tipo == "feriado":
        return f"Today is a public holiday ({feriados.feriado_em(dia)}) and "
    if tipo == "sabado":
        return "It's Saturday and "
    if tipo == "domingo":
        return "It's Sunday and "
    return "At this time, "


def decidir_encaminhamento(
    cor: str, lat: float, lng: float, quando: datetime | None = None
) -> dict:
    """Devolve a recomendação completa de encaminhamento."""
    quando = quando or agora_na_madeira()
    esperas = espera.do_cache()
    ilha = _ilha_do_utente(lat, lng)
    no_porto_santo = ilha == "porto_santo"

    candidatas = _candidatas(SERVICOS_POR_COR[cor], lat, lng, quando, ilha, esperas, cor)
    abertas = [c for c in candidatas if c["aberta_agora"]]

    # Que método de viagem foi realmente usado neste pedido (osrm|rede),
    # para a interface poder ser transparente sobre a estimativa.
    metodo_viagem = next(
        (
            (c.get("tempo_viagem") or {}).get("metodo")
            for c in candidatas
            if c.get("tempo_viagem")
        ),
        None,
    )

    dia = quando.date()
    base = {
        "cor": cor,
        "cor_info": info_cor(cor),
        "ilha": ilha,
        "contactos": CONTACTOS,
        "gerado_em": quando.isoformat(timespec="minutes"),
        "espera_info": {
            k: esperas.get(k) for k in ("disponivel", "desatualizado", "obtido_em")
        },
        "viagem_info": viagem.descrever(metodo_viagem),
        "dia": {
            "tipo": feriados.tipo_de_dia(dia),
            "feriado": feriados.feriado_em(dia),
            "descricao": feriados.descricao_do_dia(dia),
            "descricao_en": _descricao_dia_en(dia),
        },
    }

    # ---------------------------------------------------------------- #
    if cor == "vermelho":
        referencia = abertas[0] if abertas else (candidatas[0] if candidatas else None)
        mensagem = (
            "Ligue já o 112. Siga as instruções do operador e, se possível, "
            "não se desloque pelos próprios meios. A urgência mais próxima "
            "é indicada abaixo apenas como referência."
        )
        mensagem_en = (
            "Call 112 now. Follow the operator's instructions and, if "
            "possible, do not travel by your own means. The nearest "
            "emergency department is shown below for reference only."
        )
        if no_porto_santo:
            mensagem += NOTA_TRANSFERENCIA_PORTO_SANTO
            mensagem_en += NOTA_TRANSFERENCIA_PORTO_SANTO_EN
        return base | {
            "acao": "ligar_112",
            "mensagem": mensagem,
            "mensagem_en": mensagem_en,
            "unidade": referencia,
            "alternativas": [] if no_porto_santo else abertas[1:3],
        }

    # ---------------------------------------------------------------- #
    if cor in ("laranja", "amarelo"):
        if abertas:
            principal, restantes, troca = espera.escolher_principal(abertas)
            alternativas = [] if no_porto_santo else restantes[:2]

            # No laranja, o hospital deve estar sempre visível: se a
            # unidade principal e as alternativas forem só atendimentos
            # urgentes, acrescenta-se a urgência hospitalar mais próxima.
            if cor == "laranja" and not no_porto_santo:
                mostradas = [principal, *alternativas]
                tem_hospitalar = any(
                    s in u["horarios"]
                    for u in mostradas
                    for s in SERVICOS_HOSPITALARES
                )
                if not tem_hospitalar:
                    hospitalares = _candidatas(
                        SERVICOS_HOSPITALARES, lat, lng, quando, ilha, esperas, cor
                    )
                    hospital = _primeira_aberta(hospitalares)
                    if hospital:
                        alternativas = ([hospital] + alternativas)[:3]

            mensagem = (
                f"Dirija-se a {principal['nome']} "
                f"({_texto_chegada(principal)}). "
                "Se os sintomas agravarem pelo caminho, ligue 112."
            )
            mensagem_en = (
                f"Go to {principal['nome']} "
                f"({_texto_chegada_en(principal)}). "
                "If symptoms worsen on the way, call 112."
            )
            # Regra experimental (por validar): explicar porque é que a
            # unidade sugerida não é simplesmente a mais próxima.
            if troca:
                mensagem += (
                    f" Nota: {troca['preterida']['nome']} fica mais perto "
                    f"({troca['preterida']['distancia_km']} km), mas com o tempo "
                    f"de espera atual estimamos ~{troca['total_preterida_min']} min "
                    f"aí, contra ~{troca['total_escolhida_min']} min em "
                    f"{principal['nome']}. Por isso sugerimos esta. Regra "
                    "experimental, por validar."
                )
                mensagem_en += (
                    f" Note: {troca['preterida']['nome']} is closer "
                    f"({troca['preterida']['distancia_km']} km), but with the "
                    f"current waiting time we estimate ~{troca['total_preterida_min']} "
                    f"min there, versus ~{troca['total_escolhida_min']} min at "
                    f"{principal['nome']}. That is why we suggest this one. Experimental "
                    "rule, pending validation."
                )
            if no_porto_santo and cor == "laranja":
                mensagem += NOTA_TRANSFERENCIA_PORTO_SANTO
                mensagem_en += NOTA_TRANSFERENCIA_PORTO_SANTO_EN
            return base | {
                "acao": "ir_unidade",
                "mensagem": mensagem,
                "mensagem_en": mensagem_en,
                "unidade": principal,
                "alternativas": alternativas,
                "reordenado_por_espera": bool(troca),
            }
        # Sem nada aberto (não deve acontecer: há urgências 24h). Segurança:
        return base | {
            "acao": "ligar_112",
            "mensagem": (
                "Não foi possível encontrar uma unidade aberta perto de si. "
                "Ligue 112 para orientação imediata."
            ),
            "mensagem_en": (
                "We could not find an open unit near you. "
                "Call 112 for immediate guidance."
            ),
            "unidade": candidatas[0] if candidatas else None,
            "alternativas": [],
        }

    # ---------------------------------------------------------------- #
    if cor == "verde":
        # Centro de saúde do utente, para seguimento se persistir.
        consultas = _candidatas(["consulta_aberta"], lat, lng, quando, ilha, esperas, cor)
        centro_local = consultas[0] if consultas else None

        # Há alguma CONSULTA aberta agora? (Não basta a unidade estar
        # "aberta" pelo atendimento urgente 24h — era isso que fazia o
        # sistema parecer assumir que qualquer dia é dia útil.)
        consultas_abertas = [
            c for c in abertas if "consulta_aberta" in c["servicos_abertos"]
        ]

        if consultas_abertas:
            principal = abertas[0]  # a aberta mais próxima (de qualquer tipo)
            centro_extra = (
                centro_local
                if centro_local and centro_local["id"] != principal["id"]
                else None
            )
            return base | {
                "acao": "ir_unidade",
                "mensagem": (
                    f"Dirija-se a {principal['nome']} "
                    f"({_texto_chegada(principal)}). Evitar a urgência "
                    "hospitalar liberta-a para os casos graves e poupa-lhe "
                    "horas de espera."
                ),
                "mensagem_en": (
                    f"Go to {principal['nome']} "
                    f"({_texto_chegada_en(principal)}). Avoiding the hospital "
                    "emergency department frees it up for serious cases and "
                    "saves you hours of waiting."
                ),
                "unidade": principal,
                "alternativas": [] if no_porto_santo else abertas[1:3],
                "centro_saude_proximo": centro_extra,
                "autocuidado": TEXTOS_AUTOCUIDADO["verde"],
            }

        if abertas:
            # Fim de semana, feriado ou noite: só atendimentos urgentes
            # abertos. Numa situação pouco urgente, ir já não é a única
            # opção razoável — apresentar as duas.
            principal = abertas[0]
            reabre = (
                f" (o mais próximo de si {centro_local['proxima_abertura_texto']})"
                if centro_local and centro_local.get("proxima_abertura_texto")
                else ""
            )
            reabre_en = (
                f" (the nearest to you {centro_local['proxima_abertura_texto_en']})"
                if centro_local and centro_local.get("proxima_abertura_texto_en")
                else ""
            )
            mensagem = (
                _contexto_do_dia(quando)
                + f"os centros de saúde estão fechados{reabre}. "
                "Numa situação pouco urgente tem duas opções razoáveis: "
                "vigiar em casa com o apoio do SNS 24, ou, se preferir ser "
                f"observado hoje, dirigir-se a {principal['nome']} "
                f"({_texto_chegada(principal)}), com atendimento aberto."
            )
            mensagem_en = (
                _contexto_do_dia_en(quando)
                + f"the health centres are closed{reabre_en}. "
                "In a non-urgent situation you have two reasonable options: "
                "watch and wait at home with SNS 24 support, or, if you prefer "
                f"to be seen today, go to {principal['nome']} "
                f"({_texto_chegada_en(principal)}), which has open care."
            )
            return base | {
                "acao": "ir_unidade",
                "mensagem": mensagem,
                "mensagem_en": mensagem_en,
                "unidade": principal,
                "alternativas": [] if no_porto_santo else abertas[1:3],
                "centro_saude_proximo": centro_local,
                "autocuidado": TEXTOS_AUTOCUIDADO["verde"],
            }

        # Nada aberto de todo (só possível se os dados de atendimento
        # urgente mudarem). Mantém-se o caminho seguro via SNS 24.
        urgencias = _candidatas(SERVICOS_URGENCIA, lat, lng, quando, ilha, esperas, cor)
        urgencia_aberta = _primeira_aberta(urgencias)
        return base | {
            "acao": "contactar_sns24",
            "mensagem": (
                _contexto_do_dia(quando)
                + "não encontrámos unidades abertas para situações pouco "
                "urgentes perto de si. Ligue para o SNS 24 (808 24 24 24) "
                "para aconselhamento, ou aguarde pela abertura da unidade "
                "indicada abaixo. Se os sintomas agravarem, dirija-se à "
                "urgência."
            ),
            "mensagem_en": (
                _contexto_do_dia_en(quando)
                + "we could not find units open for non-urgent situations "
                "near you. Call SNS 24 (808 24 24 24) for advice, or wait for "
                "the unit shown below to open. If symptoms worsen, go to the "
                "emergency department."
            ),
            "unidade": candidatas[0] if candidatas else None,
            "alternativas": [urgencia_aberta] if urgencia_aberta else [],
            "centro_saude_proximo": centro_local,
            "autocuidado": TEXTOS_AUTOCUIDADO["verde"],
        }

    # ---------------------------------------------------------------- #
    if cor == "azul":
        proxima = candidatas[0] if candidatas else None
        return base | {
            "acao": "autocuidado",
            "mensagem": (
                "A situação não aparenta ser urgente. Vigie os sintomas em "
                "casa; se precisar de aconselhamento, o SNS 24 e o seu "
                "centro de saúde (indicado abaixo) são os contactos certos."
            ),
            "mensagem_en": (
                "The situation does not appear to be urgent. Watch your "
                "symptoms at home; if you need advice, SNS 24 and your health "
                "centre (shown below) are the right contacts."
            ),
            "unidade": proxima,
            "alternativas": [],
            "autocuidado": TEXTOS_AUTOCUIDADO["azul"],
        }

    raise ValueError(f"Cor de triagem desconhecida: {cor!r}")
