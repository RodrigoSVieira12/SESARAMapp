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
3. No verde, a mensagem depende do dia e da hora:
   - com consulta aberta num centro de saúde → recomenda-se essa;
   - ao fim de semana, feriado ou à noite (só atendimentos urgentes
     abertos) → apresentam-se DUAS opções razoáveis: vigiar em casa com
     o apoio do SNS 24, ou ser observado hoje no atendimento urgente;
   - em qualquer caso o verde e o azul incluem um bloco de autocuidado
     (ver TEXTOS_AUTOCUIDADO), porque "esperar em casa" é muitas vezes
     uma opção legítima numa situação pouco urgente.
4. Em caso de dúvida, o sistema erra por excesso de urgência.
"""

from __future__ import annotations

from datetime import datetime

from . import espera, feriados, geo, horarios, unidades
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
        "aberta_agora": bool(abertos),
        "servicos_abertos": abertos,
        "horarios": {
            s: unidade["servicos"][s].get("texto", "") for s in correspondentes
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


def _elegiveis_na_ilha(procurados: list[str], ilha: str) -> list[dict]:
    na_ilha = [
        u for u in unidades.com_servicos(procurados)
        if u.get("ilha", "madeira") == ilha
    ]
    # Rede de segurança: se a ilha não tiver nenhuma unidade com estes
    # serviços, é melhor sugerir algo do que nada.
    return na_ilha or unidades.com_servicos(procurados)


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
    return [_resumo_unidade(u, servicos, quando, esperas, cor) for u in ordenadas]


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
        "dia": {
            "tipo": feriados.tipo_de_dia(dia),
            "feriado": feriados.feriado_em(dia),
            "descricao": feriados.descricao_do_dia(dia),
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
        if no_porto_santo:
            mensagem += NOTA_TRANSFERENCIA_PORTO_SANTO
        return base | {
            "acao": "ligar_112",
            "mensagem": mensagem,
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
                f"({principal['distancia_km']} km). "
                "Se os sintomas agravarem pelo caminho, ligue 112."
            )
            # Regra experimental (por validar): explicar porque é que a
            # unidade sugerida não é simplesmente a mais próxima.
            if troca:
                mensagem += (
                    f" Nota: {troca['preterida']['nome']} fica mais perto "
                    f"({troca['preterida']['distancia_km']} km), mas com o tempo "
                    f"de espera atual estimamos ~{troca['total_preterida_min']} min "
                    f"aí, contra ~{troca['total_escolhida_min']} min em "
                    f"{principal['nome']} — por isso sugerimos esta. Regra "
                    "experimental, por validar."
                )
            if no_porto_santo and cor == "laranja":
                mensagem += NOTA_TRANSFERENCIA_PORTO_SANTO
            return base | {
                "acao": "ir_unidade",
                "mensagem": mensagem,
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
                    f"({principal['distancia_km']} km). Evitar a urgência "
                    "hospitalar liberta-a para os casos graves e poupa-lhe "
                    "horas de espera."
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
            mensagem = (
                _contexto_do_dia(quando)
                + f"os centros de saúde estão fechados{reabre}. "
                "Numa situação pouco urgente tem duas opções razoáveis: "
                "vigiar em casa com o apoio do SNS 24, ou, se preferir ser "
                f"observado hoje, dirigir-se a {principal['nome']} "
                f"({principal['distancia_km']} km), com atendimento aberto."
            )
            return base | {
                "acao": "ir_unidade",
                "mensagem": mensagem,
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
            "unidade": proxima,
            "alternativas": [],
            "autocuidado": TEXTOS_AUTOCUIDADO["azul"],
        }

    raise ValueError(f"Cor de triagem desconhecida: {cor!r}")
