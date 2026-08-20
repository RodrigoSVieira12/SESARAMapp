"""Endpoints da API.

Resumo:
  GET  /api/saude                 → health check
  GET  /api/queixas               → lista de queixas disponíveis
  GET  /api/queixas/sugerir       → sugestões a partir de texto livre
  GET  /api/red-flags             → sinais de emergência (avaliados primeiro)
  GET  /api/fluxogramas           → árvores Mermaid das regras atuais (relidas do disco)
  POST /api/triagem               → próxima pergunta OU resultado (cor)
  GET  /api/unidades              → todas as unidades de saúde
  GET  /api/unidades/proxima      → unidades mais próximas de um ponto
  GET  /api/espera                → tempos de espera em tempo real (SESARAM)
  GET  /api/viagem                → tempo de viagem estimado entre dois pontos
  GET  /api/localidades           → concelhos, freguesias e sítios (modo manual)
  POST /api/encaminhamento        → para onde ir, dado cor + localização
"""

from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Query, Response

from ..core import (
    espera,
    feriados,
    fluxogramas,
    geo,
    horarios,
    localidades,
    pdf_clinico,
    routing,
    sugestoes,
    unidades,
    viagem,
)
from ..core.cores import CONTACTOS, info_cor
from ..core.triage_engine import ErroTriagem, TriageEngine
from ..models.respostas import (
    EncaminhamentoResponse,
    IntegracaoTriagemResponse,
    TriagemResponse,
)
from ..models.schemas import (
    EncaminhamentoRequest,
    IntegracaoTriagemRequest,
    ResumoPdfRequest,
    TriagemRequest,
)
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
    q: str = Query(
        min_length=1, max_length=120, description="Texto livre do utente, ex.: 'dói-me a barriga'."
    ),
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


@router.get("/fluxogramas", tags=["triagem"])
def fluxogramas_atuais(
    idioma: str = Query(
        "pt",
        pattern="^(pt|en)$",
        description="Idioma dos rótulos e textos das árvores (pt ou en).",
    ),
) -> dict:
    """Fluxogramas Mermaid das regras ATUAIS em app/data/rules/.

    Ao contrário do resto da API (que usa o motor carregado no arranque),
    aqui as regras são RELIDAS E REVALIDADAS DO DISCO a cada pedido: é a
    peça que permite editar um JSON, guardar, e ver a árvore redesenhada
    no navegador (/fluxogramas) sem reiniciar o servidor. Se alguma regra
    estiver inválida, devolve a mensagem de validação por extenso em
    "erro" — em vez de uma página em branco, vê-se o que corrigir.

    Devolve apenas TEXTO Mermaid; o desenho acontece no cliente com a
    biblioteca embutida em /static/vendor/mermaid.min.js.
    """
    try:
        motor_fresco = TriageEngine()
    except RuntimeError as erro:
        return {"versao": VERSAO, "idioma": idioma, "erro": str(erro), "fluxos": []}
    return {
        "versao": VERSAO,
        "idioma": idioma,
        "erro": None,
        "fluxos": [
            {
                "id": fid,
                "nome": (f.get("nome_en") if idioma == "en" and f.get("nome_en") else f["nome"]),
                "mermaid": fluxogramas.mermaid_do_fluxo(f, idioma),
            }
            for fid, f in motor_fresco.fluxos.items()
        ],
    }


