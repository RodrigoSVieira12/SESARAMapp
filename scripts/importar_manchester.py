# -*- coding: utf-8 -*-
"""Importador da Triagem de Manchester: Excel -> ficheiros de regras JSON.

Lê a tabela oficial (Fluxograma | Prioridade | Discriminador | Descrição)
e gera um ficheiro app/data/rules/<fluxo>.json por fluxograma, no modelo
por discriminadores (v0.14.0): cada pergunta é um discriminador com a sua
prioridade (P1-P5), a cor de Manchester correspondente e a descrição
clínica (coluna H). O motor percorre-os por ordem de prioridade e o
primeiro "sim" decide a cor; se todos forem "não", o desfecho é azul.

Reexecutável: apaga e regenera app/data/rules/*.json (exceto red_flags.json).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
# slug() e o mapa prioridade->cor são partilhados com o importador do
# aconselhamento desde a v0.15.2 (antes eram duas cópias que tinham de
# andar sincronizadas à mão): ver scripts/_manchester_comum.py.
from _manchester_comum import COR_DA_PRIORIDADE, slug  # noqa: F401
from _manchester_fluxos import FLUXOS
from _manchester_traducoes import DISCRIMINADORES_EN
from _perguntas_utente import PERGUNTAS_UTENTE

# Linhas que NÃO são discriminadores de sim/não:
#  - o divisor visual "limite de risco" da tabela de Manchester;
#  - o marcador do desfecho P5 (nenhum discriminador positivo) -> é o
#    recuo automático do motor, não uma pergunta;
#  - uma instrução de preenchimento; e linhas em branco.
MARCADORES = {
    "------- LIMITE RISCO -------",
    "Sem discriminador Positivo",
    "USE OUTRO DISCRIMINADOR",
    "",
}

FONTE_PT = (
    "Discriminadores do Sistema de Triagem de Manchester, organizados por "
    "prioridade clínica (P1-P5). Importados da tabela de referência; "
    "sujeitos a validação clínica antes de uso real."
)
FONTE_EN = (
    "Manchester Triage System discriminators, organised by clinical "
    "priority (P1-P5). Imported from the reference table; subject to "
    "clinical validation before real use."
)


def limpar(s) -> str:
    """Tira \\xa0 e espaços das pontas, MANTENDO o espaçamento interno.

    Diferente de _manchester_comum.normalizar() de propósito: os textos dos
    discriminadores ficam gravados tal e qual estão na tabela (fidelidade);
    a normalização agressiva (colapsar espaços internos) é só para as CHAVES
    do aconselhamento, onde o emparelhamento exato é o que importa.
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    return str(s).replace("\xa0", " ").strip()


def carregar_tabela(caminho: Path) -> pd.DataFrame:
    df = pd.read_excel(caminho, engine="xlrd", header=None)
    df = df.iloc[1:].reset_index(drop=True)  # 1.ª linha em branco
    df.columns = ["c0", "c1", "fluxograma", "prioridade", "disc_id", "c5", "texto", "descricao"]
    for c in ("fluxograma", "prioridade", "texto", "descricao"):
        df[c] = df[c].map(limpar)
    return df


def gerar(caminho_excel: Path, pasta_rules: Path) -> dict:
    df = carregar_tabela(caminho_excel)
    # ordem de aparição dos fluxos na tabela (mantém a ordem oficial)
    ordem_fluxos = list(dict.fromkeys(df["fluxograma"].tolist()))

    # apagar regras antigas (menos red_flags.json)
    for antigo in pasta_rules.glob("*.json"):
        if antigo.name != "red_flags.json":
            antigo.unlink()

    resumo = {
        "fluxos": 0,
        "discriminadores": 0,
        "por_prioridade": {},
        "sem_descricao": 0,
        "sem_traducao": [],
    }
    ordem_prioridade = ["P1", "P2", "P3", "P4", "P5"]

    for nome_original in ordem_fluxos:
        fid = slug(nome_original)
        nome_pt, nome_en, desc_pt, desc_en, pediatrico = FLUXOS[fid]
        sub = df[df["fluxograma"] == nome_original]

        perguntas = []
        vistos_ids = set()
        # ordenar por prioridade (P1->P5) preservando a ordem da tabela dentro de cada uma
        sub = sub.copy()
        sub["ord"] = sub["prioridade"].map({p: i for i, p in enumerate(ordem_prioridade)})
        sub = sub.sort_values(["ord"], kind="stable")

        for _, r in sub.iterrows():
            texto = r["texto"]
            if texto in MARCADORES:
                continue
            prioridade = r["prioridade"]
            cor = COR_DA_PRIORIDADE.get(prioridade)
            if cor is None:
                continue
            disc_id = int(r["disc_id"]) if str(r["disc_id"]).strip().isdigit() else None
            # id estável e único dentro do fluxo
            base = (
                f"{fid}_{prioridade.lower()}_{disc_id if disc_id is not None else slug(texto)[:20]}"
            )
            pid = base
            n = 2
            while pid in vistos_ids:
                pid = f"{base}_{n}"
                n += 1
            vistos_ids.add(pid)

            texto_en = DISCRIMINADORES_EN.get(texto)
            if texto_en is None:
                resumo["sem_traducao"].append(texto)
                texto_en = texto  # recuo seguro

            # Perguntas em linguagem do utente (v0.14.1). Recuo seguro para o
            # texto clínico se faltar a versão do utente.
            par_utente = PERGUNTAS_UTENTE.get(texto)
            if par_utente is None:
                resumo.setdefault("sem_utente", []).append(texto)
                texto_utente_pt, texto_utente_en = texto, texto_en
            else:
                texto_utente_pt, texto_utente_en = par_utente

            pergunta = {
                "id": pid,
                "disc_id": disc_id,
                "prioridade": prioridade,
                "cor": cor,
                "texto": texto,
                "texto_utente": texto_utente_pt,
                "texto_en": texto_en,
                "texto_utente_en": texto_utente_en,
            }
            descricao = r["descricao"]
            # descrição só entra se acrescentar algo (não repetir o texto)
            if descricao and descricao != texto:
                pergunta["descricao"] = descricao
            else:
                resumo["sem_descricao"] += 1
            perguntas.append(pergunta)
            resumo["por_prioridade"][prioridade] = resumo["por_prioridade"].get(prioridade, 0) + 1

        fluxo = {
            "id": fid,
            "nome": nome_pt,
            "nome_en": nome_en,
            "descricao": desc_pt,
            "descricao_en": desc_en,
            "pediatrico": pediatrico,
            "fonte": FONTE_PT,
            "fonte_en": FONTE_EN,
            "perguntas": perguntas,
        }
        (pasta_rules / f"{fid}.json").write_text(
            json.dumps(fluxo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        resumo["fluxos"] += 1
        resumo["discriminadores"] += len(perguntas)

    return resumo


if __name__ == "__main__":
    excel = Path(sys.argv[1])
    rules = Path(sys.argv[2])
    rules.mkdir(parents=True, exist_ok=True)
    res = gerar(excel, rules)
    print(f"Fluxos gerados: {res['fluxos']}")
    print(f"Discriminadores: {res['discriminadores']}")
    print(f"Por prioridade: {dict(sorted(res['por_prioridade'].items()))}")
    print(f"Perguntas sem descrição própria: {res['sem_descricao']}")
    faltam = sorted(set(res["sem_traducao"]))
    print(f"Textos sem tradução EN: {len(faltam)}")
    for t in faltam:
        print("   FALTA:", t)
