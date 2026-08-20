# -*- coding: utf-8 -*-
"""Aplica as reescritas leigas ao aconselhamento.json — SEM Excel (v0.15.2).

O ciclo de edição da equipa clínica passa a ser:

    1. editar app/data/aconselhamento_utente.json (frases PT/EN e estado de
       validação por item);
    2. correr:  python scripts/aplicar_aconselhamento_utente.py
    3. rever o diff e submeter (o CI volta a verificar tudo).

Este script pega no app/data/aconselhamento.json EXISTENTE (os conselhos
clínicos importados da tabela) e refaz, item a item, apenas a camada do
utente: `texto_utente`, `texto_utente_en` e o estado de validação
(`validado`, `validado_por`, `validado_em`), emparelhando pelo texto clínico
exato — a mesma chave do importador. O campo `texto` (clínico) fica INTOCADO;
é ele que alimenta os integradores e o documento de validação clínica.

Ao contrário do importador (`importar_aconselhamento.py`), NÃO precisa da
tabela Excel: serve para o dia a dia (corrigir uma frase, marcar um item como
validado). O importador continua a existir para quando a própria tabela de
origem mudar — e usa exatamente a mesma função de fusão daqui, para não haver
duas lógicas a divergir.

Também grava, em `fonte.reescritas`, o SHA-256 do ficheiro de reescritas: é o
que permite ao verificador apanhar "alguém editou as reescritas e esqueceu-se
de correr este script" (JSON desatualizado = erro no CI). Sem carimbos de
data/hora de propósito: correr duas vezes seguidas produz byte a byte o mesmo
ficheiro (idempotente), e o diff mostra só o que mudou de facto.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _aconselhamento_utente import FICHEIRO_REESCRITAS, carregar_reescritas
from _manchester_comum import normalizar, sha256_de

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO_ACONSELHAMENTO = RAIZ / "app" / "data" / "aconselhamento.json"

DESCRICAO = (
    "Aconselhamento da Triagem de Manchester (o que o utente pode fazer), por "
    "fluxograma e cor. Cada item tem 'texto' (o conselho clinico da tabela de "
    "referencia, para o profissional e para integradores) e, quando existe uma "
    "versao leiga segura, 'texto_utente' (linguagem do dia a dia, mostrada ao "
    "utente), a variante inglesa 'texto_utente_en' e o estado de validacao "
    "clinica ('validado', 'validado_por', 'validado_em'). As reescritas e o "
    "estado de validacao editam-se em app/data/aconselhamento_utente.json e "
    "aplicam-se com scripts/aplicar_aconselhamento_utente.py (sem Excel). "
    "Itens so do profissional ficam sem 'texto_utente' de proposito e nao sao "
    "mostrados ao utente. Ficheiro GERADO: nao editar a mao. Sujeito a "
    "validacao clinica antes de uso real."
)

# Ordem canónica das chaves de cada item, para o JSON ficar legível a quem
# revê (clínico primeiro, depois a camada do utente, depois o estado).
_ORDEM_ITEM = (
    "texto",
    "texto_utente",
    "texto_utente_en",
    "validado",
    "validado_por",
    "validado_em",
)

# Campos da camada do utente: são estes (e só estes) que este script gere.
_CAMPOS_UTENTE = ("texto_utente", "texto_utente_en", "validado", "validado_por", "validado_em")


def _item_ordenado(item: dict) -> dict:
    novo = {c: item[c] for c in _ORDEM_ITEM if c in item}
    for c, v in item.items():
        if c not in novo:
            novo[c] = v
    return novo


def fundir(
    dados: dict, registo: dict[str, dict], caminho_reescritas: Path = FICHEIRO_REESCRITAS
) -> dict:
    """Refaz a camada do utente de `dados` a partir do `registo` de reescritas.

    Muta e devolve `dados`. Devolve também estatísticas via o próprio dict
    (chave interna "_relatorio", removida antes de gravar) para o chamador
    imprimir. Usada pelo importador e por este script — uma única lógica.
    """
    com_utente = 0
    removidos: list[str] = []
    total = 0
    usadas: set[str] = set()

    for _fid, cores in dados.get("fluxos", {}).items():
        for _cor, bloco in cores.items():
            itens_novos = []
            for item in bloco.get("itens", []):
                total += 1
                chave = normalizar(item.get("texto"))
                entrada = registo.get(chave)
                tinha = bool(item.get("texto_utente"))
                # limpar a camada do utente e reconstruí-la do registo
                for campo in _CAMPOS_UTENTE:
                    item.pop(campo, None)
                if entrada:
                    usadas.add(chave)
                    item["texto_utente"] = entrada["pt"]
                    item["texto_utente_en"] = entrada["en"]
                    item["validado"] = bool(entrada.get("validado", False))
                    item["validado_por"] = entrada.get("validado_por")
                    item["validado_em"] = entrada.get("validado_em")
                    com_utente += 1
                elif tinha:
                    removidos.append(chave)
                itens_novos.append(_item_ordenado(item))
            bloco["itens"] = itens_novos

    # Proveniência: preservar o registo da tabela (escrito pelo importador,
    # quando corre com o Excel) e atualizar o das reescritas.
    fonte = dados.get("fonte") or {}
    fonte["tabela"] = fonte.get("tabela")  # mantém (ou explicita null)
    fonte["reescritas"] = {
        "ficheiro": str(caminho_reescritas.relative_to(RAIZ)),
        "sha256": sha256_de(caminho_reescritas),
    }

    # Topo em ordem canónica (descricao, fonte, fluxos), com a descrição
    # regenerada — é texto do sistema, não conteúdo clínico.
    fluxos = dados["fluxos"]
    dados.clear()
    dados["descricao"] = DESCRICAO
    dados["fonte"] = fonte
    dados["fluxos"] = fluxos
    dados["_relatorio"] = {
        "total": total,
        "com_utente": com_utente,
        "removidos": removidos,
        "sem_uso": [c for c in registo if c not in usadas],
    }
    return dados


def main() -> int:
    if not FICHEIRO_ACONSELHAMENTO.exists():
        print(
            "ERRO: app/data/aconselhamento.json não existe. Este script só "
            "atualiza a camada do utente; para criar o ficheiro a partir da "
            "tabela, correr scripts/importar_aconselhamento.py <tabela.xls>.",
            file=sys.stderr,
        )
        return 1

    registo = carregar_reescritas()["itens"]
    dados = json.loads(FICHEIRO_ACONSELHAMENTO.read_text(encoding="utf-8"))
    antes = json.dumps(dados, ensure_ascii=False, sort_keys=True)

    fundir(dados, registo)
    rel = dados.pop("_relatorio")

    depois = json.dumps(dados, ensure_ascii=False, sort_keys=True)
    FICHEIRO_ACONSELHAMENTO.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    pct = round(100 * rel["com_utente"] / rel["total"]) if rel["total"] else 0
    print(
        f"Itens (fluxo,cor): {rel['total']}; com versão de utente: "
        f"{rel['com_utente']} ({pct}%)."
    )
    if rel["removidos"]:
        print(
            f"AVISO: {len(rel['removidos'])} item(ns) PERDERAM a versão de "
            f"utente (chave já não está nas reescritas):"
        )
        for c in dict.fromkeys(rel["removidos"]):
            print(f"    - {c[:88]}")
    if rel["sem_uso"]:
        print(
            f"AVISO: {len(rel['sem_uso'])} chave(s) das reescritas sem "
            f"correspondência no aconselhamento (órfãs — o verificador "
            f"marca isto como ERRO):"
        )
        for c in rel["sem_uso"]:
            print(f"    - {c[:88]}")
    print(
        "Sem alterações."
        if antes == depois
        else f"Atualizado: {FICHEIRO_ACONSELHAMENTO.relative_to(RAIZ)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
