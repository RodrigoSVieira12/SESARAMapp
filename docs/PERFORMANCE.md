# Performance

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
(200 iterações por endpoint depois de aquecimento). São ordens de
grandeza numa máquina concreta, para detetar regressões entre versões —
não uma promessa de produção. O scraping não entra no caminho medido: o
encaminhamento lê apenas o cache local, como em produção.*

## Results (v0.13.1, 2026-07-13)

| Pedido | n | erros | média | mediana | p95 | máx |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GET /api/saude | 200 | 0 | 1.7 ms | 1.7 ms | 1.9 ms | 2.5 ms |
| GET /api/queixas | 200 | 0 | 1.9 ms | 1.8 ms | 2.0 ms | 2.7 ms |
| POST /api/triagem (1.ª pergunta) | 200 | 0 | 2.1 ms | 2.1 ms | 2.5 ms | 4.1 ms |
| POST /api/triagem (red flags) | 200 | 0 | 2.5 ms | 2.2 ms | 2.7 ms | 42.7 ms |
| POST /api/encaminhamento (amarelo, Funchal) | 200 | 0 | 7.2 ms | 6.3 ms | 8.4 ms | 53.8 ms |
| GET /api/unidades/proxima | 200 | 0 | 4.3 ms | 3.9 ms | 4.7 ms | 46.4 ms |

Environment: Python 3.12.3 · Linux x86_64 · medido em processo (TestClient, sem rede).

## Why it is this fast

No database and no network calls in the request path: the rules, the
units and the road network live in memory after startup, and the waiting
times come from a local file cache. The most expensive request is the
routing one, which computes distances and road times for all candidate
units of the island — still a few milliseconds for the whole of Madeira.
