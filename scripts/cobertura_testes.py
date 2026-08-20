#!/usr/bin/env python3
"""Cobertura de testes: medir e (opcionalmente) atualizar os badges (v0.13.0).

Correr, a partir da pasta do projeto:

    python scripts/cobertura_testes.py                      # só medir
    python scripts/cobertura_testes.py --atualizar-readme   # medir e
                                        # atualizar os badges nos READMEs
    python scripts/cobertura_testes.py --html               # relatório
                                        # navegável em htmlcov/index.html

O que faz:
  1. Corre a suite completa com medição de cobertura
     (python -m pytest --cov=app).
  2. Mostra o total por módulo e o resumo (N testes, X%).
  3. Com --atualizar-readme, reescreve os badges "tests" e "coverage"
     no README.md e no README.pt.md com os números reais. Assim os
     badges nunca ficam a mentir por esquecimento: fazem parte do ritual
     de fechar uma versão, tal como o validar_dados.py.

Notas:
  - Precisa do pacote pytest-cov (está no requirements.txt).
  - O relatório HTML (htmlcov/) e o ficheiro .coverage são artefactos
    locais: estão no .gitignore e no .dockerignore, não se enviam.
  - O script não altera mais nada nos READMEs além dos dois badges.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
READMES = [RAIZ / "README.md", RAIZ / "README.pt.md"]

PADRAO_TOTAL = re.compile(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", re.MULTILINE)
PADRAO_PASSARAM = re.compile(r"(\d+) passed")
PADRAO_BADGE_TESTES = re.compile(r"tests-\d+%20passed-[a-z]+")
PADRAO_BADGE_COBERTURA = re.compile(r"coverage-\d+%25-[a-z]+")


def cor_do_badge(percentagem: int) -> str:
    """Verde a partir de 90%, amarelo a partir de 75%, laranja abaixo."""
    if percentagem >= 90:
        return "brightgreen"
    if percentagem >= 75:
        return "yellow"
    return "orange"


def medir(com_html: bool) -> tuple[int, int]:
    """Corre o pytest com cobertura; devolve (n_testes, percentagem)."""
    comando = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--cov=app",
        "--cov-report=term",
    ]
    if com_html:
        comando.append("--cov-report=html")
    resultado = subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True)
    print(resultado.stdout)
    if resultado.returncode != 0:
        print(resultado.stderr)
        sys.exit("Há testes a falhar — corrigir antes de medir a cobertura.")

    total = PADRAO_TOTAL.search(resultado.stdout)
    passaram = PADRAO_PASSARAM.search(resultado.stdout)
    if not total or not passaram:
        sys.exit(
            "Não consegui ler o resumo do pytest-cov. "
            "O pytest-cov está instalado? (pip install -r requirements.txt)"
        )
    return int(passaram.group(1)), int(total.group(1))


def atualizar_badges(n_testes: int, percentagem: int) -> None:
    cor = cor_do_badge(percentagem)
    novo_testes = f"tests-{n_testes}%20passed-brightgreen"
    novo_cobertura = f"coverage-{percentagem}%25-{cor}"
    for readme in READMES:
        texto = readme.read_text(encoding="utf-8")
        novo, n1 = PADRAO_BADGE_TESTES.subn(novo_testes, texto)
        novo, n2 = PADRAO_BADGE_COBERTURA.subn(novo_cobertura, novo)
        if n1 == 0 or n2 == 0:
            print(
                f"  AVISO: badges não encontrados em {readme.name} "
                "(nada alterado nesse ficheiro)."
            )
            continue
        readme.write_text(novo, encoding="utf-8")
        print(f"  {readme.name}: badges atualizados " f"({n_testes} testes, {percentagem}%).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Mede a cobertura de testes e atualiza os badges.")
    parser.add_argument(
        "--atualizar-readme",
        action="store_true",
        help="reescrever os badges nos dois READMEs com os números medidos",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="gerar também o relatório navegável em htmlcov/index.html",
    )
    argumentos = parser.parse_args()

    n_testes, percentagem = medir(com_html=argumentos.html)
    print(f"Resumo: {n_testes} testes a passar, {percentagem}% de cobertura.")
    if argumentos.html:
        print("Relatório detalhado: htmlcov/index.html")
    if argumentos.atualizar_readme:
        atualizar_badges(n_testes, percentagem)
    else:
        print(
            "(para atualizar os badges dos READMEs: "
            "python scripts/cobertura_testes.py --atualizar-readme)"
        )


if __name__ == "__main__":
    main()
