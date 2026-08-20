# -*- coding: utf-8 -*-
"""Marcar reescritas como clinicamente validadas — CLI (v0.15.3).

Desde a v0.15.2 (aconselhamento) e a v0.15.3 (perguntas), cada reescrita
mostrada ao utente tem estado de validação clínica (`validado`,
`validado_por`, `validado_em`) no seu ficheiro editável. Marcar um item à
mão obriga a mexer em três campos num JSON grande — e, no caso do
aconselhamento, ainda a lembrar-se de correr o `aplicar` para o SHA-256 em
`fonte.reescritas` não ficar dessincronizado. Este CLI faz isso tudo de
uma vez, com a chave clínica exata como identificador.

Uso típico (correr a partir da raiz do projeto):

    # Ver o que está por validar (a lista é longa; --contem filtra)
    python scripts/marcar_validado.py perguntas --listar
    python scripts/marcar_validado.py perguntas --listar --contem "dor no peito"

    # Marcar um ou mais itens como validados (a chave é o texto clínico)
    python scripts/marcar_validado.py perguntas "Dor precordial?" \
        --por "Dra. Exemplo (Triagem)"

    # Datar explicitamente (por omissão usa a data de hoje)
    python scripts/marcar_validado.py aconselhamento \
        "Não reativo e não respira: iniciar T-CPR" \
        --por "Dr. Exemplo" --em 2026-07-18

    # Reverter uma validação
    python scripts/marcar_validado.py perguntas "Dor precordial?" --desmarcar

Notas de comportamento:

- A chave é comparada com espaços colapsados (a mesma normalização de todo
  o projeto), por isso copiar/colar da tabela ou do /revisao funciona mesmo
  com espaços a mais. Se a chave não existir, o script sugere as mais
  parecidas em vez de falhar às cegas.
- `aconselhamento`: depois de gravar, corre automaticamente
  `aplicar_aconselhamento_utente.py` — só para ressincronizar o SHA-256
  (as frases não mudam, e o aplicar é idempotente).
- `perguntas`: não precisa de aplicar nada; o estado vive só em
  `perguntas_utente.json` e o motor lê-o no arranque (portão de produção).
- O ficheiro é reescrito no formato canónico (indent=2, UTF-8 sem escapes,
  newline final) — um `git diff` depois de marcar mostra SÓ os campos de
  validação do item tocado.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from _aconselhamento_utente import FICHEIRO_REESCRITAS, carregar_reescritas
from _perguntas_utente import FICHEIRO_PERGUNTAS, carregar_perguntas

RE_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Configuração por alvo: ficheiro editável, carregador (que valida a
# estrutura antes de mexermos), e script a correr depois de gravar.
ALVOS = {
    "aconselhamento": {
        "ficheiro": FICHEIRO_REESCRITAS,
        "carregar": carregar_reescritas,
        "aplicar_depois": RAIZ / "scripts" / "aplicar_aconselhamento_utente.py",
        "nome_item": "reescrita do aconselhamento",
    },
    "perguntas": {
        "ficheiro": FICHEIRO_PERGUNTAS,
        "carregar": carregar_perguntas,
        "aplicar_depois": None,  # estado vive só no JSON; o motor lê-o
        "nome_item": "reescrita de pergunta",
    },
}


def _norm(texto: str) -> str:
    """Espaços (incl. NBSP) colapsados num só — igual a normalizar()."""
    return " ".join(str(texto).split())


def resolver_chave(itens: dict, pedida: str) -> str | None:
    """Devolve a chave REAL do registo que corresponde à pedida, ou None.

    A comparação colapsa espaços dos dois lados: as chaves do ficheiro já
    estão normalizadas por construção, mas quem cola da tabela pode trazer
    espaços duplos ou NBSP e não deve ser castigado por isso.
    """
    alvo = _norm(pedida)
    for chave in itens:
        if _norm(chave) == alvo:
            return chave
    return None


def sugerir(itens: dict, pedida: str, quantas: int = 5) -> list[str]:
    """Chaves parecidas com a pedida, para a mensagem de erro ajudar.

    Junta duas heurísticas: conter o texto pedido (o caso "escrevi só um
    pedaço") e semelhança difflib (o caso "enganei-me numa palavra").
    """
    alvo = _norm(pedida).casefold()
    contem = [c for c in itens if alvo and alvo in _norm(c).casefold()]
    parecidas = difflib.get_close_matches(
        _norm(pedida), [_norm(c) for c in itens], n=quantas, cutoff=0.5
    )
    # difflib devolve as versões normalizadas == originais (chaves já
    # normalizadas), por isso podem juntar-se diretamente.
    saida: list[str] = []
    for c in contem + parecidas:
        if c not in saida:
            saida.append(c)
    return saida[:quantas]


def marcar_itens(
    dados: dict,
    chaves: list[str],
    *,
    por: str | None,
    em: str | None,
    desmarcar: bool = False,
) -> tuple[list[str], dict[str, list[str]]]:
    """Aplica a marcação em memória. Devolve (resolvidas, falhadas).

    `falhadas` mapeia cada chave não encontrada para as sugestões. Não grava
    nada — quem chama decide (e os testes usam isto diretamente com dados
    seus, sem tocar nos ficheiros reais).
    """
    itens = dados["itens"]
    resolvidas: list[str] = []
    falhadas: dict[str, list[str]] = {}
    for pedida in chaves:
        real = resolver_chave(itens, pedida)
        if real is None:
            falhadas[pedida] = sugerir(itens, pedida)
            continue
        item = itens[real]
        if desmarcar:
            item["validado"] = False
            item["validado_por"] = None
            item["validado_em"] = None
        else:
            item["validado"] = True
            item["validado_por"] = por
            item["validado_em"] = em
        resolvidas.append(real)
    return resolvidas, falhadas


def gravar(dados: dict, caminho: Path) -> None:
    """Reescreve o ficheiro no formato canónico do projeto (byte-estável)."""
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _listar(dados: dict, contem: str | None, todos: bool) -> None:
    itens = dados["itens"]
    filtro = _norm(contem).casefold() if contem else ""
    validados = sum(1 for i in itens.values() if i.get("validado"))
    mostrados = 0
    for chave, item in itens.items():
        if filtro and filtro not in _norm(chave).casefold():
            continue
        if item.get("validado"):
            if not todos:
                continue
            estado = f"[validado {item.get('validado_em')}, {item.get('validado_por')}]"
        else:
            estado = "[por validar]"
        print(f"  {estado} {chave}")
        mostrados += 1
    extra = f" ({mostrados} na lista acima)" if (filtro or not todos) else ""
    print(
        f"\n{len(itens)} itens: {validados} validados, "
        f"{len(itens) - validados} por validar{extra}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Marcar reescritas (aconselhamento ou perguntas) como "
        "clinicamente validadas, sem editar o JSON à mão.",
    )
    parser.add_argument("alvo", choices=sorted(ALVOS), help="que ficheiro de reescritas mexer")
    parser.add_argument(
        "chaves",
        nargs="*",
        help="texto clínico EXATO de cada item (entre aspas); " "espaços a mais são tolerados",
    )
    parser.add_argument(
        "--listar",
        action="store_true",
        help="listar itens por validar (com --todos, também os validados) e sair",
    )
    parser.add_argument("--contem", help="ao listar, filtrar chaves que contêm este texto")
    parser.add_argument("--todos", action="store_true", help="ao listar, incluir os já validados")
    parser.add_argument("--por", help="quem valida (obrigatório ao marcar)")
    parser.add_argument("--em", help="data da validação AAAA-MM-DD (por omissão, hoje)")
    parser.add_argument(
        "--desmarcar",
        action="store_true",
        help="reverter a validação dos itens indicados",
    )
    args = parser.parse_args(argv)

    cfg = ALVOS[args.alvo]
    dados = cfg["carregar"]()  # valida a estrutura; falha cedo se partido

    if args.listar:
        _listar(dados, args.contem, args.todos)
        return 0

    if not args.chaves:
        parser.error("indique pelo menos uma chave (ou use --listar)")
    if not args.desmarcar:
        if not args.por or not args.por.strip():
            parser.error("--por é obrigatório ao marcar como validado")
        if args.em is None:
            args.em = date.today().isoformat()
        if not RE_DATA.match(args.em):
            parser.error(f"--em tem de ser AAAA-MM-DD (recebi {args.em!r})")
        try:
            date.fromisoformat(args.em)
        except ValueError:
            parser.error(f"--em não é uma data real: {args.em!r}")

    resolvidas, falhadas = marcar_itens(
        dados,
        args.chaves,
        por=(args.por.strip() if args.por else None),
        em=args.em,
        desmarcar=args.desmarcar,
    )

    if falhadas:
        for pedida, sugestoes in falhadas.items():
            print(f"ERRO: chave não encontrada: {pedida!r}", file=sys.stderr)
            for s in sugestoes:
                print(f"  parecida: {s!r}", file=sys.stderr)
        print(
            "Nada foi gravado. Use --listar --contem para encontrar a chave exata.",
            file=sys.stderr,
        )
        return 1

    gravar(dados, cfg["ficheiro"])
    verbo = "desmarcado(s)" if args.desmarcar else "validado(s)"
    print(f"{len(resolvidas)} item(ns) {verbo} em {cfg['ficheiro'].name}:")
    for chave in resolvidas:
        print(f"  - {chave}")

    if cfg["aplicar_depois"] is not None:
        # Só para ressincronizar o SHA-256 em fonte.reescritas — as frases
        # não mudaram e o aplicar é idempotente, por isso isto é seguro.
        print(f"\nA ressincronizar (corre {cfg['aplicar_depois'].name})...")
        res = subprocess.run(
            [sys.executable, str(cfg["aplicar_depois"])],
            cwd=str(RAIZ),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print(res.stdout, file=sys.stderr)
            print(res.stderr, file=sys.stderr)
            print(
                "ERRO: o aplicar falhou depois de gravar — corra-o à mão " "antes de fazer commit.",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
