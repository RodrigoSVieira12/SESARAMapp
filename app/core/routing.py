"""Encaminhamento: dada a cor de triagem, a localização do utente e a
hora atual, decidir PARA ONDE o utente deve ir.

Separar isto do motor de triagem é deliberado:
- a triagem responde "quão urgente é?" (decisão clínica);
- o encaminhamento responde "onde e quando?" (decisão logística:
  proximidade, horários — com fins de semana e feriados —, e a ILHA
  onde o utente está).

Decisões desta versão (todas a validar clinicamente com o SESARAM):
1. (v0.12.1, indicação da reunião de acompanhamento) Vermelho, laranja
   e amarelo são encaminhados DIRETAMENTE para a urgência do hospital
   de referência — por omissão o Hospital Dr. Nélio Mendonça. A
   política vive em app/data/encaminhamento.json e é editável sem
   tocar em código: retirar uma cor da lista repõe, para essa cor, o
   comportamento por proximidade (qualquer urgência aberta, hospitalar
   ou atendimento urgente dos centros de saúde). Válvula para o
   futuro: um desfecho AMARELO pode declarar "destino":
   "atendimento_urgente" no próprio ficheiro de regras e passa a valer
   a urgência aberta mais próxima para esse desfecho. No vermelho a
   ação continua a ser ligar 112; o hospital aparece como referência.
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

Organização desde a v0.13.1 (responsabilidade única; ver
docs/adr/0010-divisao-routing.md): este módulo DECIDE; as frases
mostradas ao utente vivem em routing_textos.py; a lista "porquê esta
recomendação?" (explicabilidade) é construída por motivos.py e devolvida
no campo `motivos` de todas as respostas.
"""

from __future__ import annotations

import json as _json
import logging
from datetime import datetime
from pathlib import Path as _Path

from . import espera, feriados, geo, horarios, motivos, unidades, viagem
from .cores import CONTACTOS, info_cor
from .routing_textos import (
    NOTA_TRANSFERENCIA_PORTO_SANTO,
    NOTA_TRANSFERENCIA_PORTO_SANTO_EN,
    _contexto_do_dia,
    _contexto_do_dia_en,
    _descricao_dia_en,
    _horario_en,
    _texto_chegada,
    _texto_chegada_en,
    _texto_proxima_abertura,
    _texto_proxima_abertura_en,
)

logger = logging.getLogger(__name__)

try:
    from zoneinfo import ZoneInfo

    FUSO_MADEIRA = ZoneInfo("Atlantic/Madeira")
except Exception:  # pragma: no cover - ex.: Windows sem o pacote tzdata
    FUSO_MADEIRA = None


def agora_na_madeira() -> datetime:
    if FUSO_MADEIRA is not None:
        return datetime.now(FUSO_MADEIRA)
    return datetime.now()


# Que tipos de serviço servem cada cor NO COMPORTAMENTO POR PROXIMIDADE.
# Desde a v0.12.1 este mapa só decide o encaminhamento de vermelho /
# laranja / amarelo quando a política de hospital direto NÃO se aplica:
# amarelos excecionados por "destino", Porto Santo (regra da ilha), cor
# retirada de encaminhamento.json, ou recuo por erro de dados. NOTA
# CLÍNICA: mapeamento a validar pela equipa do SESARAM (docstring, 1).
SERVICOS_POR_COR: dict[str, list[str]] = {
    "vermelho": ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"],
    "laranja": ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"],
    "amarelo": ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"],
    "verde": ["atendimento_urgente", "consulta_aberta"],
    "azul": ["consulta_aberta", "atendimento_urgente"],
}

SERVICOS_URGENCIA = ["urgencia_polivalente", "urgencia_basica", "atendimento_urgente"]
SERVICOS_HOSPITALARES = ["urgencia_polivalente", "urgencia_basica"]

