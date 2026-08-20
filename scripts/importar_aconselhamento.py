# -*- coding: utf-8 -*-
"""Importador do Aconselhamento de Manchester: Excel -> aconselhamento.json.

A tabela de referência traz, além do motivo/prioridade/discriminador, uma
coluna de ACONSELHAMENTO (o que fazer). Este importador lê essa coluna e gera
app/data/aconselhamento.json com uma lista de conselhos por (fluxograma, cor).

Modelo de saída:

    {
      "descricao": "...",
      "fonte": {
        "tabela":     { ficheiro, sha256, modificado_em, linhas, importado_em },
        "reescritas": { ficheiro, sha256 }
      },
      "fluxos": {
        "<fluxo_id>": {
          "<cor>": { "itens": [ {"texto": "...", "texto_utente": "...",
                                 "texto_utente_en": "...", "validado": false,
                                 "validado_por": null, "validado_em": null},
                                ... ] },
          ...
        },
        ...
      }
    }

Regras de construção (ver docs/GUIA_DOS_DADOS.md):

  * O aconselhamento é uma LISTA por (motivo, prioridade). Como a tabela é uma
    junção motivo x discriminador, o mesmo conselho repete-se em várias linhas;
    por isso deduplicamos por (fluxo, cor) mantendo a ordem de primeira
    aparição (dict.fromkeys).
  * O fluxo é identificado por slug(motivo), tal como no importar_manchester.py
    (mapa 1:1 confirmado: 56 motivos <-> 56 ficheiros de regras). Desde a
    v0.15.2 o slug(), o normalizar() e o mapa de cores vivem UMA vez em
    scripts/_manchester_comum.py, partilhados pelos dois importadores — antes
    eram duas cópias que tinham de andar sincronizadas à mão.
  * A prioridade P1-P5 traduz-se na cor de Manchester (ver app/core/cores.py).
  * As colunas aconstit (título) e aconsdes (descrição) são, na prática, o
    mesmo texto; usamos aconstit e normalizamos os espaços.
  * O bloco `fonte.tabela` regista de que Excel exato os dados vieram
    (nome, SHA-256, data de modificação, nº de linhas, data da importação):
    sem isto, "o Excel mudou?" não tinha resposta (v0.15.2).

Dupla gravação texto / texto_utente (política de segurança):

  * texto: o conselho clínico tal como está na tabela (fidelidade). É o que os
    integradores recebem via /integracao/triagem.
  * texto_utente: a reescrita em linguagem do dia a dia, com a variante
    inglesa texto_utente_en e o estado de validação clínica por item. Desde a
    v0.15.2 vive em app/data/aconselhamento_utente.json (editável pela equipa
    clínica, sem tocar em código) e é aplicada pela MESMA função de fusão do
    scripts/aplicar_aconselhamento_utente.py — que também serve para o dia a
    dia, sem precisar do Excel. Itens que são só do profissional (avaliar
    escalas, ativar meios, fármacos por nome, isolamento...) NÃO recebem
    texto_utente de propósito. O frontend só mostra itens COM texto_utente;
    ao contrário das perguntas, aqui NÃO há recuo para o texto clínico, porque
    mostrar uma instrução clínica crua a um leigo pode ser inseguro.

Reexecutável: reescreve app/data/aconselhamento.json a cada execução.
Sujeito a validação clínica antes de uso real.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _aconselhamento_utente import carregar_reescritas
from _manchester_comum import (
    COR_DA_PRIORIDADE,
    PRIORIDADES_VALIDAS,
    normalizar,
    sha256_de,
    slug,
)
from aplicar_aconselhamento_utente import fundir

RAIZ = Path(__file__).resolve().parent.parent
EXCEL_OMISSO = Path(
    "/mnt/user-data/uploads/Table_Motivo_Prioridade_Discriminadores_Aconselhamento.xls"
)
SAIDA = RAIZ / "app" / "data" / "aconselhamento.json"
PASTA_RULES = RAIZ / "app" / "data" / "rules"


def carregar_tabela(caminho: Path) -> pd.DataFrame:
    df = pd.read_excel(caminho, engine="xlrd", header=None)
    df.columns = [
        "priomotiid",
        "motivoid",
        "motivotit",
        "prioriddes",
        "priodisid",
        "discrimiid",
        "discrimtit",
        "discrimdes",
        "aconstit",
        "aconsdes",
    ]
    df["motivotit"] = df["motivotit"].map(normalizar)
    df["prioriddes"] = df["prioriddes"].map(lambda x: normalizar(x).upper())
    df["aconselhamento"] = df["aconstit"].map(normalizar)
    # Manter apenas linhas de dados reais (prioridade P1-P5); descarta os dois
    # cabecalhos e a linha em branco, e qualquer linha sem conselho.
    df = df[df["prioriddes"].isin(PRIORIDADES_VALIDAS)]
    df = df[df["aconselhamento"] != ""]
    return df.reset_index(drop=True)


def gerar(caminho_excel: Path) -> dict:
    df = carregar_tabela(caminho_excel)

    fluxos_conhecidos = {p.stem for p in PASTA_RULES.glob("*.json") if p.stem != "red_flags"}

    # ordem de aparicao dos fluxos e das cores, para uma saida estavel
    ordem_fluxos = list(dict.fromkeys(df["motivotit"].tolist()))
    ordem_cores = ["vermelho", "laranja", "amarelo", "verde", "azul"]

    fluxos: dict[str, dict] = {}
    orfaos: list[str] = []

    for motivo in ordem_fluxos:
        fid = slug(motivo)
        if fid not in fluxos_conhecidos:
            orfaos.append(f"{motivo} -> {fid}")
            continue
        sub = df[df["motivotit"] == motivo]
        bloco: dict[str, dict] = {}
        for cor in ordem_cores:
            prio = {v: k for k, v in COR_DA_PRIORIDADE.items()}[cor]
            linhas = sub[sub["prioriddes"] == prio]["aconselhamento"].tolist()
            # dedupe mantendo a ordem de primeira aparicao
            itens_txt = list(dict.fromkeys(linhas))
            if not itens_txt:
                continue
            bloco[cor] = {"itens": [{"texto": t} for t in itens_txt]}
        if bloco:
            fluxos[fid] = bloco

    # A camada do utente (texto_utente, _en, validação) e o registo das
    # reescritas entram pela MESMA função do aplicar_… — uma única lógica.
    dados: dict = {"fluxos": fluxos}
    fundir(dados, carregar_reescritas()["itens"])
    rel = dados.pop("_relatorio")

    # Proveniência da tabela: o que permite responder "de que Excel veio isto?"
    dados["fonte"]["tabela"] = {
        "ficheiro": caminho_excel.name,
        "sha256": sha256_de(caminho_excel),
        "modificado_em": datetime.fromtimestamp(
            caminho_excel.stat().st_mtime, tz=timezone.utc
        ).strftime("%Y-%m-%d"),
        "linhas": int(len(df)),
        "importado_em": datetime.now(tz=timezone.utc).strftime("%Y-%m-%d"),
    }

    # --- Relatorio -----------------------------------------------------
    print(f"Fluxos com aconselhamento: {len(dados['fluxos'])}")
    print(f"Itens (fluxo,cor) no total: {rel['total']}")
    pct = (100.0 * rel["com_utente"] / rel["total"]) if rel["total"] else 0.0
    print(f"  com texto_utente: {rel['com_utente']} ({pct:.0f}%)")
    print(f"  sem texto_utente (so backend): {rel['total'] - rel['com_utente']}")
    if orfaos:
        print("AVISO: motivos sem ficheiro de regra (ignorados):")
        for o in orfaos:
            print("  -", o)
    if rel["sem_uso"]:
        print(
            f"AVISO: {len(rel['sem_uso'])} chave(s) das reescritas sem "
            f"correspondência na tabela (órfãs; o verificador bloqueia):"
        )
        for c in rel["sem_uso"]:
            print(f"  - {c[:88]}")
    # itens distintos ainda sem versao de utente, por frequencia, para
    # orientar quem quiser alargar a cobertura das reescritas
    from collections import Counter

    freq = Counter(
        normalizar(it["texto"])
        for cores in dados["fluxos"].values()
        for bloco in cores.values()
        for it in bloco["itens"]
        if not it.get("texto_utente")
    )
    se_faltam = freq.most_common()
    if se_faltam:
        print(f"\nItens distintos sem texto_utente: {len(se_faltam)} " f"(os 15 mais frequentes)")
        for texto, n in se_faltam[:15]:
            print(f"  {n:>3}x  {texto[:88]}")

    return dados


def main(argv: list[str]) -> int:
    caminho = Path(argv[1]) if len(argv) > 1 else EXCEL_OMISSO
    if not caminho.exists():
        print(f"ERRO: Excel nao encontrado: {caminho}", file=sys.stderr)
        return 1
    dados = gerar(caminho)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nEscrito: {SAIDA.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