@router.get("/aconselhamento/revisao", tags=["triagem"])
def aconselhamento_revisao() -> dict:
    """Vista de REVISÃO do aconselhamento — ferramenta interna (/revisao).

    Quem revê o ecrã do utente não via o que o filtro de segurança esconde
    (os itens só-clínicos, sem `texto_utente`), por isso não conseguia
    confirmar facilmente que o filtro acerta. Este endpoint devolve TUDO,
    lado a lado: o texto clínico, a reescrita PT/EN quando existe, o estado
    de validação por item e a marca `mostrado_ao_utente`.

    Tal como /api/fluxogramas, RELÊ o ficheiro do disco a cada pedido: quem
    edita as reescritas e corre o aplicar vê o efeito com um refresh, sem
    reiniciar o servidor. E, de propósito, NÃO passa pelo motor: o portão
    ONDE_IR_APENAS_VALIDADO esconde itens ao utente, mas o revisor precisa
    de ver exatamente o que está escondido e porquê.
    """
    import json as _json

    from ..core.triage_engine import FICHEIRO_ACONSELHAMENTO

    if not FICHEIRO_ACONSELHAMENTO.exists():
        return {
            "versao": VERSAO,
            "erro": "aconselhamento.json não encontrado",
            "fonte": None,
            "totais": None,
            "fluxos": [],
        }
    try:
        dados = _json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
        fluxos_acons = dados.get("fluxos") or {}
    except (ValueError, OSError) as exc:
        return {
            "versao": VERSAO,
            "erro": f"aconselhamento.json ilegível: {exc}",
            "fonte": None,
            "totais": None,
            "fluxos": [],
        }

    ordem_cores = ["vermelho", "laranja", "amarelo", "verde", "azul"]
    saida = []
    total = mostrados = validados = 0
    for fid, blocos in fluxos_acons.items():
        cores = []
        for cor in ordem_cores:
            bloco = blocos.get(cor)
            if not bloco or not bloco.get("itens"):
                continue
            itens = []
            for it in bloco["itens"]:
                mostrado = bool(it.get("texto_utente"))
                total += 1
                mostrados += 1 if mostrado else 0
                validados += 1 if it.get("validado") else 0
                itens.append(
                    {
                        "texto": it.get("texto"),
                        "texto_utente": it.get("texto_utente"),
                        "texto_utente_en": it.get("texto_utente_en"),
                        "mostrado_ao_utente": mostrado,
                        "validado": bool(it.get("validado", False)),
                        "validado_por": it.get("validado_por"),
                        "validado_em": it.get("validado_em"),
                    }
                )
            cores.append({"cor": cor, "itens": itens})
        nome = (engine.fluxos.get(fid) or {}).get("nome") or fid
        saida.append({"id": fid, "nome": nome, "cores": cores})
    saida.sort(key=lambda f: f["nome"].lower())
    return {
        "versao": VERSAO,
        "erro": None,
        "fonte": dados.get("fonte"),
        "totais": {
            "itens": total,
            "mostrados_ao_utente": mostrados,
            "ocultos": total - mostrados,
            "validados": validados,
        },
        "fluxos": saida,
    }