# Textos fixos mostrados ao utente no verde e no azul. Estão aqui, num
# só sítio, para poderem ser revistos na sessão de validação clínica
# (o scripts/gerar_validacao_clinica.py inclui-os no documento).
# Textos de autocuidado: vivem em app/data/autocuidado.json para poderem
# ser revistos e corrigidos pela equipa clínica sem tocar em Python, tal
# como as regras de triagem. Estrutura por cor: titulo, intro, fazer[],
# evitar[], alerta_titulo, alerta[] — e as variantes *_en em inglês.
_FICHEIRO_AUTOCUIDADO = _Path(__file__).resolve().parents[1] / "data" / "autocuidado.json"

TEXTOS_AUTOCUIDADO: dict[str, dict] = _json.loads(
    _FICHEIRO_AUTOCUIDADO.read_text(encoding="utf-8")
)["cores"]

# Política de destino por cor (v0.12.1): que cores vão DIRETAMENTE para
# a urgência do hospital de referência. Vive em app/data/encaminhamento.json
# para a equipa clínica poder ajustar sem tocar em Python (tal como as
# regras de triagem). Sem ficheiro, o recuo seguro é a política atual.
_FICHEIRO_POLITICA = _Path(__file__).resolve().parents[1] / "data" / "encaminhamento.json"

DESTINOS_VALIDOS = ("hospital", "atendimento_urgente")


