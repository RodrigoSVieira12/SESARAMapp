# -*- coding: utf-8 -*-
"""Auditoria estática de acessibilidade (v0.15.2).

O público-alvo desta aplicação é quem mais depende de acessibilidade — utentes
idosos, com baixa visão (cataratas, sensibilidade ao contraste reduzida) ou
pouca literacia digital — e, até aqui, nada verificava o contraste nem os
básicos da página. Este script fixa o que é verificável SEM browser:

  1. CONTRASTE (WCAG 2.1). Lê as variáveis de cor de static/css/style.css e
     verifica os pares realmente usados na interface:
       - texto normal: rácio >= 4.5:1 (critério 1.4.3, nível AA);
       - componentes de interface (contornos de cartões, campos e botões):
         rácio >= 3:1 (critério 1.4.11, contraste não textual).
     Foi exatamente aqui que a análise da v0.15.1 encontrou o problema real
     (filetes a 1,4:1, invisíveis para quem tem sensibilidade ao contraste
     reduzida); com a remoção do botão de alto contraste, o TEMA BASE passou
     a ter de cumprir por si (v0.15.2) — e este auditor impede a regressão.

  2. PÁGINA (index.html e revisao.html): atributo lang, viewport que NÃO
     bloqueia o zoom (sem user-scalable=no nem maximum-scale<2 — o zoom do
     browser é a ferramenta de ampliação do utente, ver a discussão que levou
     à remoção do botão A+), botões estáticos com nome acessível, região
     viva (aria-live) no index.

  3. CSS/JS: existe estilo :focus-visible (o anel de foco para navegação por
     teclado), os alvos de toque principais (.botao, .queixa) declaram
     min-height >= 48px, e não há tabindex positivo (que baralha a ordem de
     tabulação).

O que fica DE FORA, de propósito (precisa de browser/pessoas): leitor de ecrã
real, ordem de foco dinâmica, regressão visual. Está anotado como trabalho
futuro no CHANGELOG.

Corre isolado (relatório + código de saída) e no CI, a seguir aos testes:

    python scripts/auditar_acessibilidade.py
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CSS = RAIZ / "static" / "css" / "style.css"
INDEX = RAIZ / "static" / "index.html"
REVISAO = RAIZ / "static" / "revisao.html"
JS = (RAIZ / "static" / "js" / "app.js", RAIZ / "static" / "js" / "nucleo.js")

MINIMO_TEXTO = 4.5  # WCAG 1.4.3 (AA, texto normal)
MINIMO_COMPONENTE = 3.0  # WCAG 1.4.11 (contraste não textual)
MINIMO_ALVO_PX = 48  # alvo de toque confortável (44 é o mínimo absoluto)


# ------------------------------------------------------------- contraste --


def _luminancia(cor_hex: str) -> float:
    cor_hex = cor_hex.lstrip("#")
    if len(cor_hex) == 3:
        cor_hex = "".join(c * 2 for c in cor_hex)
    r, g, b = (int(cor_hex[i : i + 2], 16) / 255 for i in (0, 2, 4))

    def canal(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = canal(r), canal(g), canal(b)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def racio_contraste(a: str, b: str) -> float:
    """Rácio de contraste WCAG entre duas cores hex (1.0 a 21.0)."""
    la, lb = _luminancia(a), _luminancia(b)
    alto, baixo = max(la, lb), min(la, lb)
    return (alto + 0.05) / (baixo + 0.05)


def variaveis_do_css(texto_css: str) -> dict[str, str]:
    """Variáveis --nome: #hex do primeiro bloco :root."""
    m = re.search(r":root\s*\{(.*?)\}", texto_css, re.S)
    if not m:
        return {}
    return dict(re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", m.group(1)))


# ----------------------------------------------------------- verificações --


def _verificar_contrastes(css: str) -> list[tuple[bool, str]]:
    v = variaveis_do_css(css)
    resultados: list[tuple[bool, str]] = []

    def par(nome: str, cor_a: str, cor_b: str, minimo: float) -> None:
        r = racio_contraste(cor_a, cor_b)
        ok = r >= minimo
        resultados.append((ok, f"{nome}: {r:.2f}:1 (mínimo {minimo}:1)"))

    # Texto (1.4.3): os pares em uso na interface.
    par(
        "texto principal sobre cartão (tinta/superficie)", v["tinta"], v["superficie"], MINIMO_TEXTO
    )
    par("texto principal sobre página (tinta/fundo)", v["tinta"], v["fundo"], MINIMO_TEXTO)
    par(
        "texto secundário (tinta-suave/superficie)", v["tinta-suave"], v["superficie"], MINIMO_TEXTO
    )
    par(
        "ligações e botões-fantasma (primaria/superficie)",
        v["primaria"],
        v["superficie"],
        MINIMO_TEXTO,
    )
    par("texto dos botões (branco/primaria)", "#ffffff", v["primaria"], MINIMO_TEXTO)
    par("banda do topo (branco/primaria-escura)", "#ffffff", v["primaria-escura"], MINIMO_TEXTO)
    par("botão 112 (branco/vermelho)", "#ffffff", v["vermelho"], MINIMO_TEXTO)
    # Rótulos escurecidos da pulseira (hardcoded no CSS de propósito):
    for cor_texto in re.findall(r"--cor-texto:\s*(#[0-9a-fA-F]{3,6})", css):
        par(
            f"rótulo da pulseira ({cor_texto}/superficie)", cor_texto, v["superficie"], MINIMO_TEXTO
        )

    # Componentes (1.4.11): contornos de cartões, campos e botões.
    par(
        "contornos de cartões e listas (linha/superficie)",
        v["linha"],
        v["superficie"],
        MINIMO_COMPONENTE,
    )
    par("contornos sobre a página (linha/fundo)", v["linha"], v["fundo"], MINIMO_COMPONENTE)
    par(
        "contornos fortes: campos de texto (linha-forte/superficie)",
        v["linha-forte"],
        v["superficie"],
        MINIMO_COMPONENTE,
    )
    par("anel de foco (primaria/superficie)", v["primaria"], v["superficie"], MINIMO_COMPONENTE)
    # linha-forte também é usada como COR DE TEXTO (botão apagar do histórico),
    # por isso tem de cumprir o mínimo de texto, não só o de componente.
    par("texto em linha-forte (apagar histórico)", v["linha-forte"], v["superficie"], MINIMO_TEXTO)

    return resultados


def _verificar_pagina(caminho: Path, exigir_aria_live: bool) -> list[tuple[bool, str]]:
    html = caminho.read_text(encoding="utf-8")
    nome = caminho.name
    resultados: list[tuple[bool, str]] = []

    resultados.append(
        (bool(re.search(r"<html[^>]+lang=", html)), f"{nome}: <html> declara a língua (lang=)")
    )

    viewport = re.search(r'name="viewport"\s+content="([^"]*)"', html)
    conteudo = viewport.group(1) if viewport else ""
    bloqueia = "user-scalable=no" in conteudo or any(
        float(m) < 2 for m in re.findall(r"maximum-scale=([\d.]+)", conteudo)
    )
    resultados.append(
        (bool(viewport) and not bloqueia, f"{nome}: o viewport não bloqueia o zoom do utente")
    )

    # Botões escritos no HTML estático precisam de nome acessível (texto ou
    # aria-label). Os botões criados pelo app.js levam sempre texto/aria-label
    # (não verificável estaticamente aqui).
    sem_nome = [
        b
        for b in re.findall(r"<button\b[^>]*>.*?</button>", html, re.S)
        if "aria-label=" not in b and not re.sub(r"<[^>]+>", "", b).strip()
    ]
    resultados.append((not sem_nome, f"{nome}: botões estáticos com nome acessível"))

    if exigir_aria_live:
        resultados.append(
            ("aria-live" in html, f"{nome}: região viva (aria-live) para os ecrãs renderizados")
        )
    return resultados


def _verificar_css_e_js(css: str) -> list[tuple[bool, str]]:
    resultados: list[tuple[bool, str]] = []
    resultados.append((":focus-visible" in css, "style.css: anel de foco :focus-visible definido"))
    for seletor in (".botao", ".queixa"):
        m = re.search(re.escape(seletor) + r"\s*\{[^}]*min-height:\s*(\d+)px", css)
        px = int(m.group(1)) if m else 0
        resultados.append(
            (
                px >= MINIMO_ALVO_PX,
                f"style.css: alvo de toque {seletor} com min-height "
                f"{px or '?'}px (mínimo {MINIMO_ALVO_PX}px)",
            )
        )
    for caminho in JS:
        js = caminho.read_text(encoding="utf-8")
        positivo = re.search(r'tabindex="[1-9]', js)
        resultados.append((positivo is None, f"{caminho.name}: sem tabindex positivo"))
    return resultados


def auditar() -> tuple[list[tuple[bool, str]], int]:
    css = CSS.read_text(encoding="utf-8")
    resultados: list[tuple[bool, str]] = []
    resultados += _verificar_contrastes(css)
    resultados += _verificar_pagina(INDEX, exigir_aria_live=True)
    if REVISAO.exists():
        resultados += _verificar_pagina(REVISAO, exigir_aria_live=False)
    resultados += _verificar_css_e_js(css)
    falhas = sum(1 for ok, _ in resultados if not ok)
    return resultados, falhas


def main() -> int:
    resultados, falhas = auditar()
    print("Auditoria estática de acessibilidade")
    print("=" * 44)
    for ok, msg in resultados:
        print(f"  {'OK   ' if ok else 'FALHA'} {msg}")
    print()
    if falhas:
        print(
            f"{falhas} verificação(ões) falhada(s). Contraste e básicos da "
            f"página têm de cumprir antes de entrar (o CI bloqueia aqui)."
        )
        return 1
    print(f"Tudo certo: {len(resultados)} verificações passadas.")
    print(
        "(Fora do alcance estático: leitor de ecrã, ordem de foco dinâmica "
        "e regressão visual — ver CHANGELOG v0.15.2.)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
