# -*- coding: utf-8 -*-
"""Verificador das perguntas em linguagem do utente (v0.15.3).

O par do `verificar_aconselhamento.py`, agora para a OUTRA metade do
conteúdo leigo: as perguntas de triagem. As reescritas ligam-se aos
discriminadores pela string exata do texto clínico — bastaria corrigir um
espaço ou uma palavra num dos lados para a ligação partir EM SILÊNCIO (o
utente passaria a ver o texto clínico, sem nenhum erro em lado nenhum).
Este script transforma essa deriva silenciosa em erro de CI.

ERROS (código != 0):
  - chave órfã: reescrita cujo texto clínico já não existe em nenhum
    discriminador (deriva da tabela/regras);
  - discriminador sem entrada: a cobertura tem de ser total — um buraco
    novo é uma regressão de legibilidade (o utente veria o texto clínico);
  - divergência regras <-> reescritas: o `texto_utente`/`texto_utente_en`
    de um discriminador não espelha a entrada do registo (alguém editou as
    reescritas sem correr o aplicar, ou editou a camada gerada das regras
    à mão) — a mensagem diz o que correr;
  - item sem PT ou sem EN (defesa em profundidade; o carregador já o exige
    no ficheiro real);
  - validado=true sem `validado_por` e/ou `validado_em` (AAAA-MM-DD): um
    "aprovado" sem registo não serve de registo.

AVISOS (não bloqueiam):
  - colisões DENTRO do mesmo fluxo: dois discriminadores distintos que
    colapsam na mesma pergunta leiga — como o motor pergunta uma de cada
    vez, o utente pode ver "a mesma pergunta" duas vezes seguidas e achar
    que a aplicação se enganou; a revisão clínica decide se diferencia as
    frases (entre fluxos diferentes a colisão é inofensiva: só corre um);
  - estilo: reescrita sem nenhum «?» (uma pergunta que não pergunta) ou
    com travessões (a política do ficheiro proíbe-os).

Uso:
    python scripts/verificar_perguntas.py        # relatório + código de saída
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _manchester_comum import normalizar  # noqa: E402
from _perguntas_utente import (  # noqa: E402
    FICHEIRO_PERGUNTAS,
    REGISTO_PERGUNTAS,
)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_REGRAS = RAIZ / "app" / "data" / "rules"

_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRAVESSOES = ("\u2014", "\u2013")  # — e –


def _carregar_discriminadores(pasta: Path) -> list[tuple[str, str, dict]]:
    """Lista [(fluxo_id, chave_normalizada, disc)] de todas as regras."""
    saida: list[tuple[str, str, dict]] = []
    for caminho in sorted(pasta.glob("*.json")):
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        if dados.get("id") == "red_flags":
            continue
        for disc in dados.get("perguntas", []):
            saida.append((dados["id"], normalizar(disc.get("texto")), disc))
    return saida


def analisar(
    pasta_regras: Path = PASTA_REGRAS,
    registo: dict[str, dict] | None = None,
) -> tuple[list[str], list[str]]:
    """Corre as verificações. Devolve (erros, avisos).

    Os caminhos e o registo são parametrizáveis para os testes; por omissão
    usa os ficheiros reais do projeto.
    """
    if registo is None:
        registo = REGISTO_PERGUNTAS
    registo_norm = {normalizar(c): i for c, i in registo.items()}
    discs = _carregar_discriminadores(pasta_regras)
    usadas = {chave for _fid, chave, _d in discs}

    erros: list[str] = []
    avisos: list[str] = []

    # 1) Chaves órfãs (ERRO): reescrita -> texto clínico que já não existe.
    orfas = [c for c in registo_norm if c not in usadas]
    if orfas:
        erros.append(
            f"{len(orfas)} chave(s) das reescritas órfã(s) (não correspondem "
            f"a nenhum discriminador atual — provável deriva de texto nas "
            f"regras ou na tabela de origem):"
        )
        for c in orfas:
            erros.append(f"    chave órfã: {c}")

    # 2) Cobertura total (ERRO): discriminador sem entrada = o utente veria
    #    o texto clínico — uma regressão a apanhar aqui, não em produção.
    sem_entrada = [f"{fid}: {chave!r}" for fid, chave, _d in discs if chave not in registo_norm]
    if sem_entrada:
        distintos = list(dict.fromkeys(sem_entrada))
        erros.append(
            f"{len(distintos)} discriminador(es) sem entrada nas reescritas "
            f"(acrescentar a app/data/perguntas_utente.json e correr "
            f"scripts/aplicar_perguntas_utente.py):"
        )
        for linha in distintos[:12]:
            erros.append(f"    sem entrada: {linha}")

    # 3) Pares completos (ERRO, defesa em profundidade).
    incompletos = [c for c, i in registo.items() if not i.get("pt") or not i.get("en")]
    if incompletos:
        erros.append(f"{len(incompletos)} item(ns) das reescritas sem PT ou sem EN:")
        for c in incompletos:
            erros.append(f"    incompleto: {c}")

    # 4) Divergência regras <-> reescritas (ERRO): cada discriminador tem de
    #    espelhar a entrada do registo. Como o estado de validação NÃO é
    #    copiado para as regras (v0.15.3), comparar os textos item a item
    #    cobre as duas derivas do SHA do aconselhamento: "editei as
    #    reescritas e esqueci-me de aplicar" e "editei a camada gerada das
    #    regras à mão" — e diz exatamente quais os itens.
    divergentes: list[str] = []
    for fid, chave, disc in discs:
        entrada = registo_norm.get(chave)
        if entrada is None:
            continue  # já apanhado em (2)
        if disc.get("texto_utente") != entrada.get("pt") or disc.get(
            "texto_utente_en"
        ) != entrada.get("en"):
            divergentes.append(f"{fid}: {chave!r}")
    if divergentes:
        distintos = list(dict.fromkeys(divergentes))
        erros.append(
            f"{len(distintos)} discriminador(es) divergem das reescritas "
            f"(reescritas editadas sem aplicar, ou camada do utente das "
            f"regras editada à mão — correr "
            f"scripts/aplicar_perguntas_utente.py):"
        )
        for linha in distintos[:12]:
            erros.append(f"    diverge: {linha}")

    # 5) Estado de validação coerente (ERRO): validado=true exige quem e
    #    quando (AAAA-MM-DD).
    mal_validados = [
        c
        for c, i in registo.items()
        if i.get("validado")
        and (
            not i.get("validado_por")
            or not isinstance(i.get("validado_em"), str)
            or not _DATA_RE.match(i["validado_em"])
        )
    ]
    if mal_validados:
        erros.append(
            f"{len(mal_validados)} item(ns) marcados validado=true sem "
            f"'validado_por' e/ou 'validado_em' (AAAA-MM-DD):"
        )
        for c in mal_validados:
            erros.append(f"    validação incompleta: {c}")

    # 6) Colisões dentro do MESMO fluxo (AVISO): a mesma pergunta leiga em
    #    mais de um discriminador — o utente responde «não» e vê a seguir o
    #    que parece a mesma pergunta outra vez.
    colisoes: list[str] = []
    por_fluxo: dict[str, dict[str, list[str]]] = {}
    for fid, chave, _d in discs:
        entrada = registo_norm.get(chave)
        if entrada is None:
            continue
        por_fluxo.setdefault(fid, {}).setdefault(entrada["pt"], []).append(chave)
    for fid, frases in sorted(por_fluxo.items()):
        for frase, chaves in frases.items():
            distintas = sorted(set(chaves))
            if len(distintas) > 1:
                colisoes.append(
                    f"{fid}: «{frase[:64]}…» <- " + " | ".join(distintas)
                    if len(frase) > 64
                    else f"{fid}: «{frase}» <- " + " | ".join(distintas)
                )
    if colisoes:
        avisos.append(
            f"{len(colisoes)} colisão(ões) de pergunta leiga dentro do mesmo "
            f"fluxo (dois discriminadores seguidos podem parecer a mesma "
            f"pergunta; a revisão clínica decide se diferencia as frases):"
        )
        for linha in colisoes[:10]:
            avisos.append(f"    {linha}")

    # 6b) Texto clínico REPETIDO no mesmo fluxo (AVISO): herdado da tabela
    #     de origem — o motor pergunta o mesmo duas vezes (em prioridades
    #     diferentes). Não é um problema das reescritas; fica listado para a
    #     sessão de revisão, a corrigir na origem, não aqui.
    repetidos: list[str] = []
    for fid, frases in sorted(por_fluxo.items()):
        contagem: dict[str, int] = {}
        for _frase, chaves in frases.items():
            for c in chaves:
                contagem[c] = contagem.get(c, 0) + 1
        for c, n in contagem.items():
            if n > 1:
                repetidos.append(f"{fid}: {c!r} ×{n}")
    if repetidos:
        avisos.append(
            f"{len(repetidos)} texto(s) clínico(s) repetido(s) dentro do "
            f"mesmo fluxo (o motor faz a mesma pergunta mais de uma vez, em "
            f"prioridades diferentes — herdado da tabela de origem; a "
            f"corrigir na origem, não aqui):"
        )
        for linha in repetidos[:10]:
            avisos.append(f"    {linha}")

    # 7) Estilo (AVISO): perguntas que não perguntam, ou com travessões.
    sem_interrogacao = [
        c
        for c, i in registo.items()
        if "?" not in (i.get("pt") or "") or "?" not in (i.get("en") or "")
    ]
    if sem_interrogacao:
        avisos.append(
            f"{len(sem_interrogacao)} reescrita(s) sem nenhum «?» (uma "
            f"pergunta que não pergunta):"
        )
        for c in sem_interrogacao[:8]:
            avisos.append(f"    sem «?»: {c}")
    com_travessao = [
        c
        for c, i in registo.items()
        if any(t in (i.get("pt") or "") + (i.get("en") or "") for t in _TRAVESSOES)
    ]
    if com_travessao:
        avisos.append(
            f"{len(com_travessao)} reescrita(s) com travessão/meio-travessão "
            f"(a política do ficheiro pede vírgulas, parênteses e hífen "
            f"simples):"
        )
        for c in com_travessao[:8]:
            avisos.append(f"    com travessão: {c}")

    return erros, avisos


def _relatorio_stdout() -> int:
    registo = REGISTO_PERGUNTAS
    discs = _carregar_discriminadores(PASTA_REGRAS)
    validados = sum(1 for i in registo.values() if i.get("validado"))
    erros, avisos = analisar()

    print("Perguntas ao utente — verificação")
    print(f"  Reescritas          : {len(registo)} " f"({validados} validada(s) clinicamente)")
    print(
        f"  Discriminadores     : {len(discs)} em " f"{len({fid for fid, _c, _d in discs})} fluxos"
    )
    print(f"  Ficheiro editável   : " f"{FICHEIRO_PERGUNTAS.relative_to(RAIZ)}")

    for a in avisos:
        print(f"AVISO: {a}" if not a.startswith("    ") else a)
    for e in erros:
        print(f"ERRO: {e}" if not e.startswith("    ") else e)

    if erros:
        print("\nFALHOU: corrigir os erros acima (o CI bloqueia aqui).")
        return 1
    print("\nOK: reescritas e regras alinhadas, sem chaves órfãs nem buracos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_relatorio_stdout())