def _carregar_politica() -> dict:
    try:
        dados = _json.loads(_FICHEIRO_POLITICA.read_text(encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover - recuo defensivo
        logger.warning(
            "encaminhamento.json em falta; a usar a política predefinida "
            "(vermelho/laranja/amarelo -> hospital hnm)"
        )
        dados = {}
    return {
        "hospital_id": dados.get("hospital_id", "hnm"),
        "direto_para_hospital": list(
            dados.get("direto_para_hospital", ["vermelho", "laranja", "amarelo"])
        ),
    }


POLITICA = _carregar_politica()


def _ilha_do_utente(lat: float, lng: float) -> str:
    """Ilha estimada: a da unidade mais próxima do utente."""
    ordenadas = geo.ordenar_por_distancia(unidades.todas(), lat, lng)
    return ordenadas[0].get("ilha", "madeira") if ordenadas else "madeira"


def _concelho_do_utente(lat: float, lng: float) -> str | None:
    """Concelho estimado do utente: o da unidade mais próxima.

    Serve só para o CONTEXTO do dia (ex.: dizer que hoje é o feriado
    municipal do concelho do utente). A decisão de aberto/fechado de
    CADA unidade usa sempre o concelho DESSA unidade, não este (ver
    _resumo_unidade)."""
    ordenadas = geo.ordenar_por_distancia(unidades.todas(), lat, lng)
    return ordenadas[0].get("concelho") if ordenadas else None


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
    # O concelho da unidade entra aqui para os feriados municipais
    # (v0.14.2): uma consulta fecha no feriado municipal do SEU concelho,
    # a urgência 24h mantém-se aberta (ver horarios.py / feriados.py).
    concelho = unidade.get("concelho")
    abertos = [
        s for s in correspondentes if horarios.esta_aberto(unidade["servicos"][s], quando, concelho)
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
        "horarios": {s: unidade["servicos"][s].get("texto", "") for s in correspondentes},
        "horarios_en": {
            s: _horario_en(unidade["servicos"][s].get("texto", "")) for s in correspondentes
        },
    }

    # Se está fechada, dizer quando reabre (o mais cedo entre os
    # serviços procurados) — evita o efeito "assume que é dia útil".
    if not abertos:
        aberturas = [
            horarios.proxima_abertura(unidade["servicos"][s], quando, concelho=concelho)
            for s in correspondentes
        ]
        aberturas = [a for a in aberturas if a is not None]
        if aberturas:
            abre = min(aberturas)
            resumo["proxima_abertura"] = abre.isoformat(timespec="minutes")
            resumo["proxima_abertura_texto"] = _texto_proxima_abertura(abre, quando)
            resumo["proxima_abertura_texto_en"] = _texto_proxima_abertura_en(abre, quando)

    # Tempo de espera em tempo real (SESARAM), quando o cache o tiver.
    # No hospital, a coluna é a da própria cor do utente.
    # Exceção (v0.14.2): no VERMELHO (emergente) o doente é atendido de
    # imediato — mostrar "tempo de espera" ou "pessoas em espera" seria
    # enganador, e o próprio site do SESARAM não publica espera para a
    # cor emergente. Por isso a espera nunca se junta ao cartão no
    # vermelho; ali a unidade é apenas uma referência (a ação é o 112).
    if esperas and cor != "vermelho":
        tempo_espera = espera.para_unidade(esperas, unidade["id"], cor)
        if tempo_espera:
            resumo["tempo_espera"] = tempo_espera
    return resumo


def _elegiveis_na_ilha(procurados: list[str], ilha: str) -> list[dict]:
    na_ilha = [u for u in unidades.com_servicos(procurados) if u.get("ilha", "madeira") == ilha]
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
        _resumo_unidade(u, servicos, quando, esperas, cor, tempos.get(u["id"])) for u in ordenadas
    ]
    resumos.sort(key=_chave_ordenacao)
    return resumos


def _primeira_aberta(candidatas: list[dict]) -> dict | None:
    return next((c for c in candidatas if c["aberta_agora"]), None)


def _resumo_hospital(
    lat: float, lng: float, quando: datetime, esperas: dict | None, cor: str
) -> dict | None:
    """Resumo do hospital de referência da política, com distância,
    tempo de viagem e espera da cor. Devolve None se o id configurado
    não existir nos dados (o chamador recua para a proximidade)."""
    hospital = unidades.por_id(POLITICA["hospital_id"])
    if hospital is None:
        return None
    com_distancia = geo.ordenar_por_distancia([hospital], lat, lng)[0]
    tempos = viagem.tempos_para_unidades(lat, lng, [com_distancia])
    return _resumo_unidade(
        com_distancia,
        SERVICOS_HOSPITALARES,
        quando,
        esperas,
        cor,
        tempos.get(com_distancia["id"]),
    )


def _destino_efetivo(cor: str, destino: str | None) -> tuple[str, str]:
    """Resolve (destino, fonte) para vermelho/laranja/amarelo.

    O campo `destino` (vindo do desfecho do fluxograma via API) só é
    honrado no AMARELO — é a válvula prevista para certos amarelos
    poderem voltar ao atendimento urgente mais próximo sem mexer em
    código. No vermelho e no laranja a política vem só da configuração.
    """
    if cor == "amarelo" and destino in DESTINOS_VALIDOS:
        return destino, "fluxograma"
    if cor in POLITICA["direto_para_hospital"]:
        return "hospital", "configuracao"
    return "atendimento_urgente", "predefinicao"


def decidir_encaminhamento(
    cor: str,
    lat: float,
    lng: float,
    quando: datetime | None = None,
    destino: str | None = None,
) -> dict:
    """Devolve a recomendação completa de encaminhamento.

    `destino` é o campo opcional do desfecho do fluxograma (só tem
    efeito no amarelo; ver _destino_efetivo).
    """
    quando = quando or agora_na_madeira()
    esperas = espera.do_cache()
    ilha = _ilha_do_utente(lat, lng)
    no_porto_santo = ilha == "porto_santo"
    # Concelho do utente (o da unidade mais próxima): usado só para o
    # CONTEXTO do dia — ex.: reconhecer o feriado municipal do concelho
    # do utente (v0.14.2). Não afeta o aberto/fechado de cada unidade.
    concelho_utente = _concelho_do_utente(lat, lng)

    candidatas = _candidatas(SERVICOS_POR_COR[cor], lat, lng, quando, ilha, esperas, cor)
    abertas = [c for c in candidatas if c["aberta_agora"]]

    # Que método de viagem foi realmente usado neste pedido (osrm|rede),
    # para a interface poder ser transparente sobre a estimativa.
    metodo_viagem = next(
        ((c.get("tempo_viagem") or {}).get("metodo") for c in candidatas if c.get("tempo_viagem")),
        None,
    )

    dia = quando.date()
    base = {
        "cor": cor,
        "cor_info": info_cor(cor),
        "ilha": ilha,
        "contactos": CONTACTOS,
        "gerado_em": quando.isoformat(timespec="minutes"),
        "espera_info": {k: esperas.get(k) for k in ("disponivel", "desatualizado", "obtido_em")},
        "viagem_info": viagem.descrever(metodo_viagem),
        "dia": {
            "tipo": feriados.tipo_de_dia(dia, concelho_utente),
            "feriado": feriados.feriado_em(dia, concelho_utente),
            "descricao": feriados.descricao_do_dia(dia, concelho_utente),
            "descricao_en": _descricao_dia_en(dia, concelho_utente),
        },
    }

    # ---------------------------------------------------------------- #
    if cor == "vermelho":
        # A ação é sempre ligar 112. A unidade abaixo é só referência:
        # com a política de hospital direto (v0.12.1), essa referência
        # é o hospital — é para lá que a emergência transporta.
        destino_ref, fonte = _destino_efetivo(cor, None)
        referencia = None
        aplicada = False
        if destino_ref == "hospital" and not no_porto_santo:
            referencia = _resumo_hospital(lat, lng, quando, esperas, cor)
            aplicada = referencia is not None
        if referencia is not None:
            frase_ref = "O hospital de referência é indicado abaixo apenas como " "referência."
            frase_ref_en = "The reference hospital is shown below for reference only."
            alternativas = []
        else:
            referencia = abertas[0] if abertas else (candidatas[0] if candidatas else None)
            frase_ref = "A urgência mais próxima é indicada abaixo apenas como " "referência."
            frase_ref_en = "The nearest emergency department is shown below for " "reference only."
            alternativas = [] if no_porto_santo else abertas[1:3]
        mensagem = (
            "Ligue já o 112. Siga as instruções do operador e, se possível, "
            "não se desloque pelos próprios meios. " + frase_ref
        )
        mensagem_en = (
            "Call 112 now. Follow the operator's instructions and, if "
            "possible, do not travel by your own means. " + frase_ref_en
        )
        if no_porto_santo:
            mensagem += NOTA_TRANSFERENCIA_PORTO_SANTO
            mensagem_en += NOTA_TRANSFERENCIA_PORTO_SANTO_EN
        return base | {
            "acao": "ligar_112",
            "mensagem": mensagem,
            "mensagem_en": mensagem_en,
            "unidade": referencia,
            "alternativas": alternativas,
            "politica": {"destino": destino_ref, "fonte": fonte, "aplicada": aplicada},
            "motivos": motivos.compilar(
                motivos.cor(cor),
                motivos.emergencia_112(),
                motivos.politica_hospital(cor) if aplicada else None,
                motivos.ilha_porto_santo() if no_porto_santo else None,
            ),
        }

    # ---------------------------------------------------------------- #
    if cor in ("laranja", "amarelo"):
        destino_final, fonte = _destino_efetivo(cor, destino)
        politica_info = {"destino": destino_final, "fonte": fonte, "aplicada": False}

        if destino_final == "hospital" and not no_porto_santo:
            hospital = _resumo_hospital(lat, lng, quando, esperas, cor)
            if hospital is not None and hospital["aberta_agora"]:
                nome_cor_en = str(info_cor(cor).get("nome_en", cor)).lower()
                mensagem = (
                    f"Dirija-se a {hospital['nome']} "
                    f"({_texto_chegada(hospital)}). Nos casos classificados "
                    f"como {cor}, o encaminhamento é feito diretamente para "
                    "a urgência do hospital. Se os sintomas agravarem pelo "
                    "caminho, ligue 112."
                )
                mensagem_en = (
                    f"Go to {hospital['nome']} "
                    f"({_texto_chegada_en(hospital)}). Cases classified as "
                    f"{nome_cor_en} are referred directly to the hospital "
                    "emergency department. If symptoms worsen on the way, "
                    "call 112."
                )
                return base | {
                    "acao": "ir_unidade",
                    "mensagem": mensagem,
                    "mensagem_en": mensagem_en,
                    "unidade": hospital,
                    "alternativas": [],
                    "reordenado_por_espera": False,
                    "politica": politica_info | {"aplicada": True},
                    "motivos": motivos.compilar(
                        motivos.cor(cor),
                        motivos.politica_hospital(cor),
                        motivos.unidade_aberta(hospital),
                        motivos.proximidade(hospital),
                        motivos.espera_atual(hospital),
                    ),
                }
            # Hospital configurado sem urgência aberta nos dados (id
            # trocado ou erro de horários): recuo seguro para o
            # comportamento por proximidade, em vez de mandar alguém
            # para uma porta que os dados dizem estar fechada.
            # Isto é um problema de DADOS, não do utente — fica no log
            # (sem localização nem respostas; ver docs/adr/0011-logging.md).
            logger.warning(
                "Encaminhamento (%s): hospital de referência '%s' sem "
                "urgência aberta nos dados; recuo para proximidade.",
                cor,
                POLITICA["hospital_id"],
            )
            politica_info = politica_info | {"recuo": True}

        if abertas:
            principal, restantes, troca = espera.escolher_principal(abertas)
            alternativas = [] if no_porto_santo else restantes[:2]

            # No laranja, o hospital deve estar sempre visível: se a
            # unidade principal e as alternativas forem só atendimentos
            # urgentes, acrescenta-se a urgência hospitalar mais próxima.
            if cor == "laranja" and not no_porto_santo:
                mostradas = [principal, *alternativas]
                tem_hospitalar = any(
                    s in u["horarios"] for u in mostradas for s in SERVICOS_HOSPITALARES
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
            # Porquê esta unidade e não outra: a fonte da política, o
            # estado (aberta, tempo de viagem, espera) e, se aplicável,
            # a troca pela espera e a regra da ilha.
            if politica_info.get("recuo"):
                motivo_politica = motivos.recuo_hospital()
            elif fonte == "fluxograma":
                motivo_politica = motivos.politica_fluxograma()
            elif no_porto_santo:
                motivo_politica = None  # a regra da ilha explica o destino
            else:
                motivo_politica = motivos.politica_proximidade()
            return base | {
                "acao": "ir_unidade",
                "mensagem": mensagem,
                "mensagem_en": mensagem_en,
                "unidade": principal,
                "alternativas": alternativas,
                "reordenado_por_espera": bool(troca),
                "politica": politica_info,
                "motivos": motivos.compilar(
                    motivos.cor(cor),
                    motivo_politica,
                    motivos.unidade_aberta(principal),
                    motivos.proximidade(principal),
                    motivos.espera_atual(principal),
                    motivos.troca_por_espera(troca, principal) if troca else None,
                    motivos.ilha_porto_santo() if no_porto_santo else None,
                ),
            }
        # Sem nada aberto (não deve acontecer: há urgências 24h). Segurança:
        return base | {
            "acao": "ligar_112",
            "mensagem": (
                "Não foi possível encontrar uma unidade aberta perto de si. "
                "Ligue 112 para orientação imediata."
            ),
            "mensagem_en": (
                "We could not find an open unit near you. " "Call 112 for immediate guidance."
            ),
            "unidade": candidatas[0] if candidatas else None,
            "alternativas": [],
            "politica": politica_info,
            "motivos": motivos.compilar(
                motivos.cor(cor),
                motivos.sem_urgencias_abertas(),
            ),
        }

    # ---------------------------------------------------------------- #
    if cor == "verde":
        # Centro de saúde do utente, para seguimento se persistir.
        consultas = _candidatas(["consulta_aberta"], lat, lng, quando, ilha, esperas, cor)
        centro_local = consultas[0] if consultas else None

        # Há alguma CONSULTA aberta agora? (Não basta a unidade estar
        # "aberta" pelo atendimento urgente 24h — era isso que fazia o
        # sistema parecer assumir que qualquer dia é dia útil.)
        consultas_abertas = [c for c in abertas if "consulta_aberta" in c["servicos_abertos"]]

        if consultas_abertas:
            principal = abertas[0]  # a aberta mais próxima (de qualquer tipo)
            centro_extra = (
                centro_local if centro_local and centro_local["id"] != principal["id"] else None
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
                "motivos": motivos.compilar(
                    motivos.cor(cor),
                    motivos.verde_evitar_urgencia(),
                    motivos.unidade_aberta(principal),
                    motivos.proximidade(principal),
                    motivos.espera_atual(principal),
                ),
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
                _contexto_do_dia(quando, concelho_utente)
                + f"os centros de saúde estão fechados{reabre}. "
                "Numa situação pouco urgente tem duas opções razoáveis: "
                "vigiar em casa com o apoio do SNS 24, ou, se preferir ser "
                f"observado hoje, dirigir-se a {principal['nome']} "
                f"({_texto_chegada(principal)}), com atendimento aberto."
            )
            mensagem_en = (
                _contexto_do_dia_en(quando, concelho_utente)
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
                "motivos": motivos.compilar(
                    motivos.cor(cor),
                    motivos.centros_fechados(quando, concelho_utente),
                    motivos.verde_duas_opcoes(),
                    motivos.unidade_aberta(principal),
                    motivos.proximidade(principal),
                    motivos.espera_atual(principal),
                ),
            }

        # Nada aberto de todo (só possível se os dados de atendimento
        # urgente mudarem). Mantém-se o caminho seguro via SNS 24.
        urgencias = _candidatas(SERVICOS_URGENCIA, lat, lng, quando, ilha, esperas, cor)
        urgencia_aberta = _primeira_aberta(urgencias)
        return base | {
            "acao": "contactar_sns24",
            "mensagem": (
                _contexto_do_dia(quando, concelho_utente)
                + "não encontrámos unidades abertas para situações pouco "
                "urgentes perto de si. Ligue para o SNS 24 (808 24 24 24) "
                "para aconselhamento, ou aguarde pela abertura da unidade "
                "indicada abaixo. Se os sintomas agravarem, dirija-se à "
                "urgência."
            ),
            "mensagem_en": (
                _contexto_do_dia_en(quando, concelho_utente)
                + "we could not find units open for non-urgent situations "
                "near you. Call SNS 24 (808 24 24 24) for advice, or wait for "
                "the unit shown below to open. If symptoms worsen, go to the "
                "emergency department."
            ),
            "unidade": candidatas[0] if candidatas else None,
            "alternativas": [urgencia_aberta] if urgencia_aberta else [],
            "centro_saude_proximo": centro_local,
            "autocuidado": TEXTOS_AUTOCUIDADO["verde"],
            "motivos": motivos.compilar(
                motivos.cor(cor),
                motivos.centros_fechados(quando, concelho_utente),
                motivos.sem_unidades_abertas(),
            ),
        }

    # ---------------------------------------------------------------- #
    if cor == "azul":
        # Como no verde (v0.14.2): o centro de saúde principal é o mais
        # próximo / mais rápido de chegar, e as duas unidades seguintes
        # aparecem numa secção de alternativas. No Porto Santo a regra da
        # ilha mantém só a unidade local (sem alternativas noutra ilha).
        principal = candidatas[0] if candidatas else None
        alternativas = [] if no_porto_santo else candidatas[1:3]
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
            "unidade": principal,
            "alternativas": alternativas,
            "autocuidado": TEXTOS_AUTOCUIDADO["azul"],
            "motivos": motivos.compilar(
                motivos.cor(cor),
                motivos.azul_autocuidado(),
                motivos.ilha_porto_santo() if no_porto_santo else None,
            ),
        }

    raise ValueError(f"Cor de triagem desconhecida: {cor!r}")
