"""Onde Ir, protótipo de orientação de utentes na RAM (estágio SESARAM).

Arrancar em desenvolvimento:
    uvicorn app.main:app --reload

Depois abrir http://127.0.0.1:8000 (aplicação) e /docs (API interativa).
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Logging da aplicação (v0.13.1). Nível controlável por variável de
# ambiente (ONDE_IR_LOG=DEBUG|INFO|WARNING|ERROR), INFO por omissão.
# basicConfig é inofensivo se o processo anfitrião já tiver configurado
# handlers (não duplica). REGRA DE PRIVACIDADE (RGPD, ver
# docs/adr/0011-logging.md): os logs registam o estado do SISTEMA
# (arranque, scraping, recuos) e NUNCA dados do utente — nem
# coordenadas, nem respostas, nem cores pedidas por utentes reais.
logging.basicConfig(
    level=os.environ.get("ONDE_IR_LOG", "INFO").upper(),
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from .api.routes import router  # noqa: E402  (o logging acima deve vir 1.º)
from .versao import VERSAO  # noqa: E402

# Servir JS e CSS como UTF-8. Em alguns sistemas (sobretudo Windows) o
# Python regista .js como "text/javascript" SEM charset, e o browser
# assume Latin-1 — o que corrompe os acentos dos textos e impede o
# arranque da app. Declarar o charset aqui resolve isto na origem, sem
# precisar de middleware.
mimetypes.add_type("text/javascript; charset=utf-8", ".js")
mimetypes.add_type("text/css; charset=utf-8", ".css")

RAIZ = Path(__file__).resolve().parent.parent
PASTA_STATIC = RAIZ / "static"

app = FastAPI(
    title="Onde Ir (RAM, protótipo)",
    version=VERSAO,
    description=(
        "Protótipo de estágio (SESARAM): orientação de utentes na Região "
        "Autónoma da Madeira: triagem simplificada por perguntas, "
        "estimativa da cor de prioridade e encaminhamento para a unidade "
        "de saúde adequada mais próxima.\n\n"
        "Ferramenta de orientação. NÃO substitui avaliação clínica nem "
        "a triagem oficial feita nas urgências. Regras e dados de unidades "
        "são exemplos por validar."
    ),
)

# Limite de tamanho do corpo dos pedidos (v0.16.2). O maior pedido
# legítimo da aplicação é o POST /api/exportar_pdf com o estado do ecrã
# (~10-20 KB); 1 MB é portanto folgadíssimo. Sem este teto, um corpo
# gigante custava CPU e memória só a ser lido e interpretado — e, antes
# dos limites dos schemas, chegava a custar dezenas de segundos ao
# gerador de PDF. É a primeira linha de defesa; as outras duas são os
# limites Pydantic (app/models/schemas.py) e os cortes do próprio
# gerador (app/core/pdf_clinico.py). Configurável por variável de
# ambiente, ex.: ONDE_IR_CORPO_MAXIMO=250000.
CORPO_MAXIMO_BYTES = int(os.environ.get("ONDE_IR_CORPO_MAXIMO", 1_000_000))


class LimiteDeCorpo:
    """Middleware ASGI puro: rejeita corpos acima do limite com 413.

    A verificação usa o cabeçalho Content-Length, que todos os clientes
    normais (browser, requests, httpx) enviam nos POST com corpo. Um
    cliente hostil pode omiti-lo (transferência em blocos); para esse
    caso valem as camadas seguintes descritas acima — este middleware é
    o corte barato e cedo, não a única defesa.
    """

    def __init__(self, app, maximo_bytes: int = CORPO_MAXIMO_BYTES) -> None:
        self.app = app
        self.maximo_bytes = maximo_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            for nome, valor in scope.get("headers") or []:
                if nome == b"content-length":
                    try:
                        excede = int(valor) > self.maximo_bytes
                    except ValueError:
                        excede = False  # cabeçalho ilegível: o servidor HTTP que decida
                    if excede:
                        corpo = json.dumps(
                            {
                                "detail": (
                                    "Corpo do pedido demasiado grande "
                                    f"(máximo {self.maximo_bytes} bytes)."
                                )
                            }
                        ).encode("utf-8")
                        await send(
                            {
                                "type": "http.response.start",
                                "status": 413,
                                "headers": [
                                    (b"content-type", b"application/json; charset=utf-8"),
                                    (b"content-length", str(len(corpo)).encode("ascii")),
                                ],
                            }
                        )
                        await send({"type": "http.response.body", "body": corpo})
                        return
                    break
        await self.app(scope, receive, send)


# Ordem importa: o Starlette embrulha por ordem inversa de registo, por
# isso o CORS (registado depois) fica por FORA e as respostas 413 deste
# middleware também levam os cabeçalhos CORS.
app.add_middleware(LimiteDeCorpo, maximo_bytes=CORPO_MAXIMO_BYTES)

# CORS aberto para facilitar o desenvolvimento (ex.: frontend noutro porto).
# Em produção, restringir allow_origins ao domínio real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

logger.info("Onde ir? v%s pronto (frontend + API em /api)", VERSAO)

# Frontend: ficheiros estáticos + página principal.
app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")


@app.get("/", include_in_schema=False)
def pagina_principal() -> FileResponse:
    return FileResponse(PASTA_STATIC / "index.html", media_type="text/html; charset=utf-8")


@app.get("/fluxogramas", include_in_schema=False)
def pagina_fluxogramas() -> FileResponse:
    """Pré-visualização viva dos fluxogramas de triagem (ferramenta interna).

    Edita-se um JSON em app/data/rules/, guarda-se, e a árvore aparece
    redesenhada aqui (as regras são relidas do disco a cada pedido em
    /api/fluxogramas). Não está ligada à interface do utente de propósito:
    destina-se a quem edita/valida regras, não ao público.
    """
    return FileResponse(PASTA_STATIC / "fluxogramas.html", media_type="text/html; charset=utf-8")


@app.get("/revisao", include_in_schema=False)
def pagina_revisao() -> FileResponse:
    """Vista de revisão do aconselhamento (ferramenta interna, v0.15.2).

    Mostra, lado a lado, o conselho clínico e a reescrita leiga (PT/EN),
    com o estado de validação por item e a marca do que fica ESCONDIDO ao
    utente pelo filtro de segurança — é aqui que quem revê confirma que o
    filtro acerta. Não está ligada à interface do utente de propósito:
    destina-se à equipa clínica e a quem mantém os dados, não ao público.
    Os dados são relidos do disco a cada pedido (GET /api/aconselhamento/
    revisao); editar as reescritas + correr o aplicar + refresh chega.
    """
    return FileResponse(PASTA_STATIC / "revisao.html", media_type="text/html; charset=utf-8")


if __name__ == "__main__":  # permite `python -m app.main`
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
