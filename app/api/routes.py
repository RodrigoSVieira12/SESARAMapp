"""Endpoints da API.

Resumo:
  GET  /api/saude                 → health check
  GET  /api/queixas               → lista de queixas disponíveis
  GET  /api/queixas/sugerir       → sugestões a partir de texto livre
  GET  /api/red-flags             → sinais de emergência (avaliados primeiro)
  POST /api/triagem               → próxima pergunta OU resultado (cor)
  GET  /api/unidades              → todas as unidades de saúde
  GET  /api/unidades/proxima      → unidades mais próximas de um ponto
  GET  /api/espera                → tempos de espera em tempo real (SEISRAM)
  POST /api/encaminhamento        → para onde ir, dado cor + localização
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..core import espera, feriados, geo, horarios, routing, sugestoes, unidades
from ..core.cores import CONTACTOS, info_cor
from ..core.triage_engine import ErroTriagem, TriageEngine
from ..models.schemas import EncaminhamentoRequest, TriagemRequest
from ..versao import VERSAO

router = APIRouter()

# O motor carrega e valida todos os fluxos no arranque do servidor.
engine = TriageEngine()


# --------------------------------------------------------------------- #
# Infraestrutura                                                          #
# --------------------------------------------------------------------- #

@router.get("/saude", tags=["infra"])
def saude() -> dict:
    return {
        "estado": "ok",
        "versao": VERSAO,
        "fluxos_carregados": len(engine.fluxos),
        "perguntas_total": sum(len(f["perguntas"]) for f in engine.fluxos.values()),
    }


# --------------------------------------------------------------------- #
# Triagem                                                                 #
# --------------------------------------------------------------------- #

@router.get("/queixas", tags=["triagem"])
def listar_queixas() -> list[dict]:
    return engine.listar_queixas()


@router.get("/queixas/sugerir", tags=["triagem"])
def sugerir_queixas(
    q: str = Query(min_length=1, max_length=120, description="Texto livre do utente, ex.: 'dói-me a barriga'."),
) -> dict:
    """Sugere queixas a partir de texto livre (sinónimos em app/data/sinonimos.json).

    Sem inteligência artificial: correspondência transparente por nome,
    descrição e dicionário de sinónimos, ignorando acentos e maiúsculas.
    Devolve no máximo 5 sugestões, ordenadas por relevância.
    """
    return {"q": q, "sugestoes": sugestoes.sugerir(q, engine.listar_queixas())}


@router.get("/red-flags", tags=["triagem"])
def listar_red_flags() -> list[dict]:
    return engine.listar_red_flags()


@router.post("/triagem", tags=["triagem"])
def triagem(pedido: TriagemRequest) -> dict:
    try:
        # 1) Sinais de emergência ganham a tudo o resto.
        if pedido.red_flags:
            resultado = engine.resultado_red_flags(pedido.red_flags)
            return {
                "tipo": "resultado",
                "queixa": None,
                "resultado": resultado | {"cor_info": info_cor(resultado["cor"])},
            }

        # 2) Fluxo normal de uma queixa.
        if not pedido.queixa:
            raise HTTPException(
                status_code=422,
                detail="Indique uma queixa ou pelo menos um sinal de emergência.",
            )
        saida = engine.avaliar(pedido.queixa, pedido.respostas)
        if saida["tipo"] == "resultado":
            saida["resultado"]["cor_info"] = info_cor(saida["resultado"]["cor"])
        return saida

    except ErroTriagem as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


# --------------------------------------------------------------------- #
# Unidades e encaminhamento                                               #
# --------------------------------------------------------------------- #

@router.get("/unidades", tags=["unidades"])
def listar_unidades() -> list[dict]:
    return unidades.todas()


@router.get("/unidades/proxima", tags=["unidades"])
def unidades_proximas(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    servico: str | None = Query(
        default=None,
        description=(
            "Filtrar por serviço: urgencia_polivalente, urgencia_basica, "
            "atendimento_urgente, consulta_aberta."
        ),
    ),
    n: int = Query(default=3, ge=1, le=10),
) -> dict:
    lista = unidades.com_servicos([servico]) if servico else unidades.todas()
    ordenadas = geo.ordenar_por_distancia(lista, lat, lng)[:n]

    agora = routing.agora_na_madeira()
    for u in ordenadas:
        u["aberta_agora"] = any(
            horarios.esta_aberto(h, agora) for h in u.get("servicos", {}).values()
        )
    return {"unidades": ordenadas, "consultado_em": agora.isoformat(timespec="minutes")}


@router.post("/encaminhamento", tags=["unidades"])
def encaminhamento(pedido: EncaminhamentoRequest) -> dict:
    return routing.decidir_encaminhamento(
        pedido.cor, pedido.lat, pedido.lng, quando=pedido.quando
    )


@router.get("/contactos", tags=["infra"])
def contactos() -> dict:
    return CONTACTOS


@router.get("/espera", tags=["unidades"])
def tempos_de_espera(
    atualizar: bool = Query(
        default=False,
        description="Se True, tenta ir buscar dados frescos ao site do SESARAM.",
    ),
) -> dict:
    """Tempos de espera em tempo real do SESARAM (sistema SEISRAM).

    Sem parâmetro, devolve o cache (rápido, sem rede). Com ?atualizar=true
    tenta uma descarga fresca — respeitando o TTL para não sobrecarregar o
    site. O campo "por_mapear" lista nomes que o site mostra e que ainda não
    estão em app/data/espera_nomes.json.
    """
    return espera.obter(force=atualizar)


@router.get("/feriados", tags=["infra"])
def listar_feriados(
    ano: int | None = Query(default=None, ge=2020, le=2100),
) -> dict:
    """Feriados (nacionais + regionais da RAM) considerados nos horários.

    Útil para conferir o calendário e para demonstrações: num feriado,
    os serviços com horário "semanal" contam como fechados, salvo se
    tiverem a chave "feriado" definida em unidades.json.
    """
    ano = ano or routing.agora_na_madeira().year
    return {
        "ano": ano,
        "feriados": [
            {"data": dia.isoformat(), "nome": nome}
            for dia, nome in sorted(feriados.feriados(ano).items())
        ],
    }
