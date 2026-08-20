# -*- coding: utf-8 -*-
"""Verificador do aconselhamento ao utente (v0.15.1; alargado na v0.15.2).

O aconselhamento leigo liga-se ao conselho clínico da tabela por uma CHAVE que
é a string clínica EXATA (ver app/data/aconselhamento_utente.json). Isto é
frágil: basta o colega corrigir um espaço ou uma palavra na tabela de origem e
a chave deixa de bater — o item perde a versão de utente e desaparece do ecrã
do doente SEM QUALQUER ERRO. Este verificador transforma essa deriva silenciosa
num sinal ruidoso:

  * ERRO (bloqueia o CI):
      - chaves ÓRFÃS — entradas nas reescritas que não correspondem a nenhum
        conselho clínico atual do aconselhamento.json (deriva de texto);
      - reescritas DESATUALIZADAS — o aconselhamento_utente.json foi editado
        mas o aplicar_aconselhamento_utente.py não voltou a correr (o SHA-256
        gravado em fonte.reescritas já não bate com o ficheiro), ou um item do
        aconselhamento.json diverge da entrada correspondente (edição à mão de
        um ficheiro gerado);
      - estado de VALIDAÇÃO incoerente — validado=true sem validado_por ou
        sem validado_em em AAAA-MM-DD (um "aprovado" sem quem nem quando não
        serve de registo).

  * AVISO (não bloqueia): sinais úteis para quem mantém os dados —
      - colisões de texto do utente (conselhos clínicos distintos que colapsam
        na mesma frase leiga; o frontend desduplica, mas convém saber);
      - gralhas conhecidas herdadas da tabela de origem ("paracematol",
        "cetrizina", "analgesicos"...), que ficam gravadas nas chaves;
      - proveniência da tabela por registar (fonte.tabela vazio até à próxima
        importação com o Excel);
      - SOBREPOSIÇÕES com o autocuidado (v0.15.2): frases do autocuidado
        (verde/azul) muito parecidas com conselhos leigos dos fluxos na mesma
        cor — os dois cartões podem aparecer no mesmo ecrã e convém a revisão
        clínica decidir se a redundância é desejada;
      - dimensão do "oculto": dos itens sem versão de utente, uma estimativa
        de quantos são mesmo só-profissionais e quantos são apenas conselhos
        leigos seguros ainda por reescrever (o backlog real).

Corre isolado (imprime um relatório e devolve != 0 se houver erros) ou é
chamado por scripts/validar_dados.py, para "passa em CI" incluir também a
integridade do aconselhamento. NÃO toca no arranque do servidor: o motor
continua a carregar o aconselhamento de forma tolerante (é um extra e nunca
deve impedir a triagem de arrancar); esta é uma rede de segurança de
desenvolvimento/CI.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _aconselhamento_utente import (
    FICHEIRO_REESCRITAS,
    REGISTO,
)
from _manchester_comum import normalizar, sha256_de

RAIZ = Path(__file__).resolve().parent.parent
FICHEIRO = RAIZ / "app" / "data" / "aconselhamento.json"
FICHEIRO_AUTOCUIDADO = RAIZ / "app" / "data" / "autocuidado.json"

# Gralhas conhecidas da tabela de origem, gravadas nas chaves porque estas têm
# de bater certo com a string clínica tal como vem no Excel. Documentadas aqui
# para não passarem por lapso; a correção de fundo é na origem (ver o guia dos
# dados) e não neste ficheiro.
GRALHAS_ORIGEM = ("paracematol", "cetrizina", "analgesicos")

# Heurística (NÃO é decisão clínica): marcadores de ações que são mesmo só do
# profissional. Serve apenas para DIMENSIONAR o backlog oculto — separar, por
# alto, o que é só-profissional do que é conselho leigo seguro ainda por
# reescrever. Qualquer reescrita/revelação real continua a exigir validação
# clínica.
MARCADORES_PROFISSIONAL = (
    "escala",
    "cincinnati",
    "glasgow",
    "quantificar",
    "avaliar",
    "ativar",
    "siv",
    "sbv",
    "sav",
    "vmer",
    "meios",
    "regulador",
    "glucagon",
    "aspirina",
    "nitro",
    "adrenalina",
    "salbutamol",
    "diazepam",
    "naloxona",
    "oxigenio",
    "isolamento",
    "isolar",
    "algaliar",
    "acesso venoso",
    "monitor",
    "amostra",
    "conservar",
    "colheita",
    "sonda",
    "puncionar",
    "policia",
    "ciav",
    "notificar",
    "medico",
    "enfermeir",
    "triagem",
)

_DATA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _sem_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def _palavras(s: str) -> set[str]:
    """Palavras "com peso" de uma frase, para a heurística de sobreposição."""
    return {p for p in re.findall(r"[a-zà-ÿ]+", _sem_acentos(s)) if len(p) >= 4}


def _carregar_textos(ficheiro: Path):
    """Lê o aconselhamento.json e devolve o material das verificações.

    Devolve (dados, textos_clinicos, utente_por_texto, textos_sem_utente,
    textos_sem_en, itens_com_utente, total_occ, com_occ):
      - dados: o JSON completo (para as verificações de fonte/validação).
      - textos_clinicos: conjunto dos 'texto' (clínicos) normalizados presentes.
      - utente_por_texto: texto_utente normalizado -> conjunto de textos clínicos
        que produzem essa mesma frase leiga (para detetar colisões).
      - textos_sem_utente: textos clínicos SEM versão de utente (o "oculto"),
        por OCORRÊNCIA (o mesmo conselho repete-se em vários fluxos/cores).
      - textos_sem_en: textos clínicos COM versão de utente mas SEM a variante
        inglesa (texto_utente_en) — sinal de aconselhamento.json desatualizado.
      - itens_com_utente: lista de (cor, texto_clinico, item) para as
        verificações de espelho/validação e de sobreposição com o autocuidado.
      - total_occ / com_occ: contagem por OCORRÊNCIA (não distinta), para a
        cobertura casar com o relatório do importador (os "61%").
    """
    dados = json.loads(ficheiro.read_text(encoding="utf-8"))
    fluxos = dados["fluxos"]
    clinicos: set[str] = set()
    por_texto: dict[str, set[str]] = {}
    sem_utente: list[str] = []
    sem_en: list[str] = []
    itens_com_utente: list[tuple[str, str, dict]] = []
    total_occ = 0
    com_occ = 0
    for _fluxo, cores in fluxos.items():
        for cor, bloco in cores.items():
            for it in bloco.get("itens", []):
                tc = normalizar(it["texto"])
                clinicos.add(tc)
                total_occ += 1
                tu = it.get("texto_utente")
                if tu:
                    com_occ += 1
                    itens_com_utente.append((cor, tc, it))
                    chave = normalizar(tu).lower()
                    por_texto.setdefault(chave, set()).add(tc)
                    # v0.15.1: cada versão de utente tem par inglês; a falta
                    # dele é o mesmo tipo de deriva silenciosa (o utente EN
                    # veria português) e conta como JSON desatualizado.
                    if not it.get("texto_utente_en"):
                        sem_en.append(tc)
                else:
                    sem_utente.append(tc)
    return (dados, clinicos, por_texto, sem_utente, sem_en, itens_com_utente, total_occ, com_occ)


def _sobreposicoes_autocuidado(
    itens_com_utente: list[tuple[str, str, dict]],
    ficheiro_autocuidado: Path,
) -> list[str]:
    """Frases do autocuidado (verde/azul) ~iguais a conselhos leigos da mesma cor.

    Os dois cartões podem aparecer no mesmo ecrã (o autocuidado no
    encaminhamento, o aconselhamento no resultado e no fim do encaminhamento);
    esta heurística lista os pares muito parecidos para a revisão clínica
    decidir se a redundância é desejada ou se um dos lados deve ceder. É um
    AVISO de propósito: a reconciliação é uma decisão clínica, não do CI.
    """
    if not ficheiro_autocuidado.exists():
        return []
    ac = json.loads(ficheiro_autocuidado.read_text(encoding="utf-8"))
    pares: list[str] = []
    # conselhos leigos distintos por cor
    leigos_por_cor: dict[str, dict[str, str]] = {}
    for cor, _tc, it in itens_com_utente:
        leigos_por_cor.setdefault(cor, {})[normalizar(it["texto_utente"])] = ""
    for cor, bloco in (ac.get("cores") or {}).items():
        frases_ac: list[str] = []
        for campo in ("fazer", "evitar", "alerta"):
            frases_ac.extend(bloco.get(campo) or [])
        for frase in frases_ac:
            pa = _palavras(frase)
            if len(pa) < 3:
                continue
            for leigo in leigos_por_cor.get(cor, {}):
                pl = _palavras(leigo)
                if len(pl) < 3:
                    continue
                comum = len(pa & pl)
                if comum / min(len(pa), len(pl)) >= 0.6:
                    pares.append(
                        f'[{cor}] autocuidado "{frase[:64]}…" ~ ' f'aconselhamento "{leigo[:64]}…"'
                    )
    return pares


def analisar(
    ficheiro: Path = FICHEIRO,
    ficheiro_reescritas: Path = FICHEIRO_REESCRITAS,
    registo: dict[str, dict] | None = None,
    ficheiro_autocuidado: Path = FICHEIRO_AUTOCUIDADO,
) -> tuple[list[str], list[str]]:
    """Corre as verificações. Devolve (erros, avisos).

    Os caminhos e o registo são parametrizáveis para os testes; por omissão
    usa os ficheiros reais do projeto.
    """
    if registo is None:
        registo = REGISTO
    if not ficheiro.exists():
        # Coerente com o resto do projeto: sem o ficheiro, é um aviso (o extra
        # não existe), não um erro que bloqueia tudo.
        return [], [f"aconselhamento.json não encontrado em {ficheiro}"]

    dados, clinicos, por_texto, _sem_utente, sem_en, itens_com_utente, _total_occ, _com_occ = (
        _carregar_textos(ficheiro)
    )
    mapa_pt = {c: i["pt"] for c, i in registo.items()}
    mapa_en = {c: i["en"] for c, i in registo.items()}
    erros: list[str] = []
    avisos: list[str] = []

    # 1) Chaves órfãs (ERRO): reescrita -> string que já não existe na tabela.
    orfas = [k for k in mapa_pt if normalizar(k) not in clinicos]
    if orfas:
        erros.append(
            f"{len(orfas)} chave(s) de aconselhamento órfã(s) (não correspondem "
            f"a nenhum conselho clínico atual — provável deriva de texto na "
            f"tabela de origem):"
        )
        for k in orfas:
            erros.append(f"    chave órfã: {k}")

    # 1b) O mesmo, para o inglês: chaves EN que já não existem na tabela são a
    #     mesma deriva silenciosa, agora na outra língua. (Com o ficheiro
    #     único da v0.15.2, PT e EN partilham a chave, por isso 1c passou a
    #     ser estrutural; mantém-se a verificação por defesa em profundidade,
    #     p. ex. para registos construídos à mão nos testes.)
    orfas_en = [k for k in mapa_en if normalizar(k) not in clinicos]
    if orfas_en and orfas_en != orfas:
        erros.append(f"{len(orfas_en)} chave(s) do mapa inglês órfã(s):")
        for k in orfas_en:
            erros.append(f"    chave órfã (EN): {k}")

    # 1c) Pares completos: cada item das reescritas tem de ter PT e EN não
    #     vazios (o carregador já o exige para o ficheiro real).
    incompletos = [c for c, i in registo.items() if not i.get("pt") or not i.get("en")]
    if incompletos:
        erros.append(f"{len(incompletos)} item(ns) das reescritas sem PT ou sem EN:")
        for k in incompletos:
            erros.append(f"    incompleto: {k}")

    # 1d) O próprio JSON tem de estar em dia: item com texto_utente sem o par
    #     texto_utente_en = aplicar/importar por correr depois de mexer nas
    #     reescritas.
    if sem_en:
        distintos_sem_en = list(dict.fromkeys(sem_en))
        erros.append(
            f"{len(distintos_sem_en)} conselho(s) no aconselhamento.json com "
            f"texto_utente mas sem texto_utente_en (voltar a correr "
            f"scripts/aplicar_aconselhamento_utente.py):"
        )
        for tc in distintos_sem_en[:10]:
            erros.append(f"    sem texto_utente_en: {tc}")

    # 1e) Sincronização com as reescritas (v0.15.2). Duas pontas:
    #     - o SHA-256 gravado em fonte.reescritas tem de bater com o ficheiro
    #       editável atual (senão: alguém editou as reescritas e não correu o
    #       aplicar — exatamente a deriva silenciosa, agora ao nível do
    #       ficheiro);
    #     - cada item do aconselhamento.json tem de espelhar a entrada do
    #       registo (senão: o ficheiro GERADO foi editado à mão).
    fonte = dados.get("fonte") or {}
    reescritas_fonte = fonte.get("reescritas") or {}
    sha_atual = sha256_de(ficheiro_reescritas) if ficheiro_reescritas.exists() else None
    if sha_atual and reescritas_fonte.get("sha256") != sha_atual:
        erros.append(
            "aconselhamento.json desatualizado: as reescritas "
            "(aconselhamento_utente.json) mudaram desde a última aplicação — "
            "correr scripts/aplicar_aconselhamento_utente.py e submeter o "
            "resultado."
        )
    else:
        espelho_errado: list[str] = []
        for _cor, tc, it in itens_com_utente:
            entrada = registo.get(tc)
            if entrada is None:
                continue  # já apanhado como incoerência via sha/órfãs
            if (
                it.get("texto_utente") != entrada.get("pt")
                or it.get("texto_utente_en") != entrada.get("en")
                or bool(it.get("validado")) != bool(entrada.get("validado"))
                or it.get("validado_por") != entrada.get("validado_por")
                or it.get("validado_em") != entrada.get("validado_em")
            ):
                espelho_errado.append(tc)
        if espelho_errado:
            distintos = list(dict.fromkeys(espelho_errado))
            erros.append(
                f"{len(distintos)} item(ns) do aconselhamento.json divergem das "
                f"reescritas (ficheiro gerado editado à mão? — correr "
                f"scripts/aplicar_aconselhamento_utente.py):"
            )
            for tc in distintos[:10]:
                erros.append(f"    diverge: {tc}")

    # 1f) Itens com texto_utente têm de trazer o estado de validação
    #     (estrutura da v0.15.2; a falta indica um JSON antigo).
    sem_estado = [tc for _cor, tc, it in itens_com_utente if "validado" not in it]
    if sem_estado:
        distintos = list(dict.fromkeys(sem_estado))
        erros.append(
            f"{len(distintos)} item(ns) com texto_utente sem estado de "
            f"validação (estrutura anterior à v0.15.2 — correr "
            f"scripts/aplicar_aconselhamento_utente.py):"
        )
        for tc in distintos[:10]:
            erros.append(f"    sem estado: {tc}")

    # 1g) Estado de validação coerente: validado=true exige quem e quando
    #     (AAAA-MM-DD). Um "aprovado" sem registo não serve de registo.
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
        for k in mal_validados:
            erros.append(f"    validação incompleta: {k}")

    # 2) Colisões de texto do utente (AVISO): o frontend desduplica, mas é bom
    #    saber que conselhos clínicos distintos colapsam na mesma frase leiga.
    colisoes = {k: v for k, v in por_texto.items() if len(v) > 1}
    if colisoes:
        avisos.append(
            f"{len(colisoes)} frase(s) de utente vinda(s) de >1 conselho clínico "
            f"(desduplicadas no ecrã; rever se a fusão é a desejada)."
        )

    # 3) Gralhas de origem gravadas nas chaves (AVISO).
    chaves_baixa = [k.lower() for k in mapa_pt]
    presentes = [g for g in GRALHAS_ORIGEM if any(g in k for k in chaves_baixa)]
    if presentes:
        avisos.append(
            "gralhas herdadas da tabela de origem presentes nas chaves "
            f"({', '.join(presentes)}); a corrigir na origem, não aqui."
        )

    # 4) Proveniência da tabela (AVISO até à próxima importação com o Excel).
    if not fonte.get("tabela"):
        avisos.append(
            "fonte.tabela por registar no aconselhamento.json: não se sabe de "
            "que versão do Excel os conselhos vieram. Fica registado "
            "automaticamente na próxima corrida de "
            "scripts/importar_aconselhamento.py <tabela.xls>."
        )

    # 5) Sobreposições com o autocuidado (AVISO, v0.15.2).
    pares = _sobreposicoes_autocuidado(itens_com_utente, ficheiro_autocuidado)
    if pares:
        avisos.append(
            f"{len(pares)} sobreposição(ões) autocuidado × aconselhamento na "
            f"mesma cor (os dois cartões podem aparecer no mesmo ecrã; a "
            f"revisão clínica decide se a redundância é desejada):"
        )
        for p in pares[:8]:
            avisos.append(f"    {p}")

    return erros, avisos


def _relatorio_stdout() -> int:
    """Modo isolado: imprime o relatório completo e devolve o código de saída."""
    if not FICHEIRO.exists():
        print(f"aconselhamento.json não encontrado ({FICHEIRO}); nada a verificar.")
        return 0

    dados, _clinicos, _por_texto, sem_utente, sem_en, itens_com_utente, total_occ, com_occ = (
        _carregar_textos(FICHEIRO)
    )
    pct = round(100 * com_occ / total_occ) if total_occ else 0
    validados = sum(1 for _c, _t, it in itens_com_utente if it.get("validado"))

    print("Verificação do aconselhamento ao utente")
    print("=" * 44)
    print(f"Chaves nas reescritas (aconselhamento_utente.json): {len(REGISTO)}")
    print(f"Itens (fluxo,cor) no aconselhamento.json:           {total_occ}")
    print(f"  com texto_utente (mostrados ao utente): {com_occ} ({pct}%)")
    print(f"    dos quais com tradução EN:            {com_occ - len(sem_en)}")
    print(f"    dos quais validados clinicamente:     {validados}")
    print(f"  sem texto_utente (só no backend):        {total_occ - com_occ}")
    tabela = (dados.get("fonte") or {}).get("tabela")
    if tabela:
        print(
            f"Tabela de origem: {tabela.get('ficheiro')} "
            f"(sha256 {str(tabela.get('sha256'))[:12]}…, "
            f"{tabela.get('linhas')} linhas, importada em "
            f"{tabela.get('importado_em')})"
        )

    erros, avisos = analisar()

    # Dimensão do oculto (heurística): só-profissional vs. por-reescrever.
    distintos = list(dict.fromkeys(sem_utente))
    so_prof = []
    por_fazer = []
    for tc in distintos:
        base = _sem_acentos(tc)
        if any(m in base for m in MARCADORES_PROFISSIONAL):
            so_prof.append(tc)
        else:
            por_fazer.append(tc)
    print(
        f"\nOculto (heurística, {len(distintos)} distintos): "
        f"~{len(so_prof)} provavelmente só-profissional, "
        f"~{len(por_fazer)} provavelmente conselho leigo por reescrever."
    )
    print("  (Estimativa para dimensionar o backlog; NÃO é decisão clínica.")
    print("   Revelar conselhos leigos exige validação clínica.)")
    if por_fazer:
        freq = Counter(sem_utente)
        print("\n  Candidatos a reescrita (backlog), pelos mais frequentes:")
        for tc in sorted(por_fazer, key=lambda x: -freq[x])[:12]:
            print(f"    {freq[tc]:>3}x  {tc[:84]}")

    if avisos:
        print("\nAvisos (não bloqueiam):")
        for a in avisos:
            print(f"  {a}" if a.startswith("    ") else f"  AVISO: {a}")

    if erros:
        print("\nERROS (deriva silenciosa a corrigir):")
        for e in erros:
            print(f"  {e}" if e.startswith("    ") else f"  ERRO: {e}")
        return 1

    print("\nTudo certo: reescritas e aconselhamento.json em sincronia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_relatorio_stdout())
