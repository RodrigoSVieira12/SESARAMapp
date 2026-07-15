"""Onde Ir, protótipo de orientação de utentes na RAM (estágio SESARAM).

Arrancar em desenvolvimento:
    uvicorn app.main:app --reload

Depois abrir http://127.0.0.1:8000 (aplicação) e /docs (API interativa).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .versao import VERSAO

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

# CORS aberto para facilitar o desenvolvimento (ex.: frontend noutro porto).
# Em produção, restringir allow_origins ao domínio real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Frontend: ficheiros estáticos + página principal.
app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")


@app.get("/", include_in_schema=False)
def pagina_principal() -> FileResponse:
    return FileResponse(
        PASTA_STATIC / "index.html", media_type="text/html; charset=utf-8"
    )


@app.get("/fluxogramas", include_in_schema=False)
def pagina_fluxogramas() -> FileResponse:
    """Pré-visualização viva dos fluxogramas de triagem (ferramenta interna).

    Edita-se um JSON em app/data/rules/, guarda-se, e a árvore aparece
    redesenhada aqui (as regras são relidas do disco a cada pedido em
    /api/fluxogramas). Não está ligada à interface do utente de propósito:
    destina-se a quem edita/valida regras, não ao público.
    """
    return FileResponse(
        PASTA_STATIC / "fluxogramas.html", media_type="text/html; charset=utf-8"
    )


if __name__ == "__main__":  # permite `python -m app.main`
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
