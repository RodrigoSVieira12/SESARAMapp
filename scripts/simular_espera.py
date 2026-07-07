"""Demonstração offline dos tempos de espera, SEM internet.

Grava no cache um cenário inventado em que o hospital, apesar de mais
perto de Câmara de Lobos, está muito mais cheio do que o centro de saúde
local — para se ver a regra experimental de troca a funcionar e os
tempos a aparecerem na interface, mesmo sem acesso ao site do SESARAM.

    python scripts/simular_espera.py

O cache dura TTL_SEGUNDOS (3 minutos). Passado esse tempo, a app tenta
ir buscar dados reais outra vez.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import espera  # noqa: E402


def main() -> int:
    pacote = {
        "obtido_em": espera._agora_iso(),
        "ok": True,
        "erro": None,
        "unidades": {
            # Centro de saúde de Câmara de Lobos: muito cheio.
            "cs_camara_lobos": {
                "tipo_dados": "geral",
                "em_espera": 9,
                "tempo_medio_min": 120,
                "atendidos": 6,
                "fonte": "centros_saude",
                "atualizado_no_site": "2026-07-04 15:00",
            },
            # Hospital: para um laranja, quase vazio.
            "hnm": {
                "tipo_dados": "por_cor",
                "por_cor": {
                    "laranja": {"em_espera": 1, "tempo_medio_min": 8, "atendidos": 4},
                },
                "geral": {"em_espera": 12, "tempo_medio_min": 40, "atendidos": 30},
                "fonte": "hospital",
                "atualizado_no_site": "2026-07-04 15:00",
            },
            # Machico: um valor simples, para o cenário verde.
            "cs_machico": {
                "tipo_dados": "geral",
                "em_espera": 2,
                "tempo_medio_min": 9,
                "atendidos": 3,
                "fonte": "centros_saude",
                "atualizado_no_site": "2026-07-04 15:00",
            },
        },
        "por_mapear": [],
    }
    espera._gravar_cache(pacote)

    print("Cache de demonstração gravado (vale ~3 minutos).")
    print()
    print("Para ver a REGRA DE TROCA a funcionar:")
    print("  1. Arranca o servidor:  python -m uvicorn app.main:app --reload")
    print("  2. Abre:  http://127.0.0.1:8000/?hora=2026-07-04T15:00:00")
    print("  3. Faz a triagem até dar LARANJA (ou escolhe um sinal de emergência")
    print("     que dê laranja) e, quando pedir a localização, escolhe o concelho")
    print("     de Câmara de Lobos.")
    print()
    print("O Hospital Dr. Nélio Mendonça deve ser sugerido À FRENTE do centro de")
    print("saúde local, com a nota a explicar que, apesar de mais longe, tem menos")
    print("espera. As duas unidades mostram o tempo estimado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
