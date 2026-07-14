#!/usr/bin/env python3
"""Relatório da tabela de tempos medidos (app/data/tempos_medidos.json).

Sem argumentos: progresso do preenchimento, por concelho.

  --links [filtro]    Links do Google Maps (modo carro) para os pares por
                      preencher, prontos a abrir. O filtro opcional limita
                      às origens que o contenham (ex.: --links santa_cruz,
                      --links gaula). Fluxo: abrir link, ler tempo e
                      distância, escrever no JSON.

  --divergencias      Para os pares JÁ medidos, compara com a rede
                      calibrada e ordena pelas maiores diferenças: é a
                      lista do que a medição corrigiu (e um radar de
                      gralhas: uma diferença absurda merece reconferir).

Correr:  python scripts/tempos_medidos_relatorio.py [--links [filtro]]
         python scripts/tempos_medidos_relatorio.py --divergencias
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core import unidades, viagem  # noqa: E402
from app.core.tempos_medidos import FICHEIRO  # noqa: E402


def _carregar() -> dict:
    if not FICHEIRO.exists():
        print("Não existe app/data/tempos_medidos.json.")
        print("Gera o esqueleto com: python scripts/atualizar_tempos_medidos.py")
        raise SystemExit(1)
    return json.loads(FICHEIRO.read_text(encoding="utf-8"))


def _nomes_unidades() -> dict[str, str]:
    return {u["id"]: u["nome"] for u in unidades.todas()}


def _coords_unidades() -> dict[str, tuple[float, float]]:
    return {u["id"]: (u["lat"], u["lng"]) for u in unidades.todas()}


def progresso(dados: dict) -> int:
    por_concelho: dict[str, list[int]] = {}
    total = feitos = 0
    for m in dados["medicoes"]:
        concelho = m["origem"].split("/")[0]
        linha = por_concelho.setdefault(concelho, [0, 0])
        for valores in m["destinos"].values():
            total += 1
            linha[1] += 1
            if valores.get("tempo_min") is not None:
                feitos += 1
                linha[0] += 1
    largura = max(len(c) for c in por_concelho)
    print(f"Tempos medidos: {feitos} de {total} pares preenchidos "
          f"({feitos * 100 // total if total else 0}%).\n")
    for concelho in sorted(por_concelho):
        f, t = por_concelho[concelho]
        barra = "#" * (f * 20 // t) if t else ""
        print(f"  {concelho:<{largura}}  {f:>3}/{t:<3}  {barra}")
    if feitos < total:
        print("\nLinks para medir: python scripts/tempos_medidos_relatorio.py --links [filtro]")
    return 0


def links(dados: dict, filtro: str | None) -> int:
    nomes = _nomes_unidades()
    coords = _coords_unidades()
    em_falta = 0
    for m in dados["medicoes"]:
        if filtro and filtro not in m["origem"]:
            continue
        pendentes = [
            uid for uid, v in m["destinos"].items() if v.get("tempo_min") is None
        ]
        if not pendentes:
            continue
        em_falta += len(pendentes)
        print(f"\n{m['nome']}  [{m['origem']}]")
        for uid in pendentes:
            lat_d, lng_d = coords[uid]
            url = (
                "https://www.google.com/maps/dir/?api=1"
                f"&origin={m['lat']},{m['lng']}"
                f"&destination={lat_d},{lng_d}"
                "&travelmode=driving"
            )
            print(f"  -> {nomes[uid]} ({uid})")
            print(f"     {url}")
    if em_falta == 0:
        print("Nada por medir" + (f" para o filtro '{filtro}'." if filtro else ": tudo preenchido."))
    else:
        print(f"\n{em_falta} pares por medir" + (f" (filtro: {filtro})" if filtro else "") + ".")
    return 0


def divergencias(dados: dict) -> int:
    nomes = _nomes_unidades()
    coords = _coords_unidades()
    linhas: list[tuple[float, str]] = []
    for m in dados["medicoes"]:
        for uid, v in m["destinos"].items():
            medido = v.get("tempo_min")
            if medido is None:
                continue
            lat_d, lng_d = coords[uid]
            pela_rede = viagem._tempo_rede(m["lat"], m["lng"], lat_d, lng_d)
            if pela_rede is None:
                continue
            delta = medido - pela_rede
            linhas.append(
                (
                    abs(delta),
                    f"  {delta:+6.1f} min  {m['nome']} -> {nomes[uid]} "
                    f"(medido {medido:.0f}, rede {pela_rede:.0f})",
                )
            )
    if not linhas:
        print("Ainda não há pares medidos para comparar.")
        return 0
    print("Diferença medido vs rede calibrada (maiores primeiro):\n")
    for _, texto in sorted(linhas, reverse=True):
        print(texto)
    print("\nDiferenças grandes são o valor desta tabela (o que o modelo")
    print("errava); diferenças ABSURDAS (ex.: 60 min num par vizinho) são")
    print("provavelmente gralhas a reconferir.")
    return 0


def main() -> int:
    dados = _carregar()
    argumentos = sys.argv[1:]
    if not argumentos:
        return progresso(dados)
    if argumentos[0] == "--links":
        return links(dados, argumentos[1] if len(argumentos) > 1 else None)
    if argumentos[0] == "--divergencias":
        return divergencias(dados)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
