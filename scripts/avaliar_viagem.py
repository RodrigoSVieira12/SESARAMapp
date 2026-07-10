#!/usr/bin/env python3
"""Avaliação do estimador de tempos de viagem (v0.11).

Compara, para cada percurso de referência em
app/data/percursos_referencia.json:

  - o método antigo (v0.10): linha reta ÷ 50 km/h;
  - o método novo (v0.11): rede calibrada de estradas (app/core/viagem.py);
  - o tempo de referência (típico, sem trânsito — POR CONFIRMAR).

Não altera nada: serve para calibrar a rede com números à frente, e para
mostrar ao orientador quanto se ganhou. Acrescentar percursos ao JSON
melhora a avaliação.

Correr:  python scripts/avaliar_viagem.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core import viagem  # noqa: E402
from app.core.geo import haversine_km  # noqa: E402

FICHEIRO_PERCURSOS = RAIZ / "app" / "data" / "percursos_referencia.json"
VELOCIDADE_ANTIGA_KMH = 50  # o que a v0.10 assumia


def main() -> int:
    percursos = json.loads(FICHEIRO_PERCURSOS.read_text(encoding="utf-8"))["percursos"]

    print(f"{'Percurso':<42} {'ref.':>5} {'v0.10':>6} {'v0.11':>6}   erro v0.10 → v0.11")
    print("-" * 92)

    erros_antigo: list[float] = []
    erros_novo: list[float] = []
    for p in percursos:
        (lat1, lng1), (lat2, lng2) = p["de"], p["para"]
        referencia = p["minutos_referencia"]

        reta_km = haversine_km(lat1, lng1, lat2, lng2)
        antigo = reta_km / VELOCIDADE_ANTIGA_KMH * 60

        estimativa = viagem.estimar(lat1, lng1, lat2, lng2)
        if estimativa is None:
            print(f"{p['nome']:<42} {referencia:>5} {antigo:>6.0f} {'—':>6}   (ilhas diferentes)")
            continue
        novo = estimativa["minutos"]

        erro_antigo = antigo - referencia
        erro_novo = novo - referencia
        erros_antigo.append(abs(erro_antigo))
        erros_novo.append(abs(erro_novo))
        print(
            f"{p['nome']:<42} {referencia:>5} {antigo:>6.0f} {novo:>6}   "
            f"{erro_antigo:+5.0f} min → {erro_novo:+3.0f} min"
        )

    if erros_novo:
        media_antigo = sum(erros_antigo) / len(erros_antigo)
        media_novo = sum(erros_novo) / len(erros_novo)
        pior_antigo = max(erros_antigo)
        pior_novo = max(erros_novo)
        print("-" * 92)
        print(
            f"Erro absoluto médio:  v0.10 (linha reta ÷ 50 km/h) = {media_antigo:.1f} min   "
            f"|   v0.11 (rede) = {media_novo:.1f} min"
        )
        print(f"Pior caso:            v0.10 = {pior_antigo:.0f} min   |   v0.11 = {pior_novo:.0f} min")
        print(
            "\nNota: os tempos de referência são típicos e estão por confirmar; a rede\n"
            "afina-se editando app/data/rede_viagem.json (minutos das ligações) e\n"
            "voltando a correr este guião."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
