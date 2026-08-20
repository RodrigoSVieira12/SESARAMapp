#!/usr/bin/env python3
"""Benchmark de desempenho da API (v0.13.1).

O que faz: mede a latência dos endpoints principais chamando a aplicação
EM PROCESSO (TestClient), sem rede nem servidor à parte — ou seja, mede o
custo do nosso código (validação, motor de triagem, encaminhamento,
geração de PDF), não o da máquina de quem testa a rede.

Correr:
    python scripts/benchmark_desempenho.py                # tabela no ecrã
    python scripts/benchmark_desempenho.py --gravar       # + docs/PERFORMANCE.md
    python scripts/benchmark_desempenho.py --iteracoes 1000

Notas honestas (também escritas no documento):
- números medidos numa máquina concreta: servem para ORDENS DE GRANDEZA
  e para detetar regressões, não como promessa de produção;
- o tempo de espera real (scraping) NÃO entra no caminho medido: o
  encaminhamento lê apenas o cache local (espera.do_cache), como em
  produção — a descarga acontece fora do pedido.

Este script é uma ferramenta de linha de comandos: usa print() de
propósito (a aplicação usa logging; ver docs/adr/0011-logging.md).
"""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# O TestClient usa httpx, que regista cada pedido em INFO; num benchmark
# de centenas de chamadas isso é só ruído. Silencia-se AQUI (ferramenta),
# nunca na aplicação.
import logging  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from app.main import app  # noqa: E402
from app.versao import VERSAO  # noqa: E402

DOCUMENTO = RAIZ / "docs" / "PERFORMANCE.md"

# Hora fixa (segunda-feira, 10:00) para o encaminhamento ser determinista:
# o benchmark mede tempo de execução, não variações de horário.
QUANDO = "2026-06-29T10:00:00"

# Os pedidos medidos: nome legível, método, rota e corpo (None = GET).
PEDIDOS: list[tuple[str, str, str, dict | None]] = [
    ("GET /api/saude", "GET", "/api/saude", None),
    ("GET /api/queixas", "GET", "/api/queixas", None),
    (
        "POST /api/triagem (1.ª pergunta)",
        "POST",
        "/api/triagem",
        {"queixa": "agressao", "respostas": {}},
    ),
    (
        "POST /api/triagem (red flags)",
        "POST",
        "/api/triagem",
        {"red_flags": ["inconsciencia"]},
    ),
    (
        "POST /api/encaminhamento (amarelo, Funchal)",
        "POST",
        "/api/encaminhamento",
        {"cor": "amarelo", "lat": 32.6496, "lng": -16.9086, "quando": QUANDO},
    ),
    (
        "GET /api/unidades/proxima",
        "GET",
        "/api/unidades/proxima?lat=32.6496&lng=-16.9086&servico=atendimento_urgente&n=3",
        None,
    ),
]


def _percentil(valores: list[float], p: float) -> float:
    """p em [0,100]; interpolação linear simples (chega para o efeito)."""
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    k = (len(ordenados) - 1) * (p / 100.0)
    baixo = int(k)
    alto = min(baixo + 1, len(ordenados) - 1)
    fracao = k - baixo
    return ordenados[baixo] * (1 - fracao) + ordenados[alto] * fracao


def medir(iteracoes: int = 300, aquecimento: int = 20) -> list[dict]:
    """Mede todos os PEDIDOS e devolve uma lista de resultados.

    Cada resultado: {rota, n, erros, media_ms, mediana_ms, p95_ms, max_ms}.
    Também é chamada pelos testes (com iterações pequenas), para o
    benchmark nunca apodrecer em silêncio.
    """
    cliente = TestClient(app)
    resultados = []
    for nome, metodo, rota, corpo in PEDIDOS:

        def chamada():
            if metodo == "GET":
                return cliente.get(rota)
            return cliente.post(rota, json=corpo)

        for _ in range(aquecimento):
            chamada()

        tempos_ms: list[float] = []
        erros = 0
        for _ in range(iteracoes):
            inicio = time.perf_counter()
            resposta = chamada()
            duracao = (time.perf_counter() - inicio) * 1000.0
            if resposta.status_code != 200:
                erros += 1
            else:
                tempos_ms.append(duracao)

        if not tempos_ms:  # tudo falhou: não inventar estatísticas
            resultados.append(
                {
                    "rota": nome,
                    "n": iteracoes,
                    "erros": erros,
                    "media_ms": 0.0,
                    "mediana_ms": 0.0,
                    "p95_ms": 0.0,
                    "max_ms": 0.0,
                }
            )
            continue
        resultados.append(
            {
                "rota": nome,
                "n": iteracoes,
                "erros": erros,
                "media_ms": statistics.fmean(tempos_ms),
                "mediana_ms": statistics.median(tempos_ms),
                "p95_ms": _percentil(tempos_ms, 95),
                "max_ms": max(tempos_ms),
            }
        )
    return resultados


