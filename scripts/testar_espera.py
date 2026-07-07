"""Teste ao vivo dos tempos de espera do SESARAM.

Corre na TUA máquina, com internet (o sandbox onde o projeto foi
construído não acede ao site do SESARAM, por isso este teste só faz
sentido no teu computador):

    python scripts/testar_espera.py

Vai às duas páginas do SEISRAM, mostra o que conseguiu ler para cada
unidade e — importante — lista os nomes que o site mostra mas que ainda
não estão em app/data/espera_nomes.json (campo "por_mapear"). Se
aparecer algum, cola-me o output que eu acrescento o mapeamento.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import espera, unidades  # noqa: E402


def main() -> int:
    nomes = {u["id"]: u["nome"] for u in unidades.todas()}
    print("A contactar o SESARAM (pode demorar alguns segundos)…\n")
    dados = espera.obter(force=True)

    if dados.get("erro"):
        print(f"Aviso: {dados['erro']}\n")

    encontradas = dados.get("unidades", {})
    if encontradas:
        print(f"Li tempos para {len(encontradas)} unidade(s):\n")
        for unidade_id, registo in sorted(encontradas.items()):
            nome = nomes.get(unidade_id, unidade_id)
            if registo.get("tipo_dados") == "por_cor":
                partes = [
                    f"{cor}={d.get('tempo_medio_min')}min/{d.get('em_espera')} em espera"
                    for cor, d in (registo.get("por_cor") or {}).items()
                ]
                geral = registo.get("geral") or {}
                print(f"  {nome}")
                print(f"      por cor: {', '.join(partes) or '(vazio)'}")
                print(
                    f"      geral: {geral.get('tempo_medio_min')}min / "
                    f"{geral.get('em_espera')} em espera"
                )
            else:
                print(
                    f"  {nome}: {registo.get('tempo_medio_min')}min / "
                    f"{registo.get('em_espera')} em espera"
                )
            if registo.get("atualizado_no_site"):
                print(f"      (site atualizado: {registo['atualizado_no_site']})")
    else:
        print("Não foi possível ler tempos de nenhuma unidade.")
        print("Pode ser falta de internet, o site estar em baixo, ou ter mudado.")

    por_mapear = dados.get("por_mapear", [])
    if por_mapear:
        print("\nNomes que o site mostra e que ainda NÃO estão mapeados:")
        for nome in por_mapear:
            print(f"  - {nome}")
        print("\n→ Cola-me este output que eu acrescento ao espera_nomes.json.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