@router.get("/perguntas/revisao", tags=["triagem"])
def perguntas_revisao() -> dict:
    """Vista de REVISÃO das perguntas — ferramenta interna (/revisao).

    O par do /api/aconselhamento/revisao para a outra metade do conteúdo
    leigo (v0.15.3): por fluxo, cada discriminador com a pergunta CLÍNICA
    oficial lado a lado com a reescrita PT/EN que o utente lê, a cor e a
    prioridade (o contexto de que o revisor precisa) e o estado de
    validação por item — que vive em app/data/perguntas_utente.json, a
    única fonte (as regras não o duplicam).

    Tal como os fluxogramas, RELÊ os ficheiros do disco a cada pedido:
    quem edita as reescritas (e corre o aplicar) ou marca um item como
    validado (não precisa de aplicar nada) vê o efeito com um refresh, sem
    reiniciar o servidor. E, de propósito, NÃO passa pelo motor: com
    ONDE_IR_APENAS_VALIDADO=1 o motor reverte as reescritas por validar
    para a pergunta clínica, mas o revisor precisa de ver a proposta.
    """
    import hashlib as _hashlib
    import json as _json

    from ..core.triage_engine import (
        FICHEIRO_PERGUNTAS_UTENTE,
        PASTA_REGRAS,
    )

    def _norm(s) -> str:
        # A forma canónica das chaves (scripts/_manchester_comum.normalizar):
        # espaços colapsados num só.
        return " ".join(str(s or "").split())

    registo: dict[str, dict] = {}
    fonte = None
    if FICHEIRO_PERGUNTAS_UTENTE.exists():
        try:
            bruto = FICHEIRO_PERGUNTAS_UTENTE.read_bytes()
            itens = (_json.loads(bruto.decode("utf-8")) or {}).get("itens") or {}
            registo = {_norm(c): i for c, i in itens.items() if isinstance(i, dict)}
            fonte = {
                "reescritas": {
                    "ficheiro": "app/data/perguntas_utente.json",
                    "sha256": _hashlib.sha256(bruto).hexdigest(),
                }
            }
        except (ValueError, OSError) as exc:
            return {
                "versao": VERSAO,
                "erro": f"perguntas_utente.json ilegível: {exc}",
                "fonte": None,
                "totais": None,
                "fluxos": [],
            }

    saida = []
    total = com_reescrita = validados = 0
    try:
        caminhos = sorted(PASTA_REGRAS.glob("*.json"))
    except OSError as exc:
        return {
            "versao": VERSAO,
            "erro": f"regras ilegíveis: {exc}",
            "fonte": fonte,
            "totais": None,
            "fluxos": [],
        }
    for caminho in caminhos:
        try:
            dados = _json.loads(caminho.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            return {
                "versao": VERSAO,
                "erro": f"{caminho.name} ilegível: {exc}",
                "fonte": fonte,
                "totais": None,
                "fluxos": [],
            }
        if dados.get("id") == "red_flags":
            continue
        perguntas = []
        for disc in dados.get("perguntas", []):
            entrada = registo.get(_norm(disc.get("texto"))) or {}
            total += 1
            com_reescrita += 1 if disc.get("texto_utente") else 0
            validados += 1 if entrada.get("validado") else 0
            perguntas.append(
                {
                    "cor": disc.get("cor"),
                    "prioridade": disc.get("prioridade"),
                    "texto": disc.get("texto"),
                    "texto_utente": disc.get("texto_utente"),
                    "texto_utente_en": disc.get("texto_utente_en"),
                    "sem_entrada": not entrada,
                    "validado": bool(entrada.get("validado", False)),
                    "validado_por": entrada.get("validado_por"),
                    "validado_em": entrada.get("validado_em"),
                }
            )
        saida.append(
            {"id": dados["id"], "nome": dados.get("nome") or dados["id"], "perguntas": perguntas}
        )
    saida.sort(key=lambda f: f["nome"].lower())
    return {
        "versao": VERSAO,
        "erro": None,
        "fonte": fonte,
        "totais": {
            "fluxos": len(saida),
            "discriminadores": total,
            "com_reescrita": com_reescrita,
            "reescritas": len(registo),
            "validados": validados,
        },
        "fluxos": saida,
    }


# response_model (v0.16.2): documenta o formato da resposta em /docs e
# valida o que sai. exclude_unset preserva o formato exato no fio: as
# chaves que o motor/routing não puseram continuam AUSENTES (não "null")
# — ver o cabeçalho de app/models/respostas.py.
@router.post(
    "/triagem",
    tags=["triagem"],
    response_model=TriagemResponse,
    response_model_exclude_unset=True,
)
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
    tempos = viagem.tempos_para_unidades(lat, lng, ordenadas)
    for u in ordenadas:
        u["aberta_agora"] = any(
            horarios.esta_aberto(h, agora, u.get("concelho"))
            for h in u.get("servicos", {}).values()
        )
        u["tempo_viagem"] = tempos.get(u["id"])
    return {"unidades": ordenadas, "consultado_em": agora.isoformat(timespec="minutes")}


@router.get("/viagem", tags=["unidades"])
def tempo_de_viagem(
    lat: float = Query(ge=-90, le=90, description="Latitude da origem."),
    lng: float = Query(ge=-180, le=180, description="Longitude da origem."),
    lat_destino: float | None = Query(None, ge=-90, le=90, description="Latitude do destino."),
    lng_destino: float | None = Query(None, ge=-180, le=180, description="Longitude do destino."),
    unidade: str | None = Query(
        None, description="Id de uma unidade como destino (permite usar tempos medidos)."
    ),
) -> dict:
    """Tempo de viagem estimado entre dois pontos (v0.11) — transparência.

    Serve para conferir o estimador (app/core/viagem.py) sem passar pela
    triagem: devolve a estimativa por estrada e a distância em linha reta,
    lado a lado. `estimativa` é None entre ilhas diferentes. Métodos:
    "rede" usa a rede calibrada local (app/data/rede_viagem.json); "medido"
    (v0.11.3) usa a tabela local de tempos por estrada quando o destino é uma
    `unidade` com medição para a zona; "osrm" só aparece se a instituição
    configurar VIAGEM_OSRM_URL.
    """
    destino_id = None
    if unidade is not None:
        alvo = next((u for u in unidades.todas() if u["id"] == unidade), None)
        if alvo is None:
            raise HTTPException(status_code=404, detail=f"Unidade desconhecida: {unidade}")
        destino_id = alvo["id"]
        lat_destino, lng_destino = alvo["lat"], alvo["lng"]
    elif lat_destino is None or lng_destino is None:
        raise HTTPException(
            status_code=422,
            detail="Indique lat_destino e lng_destino, ou o id de uma 'unidade'.",
        )
    return {
        "origem": {"lat": lat, "lng": lng},
        "destino": {"lat": lat_destino, "lng": lng_destino, "unidade": destino_id},
        "distancia_km_linha_reta": round(geo.haversine_km(lat, lng, lat_destino, lng_destino), 1),
        "estimativa": viagem.estimar(lat, lng, lat_destino, lng_destino, destino_id=destino_id),
        "nota": viagem.NOTA_VIAGEM,
        "nota_en": viagem.NOTA_VIAGEM_EN,
    }


@router.get("/localidades", tags=["unidades"])
def listar_localidades() -> dict:
    """Concelhos → freguesias → sítios da RAM, para o modo manual (v0.11.1).

    Serve o ecrã "Onde está?" quando o GPS falha ou o utente o quer
    corrigir: em vez de escolher só o concelho, pode afinar até à
    freguesia e ao sítio — nomes que qualquer pessoa conhece de cor.
    Cada nível traz um `centro` {lat, lng}; as listas já vêm ordenadas
    alfabeticamente (sem acentos contarem). Fonte editável:
    app/data/localidades.json, validada no arranque.
    """
    return localidades.arvore()


@router.post(
    "/encaminhamento",
    tags=["unidades"],
    response_model=EncaminhamentoResponse,
    response_model_exclude_unset=True,
)
def encaminhamento(pedido: EncaminhamentoRequest) -> dict:
    return routing.decidir_encaminhamento(
        pedido.cor,
        pedido.lat,
        pedido.lng,
        quando=pedido.quando,
        destino=pedido.destino,
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
    """Tempos de espera em tempo real do SESARAM (sistema SESARAM).

    Sem parâmetro, devolve o cache (rápido, sem rede). Com ?atualizar=true
    tenta uma descarga fresca — respeitando o TTL para não sobrecarregar o
    site. O campo "por_mapear" lista nomes que o site mostra e que ainda não
    estão em app/data/espera_nomes.json.
    """
    return espera.obter(force=atualizar)


# --------------------------------------------------------------------- #
# Integração (para consumo por sistemas externos)                         #
# --------------------------------------------------------------------- #


def _resultado_para(pedido) -> dict | None:
    """Corre a triagem e devolve o resultado final, OU None se ainda faltam
    perguntas (nesse caso o chamador recebe a próxima pergunta)."""
    if pedido.red_flags:
        resultado = engine.resultado_red_flags(pedido.red_flags)
        return resultado | {"cor_info": info_cor(resultado["cor"])}
    if not pedido.queixa:
        raise HTTPException(
            status_code=422,
            detail="Indique uma queixa ou pelo menos um sinal de emergência.",
        )
    saida = engine.avaliar(pedido.queixa, pedido.respostas)
    if saida["tipo"] != "resultado":
        return None
    saida["resultado"]["cor_info"] = info_cor(saida["resultado"]["cor"])
    return saida["resultado"]


@router.post(
    "/integracao/triagem",
    tags=["integracao"],
    response_model=IntegracaoTriagemResponse,
    response_model_exclude_unset=True,
)
def integracao_triagem(pedido: IntegracaoTriagemRequest) -> dict:
    """Triagem + encaminhamento numa só chamada (stateless).

    Devolve `tipo: "pergunta"` (com a próxima pergunta) enquanto faltarem
    respostas, ou `tipo: "resultado"` com a cor e, se `lat`/`lng` forem
    fornecidos, também o bloco de encaminhamento. Desenhado para ser fácil de
    consumir por um sistema externo com um único POST. Ver INTEGRACAO.md.
    """
    try:
        # Enquanto faltarem perguntas, comporta-se como POST /api/triagem.
        if not pedido.red_flags:
            if not pedido.queixa:
                raise HTTPException(
                    status_code=422,
                    detail="Indique uma queixa ou pelo menos um sinal de emergência.",
                )
            saida = engine.avaliar(pedido.queixa, pedido.respostas)
            if saida["tipo"] == "pergunta":
                return {"tipo": "pergunta", "queixa": pedido.queixa, **saida}

        resultado = _resultado_para(pedido)
        resposta: dict = {
            "tipo": "resultado",
            "queixa": pedido.queixa,
            "resultado": resultado,
        }
        if pedido.lat is not None and pedido.lng is not None:
            resposta["encaminhamento"] = routing.decidir_encaminhamento(
                resultado["cor"],
                pedido.lat,
                pedido.lng,
                quando=pedido.quando,
                destino=resultado.get("destino"),
            )
        return resposta
    except ErroTriagem as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro


def _pdf_bytes(pedido: ResumoPdfRequest) -> bytes:
    dados = pedido.model_dump()
    if not dados.get("gerado_em"):
        dados["gerado_em"] = routing.agora_na_madeira().isoformat(timespec="minutes")
    if not dados.get("contactos"):
        dados["contactos"] = CONTACTOS
    return pdf_clinico.gerar_pdf(dados)


@router.post("/exportar_pdf", tags=["integracao"])
def exportar_pdf(pedido: ResumoPdfRequest) -> Response:
    """Gera o resumo de orientação em PDF (application/pdf) para descarregar.

    O corpo é o que o utente viu (cor, queixa, respostas, unidade, etc.); o
    servidor desenha o PDF. É o mesmo documento que serve de anexo em
    qualquer integração futura.
    """
    pdf = _pdf_bytes(pedido)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="orientacao.pdf"'},
    )


@router.post("/exportar_pdf_base64", tags=["integracao"])
def exportar_pdf_base64(pedido: ResumoPdfRequest) -> dict:
    """Igual a /exportar_pdf, mas devolve o PDF em base64 dentro de JSON.

    Útil para um sistema que prefira receber o documento embutido numa
    resposta JSON (por exemplo, para anexar a um registo) em vez de um
    download binário.
    """
    pdf = _pdf_bytes(pedido)
    return {
        "nome_ficheiro": "orientacao.pdf",
        "tipo_mime": "application/pdf",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
    }


@router.get("/feriados", tags=["infra"])
def listar_feriados(
    ano: int | None = Query(default=None, ge=2020, le=2100),
) -> dict:
    """Feriados (nacionais + regionais da RAM) considerados nos horários.

    Útil para conferir o calendário e para demonstrações: num feriado,
    os serviços com horário "semanal" contam como fechados, salvo se
    tiverem a chave "feriado" definida em unidades.json. Os feriados
    MUNICIPAIS vêm à parte (`feriados_municipais`): aplicam-se só às
    unidades do respetivo concelho (v0.14.2).
    """
    ano = ano or routing.agora_na_madeira().year
    return {
        "ano": ano,
        "feriados": [
            {"data": dia.isoformat(), "nome": nome}
            for dia, nome in sorted(feriados.feriados(ano).items())
        ],
        "feriados_municipais": [
            {
                "concelho": concelho,
                "data": f"{ano:04d}-{mes:02d}-{dia:02d}",
                "nome": nome,
            }
            for concelho, (mes, dia, nome) in sorted(feriados.FERIADOS_MUNICIPAIS.items())
        ],
    }