def _tabela(resultados: list[dict]) -> str:
    linhas = [
        "| Pedido | n | erros | média | mediana | p95 | máx |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in resultados:
        linhas.append(
            f"| {r['rota']} | {r['n']} | {r['erros']} "
            f"| {r['media_ms']:.1f} ms | {r['mediana_ms']:.1f} ms "
            f"| {r['p95_ms']:.1f} ms | {r['max_ms']:.1f} ms |"
        )
    return "\n".join(linhas)


def _ambiente() -> str:
    return (
        f"Python {platform.python_version()} · {platform.system()} "
        f"{platform.machine()} · medido em processo (TestClient, sem rede)"
    )


def _documento(resultados: list[dict], iteracoes: int) -> str:
    data = datetime.now().strftime("%Y-%m-%d")
    return f"""# Performance

Latency of the main API endpoints, measured **in-process** with
FastAPI's `TestClient` — so the numbers reflect the cost of the
application code (validation, triage engine, routing, waiting-time cache
read), not network or deployment overhead. Re-measure at any time with:

```bash
python scripts/benchmark_desempenho.py --gravar
```

**How to read this.** These are order-of-magnitude numbers from one
machine, useful to spot regressions between versions; they are not a
production promise. Real waiting-time scraping is *not* in the measured
path: like in production, `/api/encaminhamento` only reads the local
cache. Errors would be counted in the `erros` column (expected: 0).

*Em português: latências dos endpoints principais, medidas em processo
({iteracoes} iterações por endpoint depois de aquecimento). São ordens de
grandeza numa máquina concreta, para detetar regressões entre versões —
não uma promessa de produção. O scraping não entra no caminho medido: o
encaminhamento lê apenas o cache local, como em produção.*

## Results (v{VERSAO}, {data})

{_tabela(resultados)}

Environment: {_ambiente()}.

## Why it is this fast

No database and no network calls in the request path: the rules, the
units and the road network live in memory after startup, and the waiting
times come from a local file cache. The most expensive request is the
routing one, which computes distances and road times for all candidate
units of the island — still a few milliseconds for the whole of Madeira.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mede a latência dos endpoints principais.")
    parser.add_argument(
        "--iteracoes",
        type=int,
        default=300,
        help="iterações medidas por endpoint (predefinição: 300)",
    )
    parser.add_argument(
        "--aquecimento",
        type=int,
        default=20,
        help="chamadas de aquecimento por endpoint (não medidas)",
    )
    parser.add_argument(
        "--gravar", action="store_true", help="escrever docs/PERFORMANCE.md com os resultados"
    )
    argumentos = parser.parse_args(argv)

    print(
        f"A medir {len(PEDIDOS)} pedidos × {argumentos.iteracoes} iterações "
        f"(+{argumentos.aquecimento} de aquecimento)…\n"
    )
    resultados = medir(argumentos.iteracoes, argumentos.aquecimento)

    largura = max(len(r["rota"]) for r in resultados)
    print(
        f"{'pedido'.ljust(largura)}  {'média':>9} {'mediana':>9} {'p95':>9} {'máx':>9} {'erros':>6}"
    )
    for r in resultados:
        print(
            f"{r['rota'].ljust(largura)}  "
            f"{r['media_ms']:>7.1f}ms {r['mediana_ms']:>7.1f}ms "
            f"{r['p95_ms']:>7.1f}ms {r['max_ms']:>7.1f}ms {r['erros']:>6}"
        )
    print(f"\nAmbiente: {_ambiente()}")

    if argumentos.gravar:
        DOCUMENTO.write_text(_documento(resultados, argumentos.iteracoes), encoding="utf-8")
        print(f"Escrito: {DOCUMENTO.relative_to(RAIZ)}")
    else:
        print("(para gravar em docs/PERFORMANCE.md: --gravar)")

    com_erros = [r for r in resultados if r["erros"]]
    return 1 if com_erros else 0


if __name__ == "__main__":
    raise SystemExit(main())
