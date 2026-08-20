# -*- coding: utf-8 -*-
"""Aplica as perguntas leigas às regras — a partir do JSON editável (v0.15.3).

O ciclo de edição da equipa clínica é o mesmo do aconselhamento:

    1. editar app/data/perguntas_utente.json (frases PT/EN por discriminador);
    2. correr:  python scripts/aplicar_perguntas_utente.py
    3. rever o diff e submeter (o CI volta a verificar tudo).

Para cada discriminador em app/data/rules/*.json, refaz APENAS a camada do
utente (``texto_utente`` e ``texto_utente_en``) a partir do registo,
emparelhando pelo texto clínico exato (campo ``texto``, com os espaços
colapsados — a mesma normalização do resto do projeto). Os campos clínicos
(``texto``, ``texto_en``, ``descricao``, prioridade, cor…) ficam INTOCADOS:
são eles que alimentam a lógica de triagem, os fluxogramas e o documento de
validação clínica.

O ESTADO DE VALIDAÇÃO (`validado`/`validado_por`/`validado_em`) NÃO é
copiado para as regras, de propósito — e isto é diferente do
aconselhamento. O `aconselhamento.json` é um ficheiro GERADO ("não editar à
mão"), por isso embutir lá o estado era de borla; as regras são o ficheiro
que a equipa clínica edita à mão, e copiar para lá campos gerados encheria
os 55 ficheiros de ruído e cada validação tocaria em dois sítios. O estado
vive SÓ em perguntas_utente.json (uma única fonte): o motor lê-o no
arranque (portão ONDE_IR_APENAS_VALIDADO) e a página /revisao junta as duas
pontas a cada refresh. Consequência prática: marcar um item como validado
NÃO precisa de correr este script — só a mudança de frases precisa.

Cobertura total ou erro: hoje todos os 1187 discriminadores têm reescrita;
um discriminador sem entrada no registo é uma REGRESSÃO de legibilidade
(o utente passaria a ver o texto clínico) e sai daqui com código != 0,
para o CI apanhar. Nesse caso a camada do utente do discriminador é
removida (o recuo do motor para o texto clínico é seguro), mas a lista do
que falta fica impressa com a instrução do que acrescentar.

Nota sobre o importador: `importar_manchester.py` (que precisa do Excel)
usa o MESMO registo ao regenerar as regras; correr este script a seguir a
uma importação normaliza a camada do utente e confirma a cobertura.

Escreve com indent=2, ensure_ascii=False e uma linha em branco final,
exatamente como os ficheiros originais, e só toca nos ficheiros que mudam.
É seguro correr várias vezes (idempotente byte a byte).

Uso:
    python scripts/aplicar_perguntas_utente.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _manchester_comum import normalizar  # noqa: E402
from _perguntas_utente import carregar_perguntas  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PASTA_REGRAS = RAIZ / "app" / "data" / "rules"

# Ordem preferida das chaves conhecidas (a mesma desde a v0.14.1, para o
# JSON ficar legível a quem revê, com o clínico e o do utente lado a lado,
# por idioma); chaves extra mantêm-se no fim pela ordem em que já estavam.
ORDEM = [
    "id",
    "disc_id",
    "prioridade",
    "cor",
    "texto",
    "texto_utente",
    "texto_en",
    "texto_utente_en",
    "descricao",
]

# Campos da camada do utente nas regras: são estes (e só estes) que este
# script gere.
_CAMPOS_UTENTE = ("texto_utente", "texto_utente_en")


def _reordenar(disc: dict) -> dict:
    novo: dict = {}
    for chave in ORDEM:
        if chave in disc:
            novo[chave] = disc[chave]
    for chave, valor in disc.items():
        if chave not in novo:
            novo[chave] = valor
    return novo


def aplicar_a_fluxo(dados: dict, registo_norm: dict[str, dict]) -> dict:
    """Refaz a camada do utente de UM fluxo a partir do registo.

    Muta e devolve `dados`; pendura as estatísticas em "_relatorio" (o
    chamador remove antes de gravar). `registo_norm` tem as chaves já
    normalizadas. É a única lógica de fusão — usada aqui e nos testes.
    """
    aplicados = 0
    sem_entrada: list[str] = []
    usadas: set[str] = set()

    novas = []
    for disc in dados.get("perguntas", []):
        chave = normalizar(disc.get("texto"))
        entrada = registo_norm.get(chave)
        for campo in _CAMPOS_UTENTE:
            disc.pop(campo, None)
        if entrada is not None:
            usadas.add(chave)
            disc["texto_utente"] = entrada["pt"]
            disc["texto_utente_en"] = entrada["en"]
            aplicados += 1
        else:
            sem_entrada.append(chave)
        novas.append(_reordenar(disc))
    dados["perguntas"] = novas
    dados["_relatorio"] = {
        "aplicados": aplicados,
        "sem_entrada": sem_entrada,
        "usadas": usadas,
    }
    return dados


def main() -> int:
    registo = carregar_perguntas()["itens"]
    registo_norm = {normalizar(c): i for c, i in registo.items()}

    ficheiros = sorted(PASTA_REGRAS.glob("*.json"))
    total_disc = 0
    total_aplicados = 0
    sem_entrada: list[str] = []
    usadas: set[str] = set()
    alterados: list[str] = []

    for caminho in ficheiros:
        original = caminho.read_text(encoding="utf-8")
        dados = json.loads(original)
        if dados.get("id") == "red_flags":
            continue  # não tem discriminadores (tem "sinais")

        aplicar_a_fluxo(dados, registo_norm)
        rel = dados.pop("_relatorio")
        total_disc += rel["aplicados"] + len(rel["sem_entrada"])
        total_aplicados += rel["aplicados"]
        sem_entrada.extend(f"{dados['id']}: {c!r}" for c in rel["sem_entrada"])
        usadas |= rel["usadas"]

        saida = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
        if saida != original:
            caminho.write_text(saida, encoding="utf-8")
            alterados.append(caminho.name)

    print(f"Ficheiros processados : {len(ficheiros)}")
    print(f"Discriminadores       : {total_disc}")
    print(f"Com texto_utente      : {total_aplicados}")

    orfas = [c for c in registo_norm if c not in usadas]
    if orfas:
        # Aviso aqui; o verificador marca-o como ERRO no CI, tal como faz
        # com as chaves órfãs do aconselhamento.
        print(
            f"AVISO: {len(orfas)} chave(s) das reescritas sem correspondência "
            f"em nenhum discriminador (órfãs — o verificador marca isto "
            f"como ERRO):"
        )
        for c in orfas:
            print(f"    - {c[:88]}")

    if alterados:
        print(f"Atualizado(s) {len(alterados)} ficheiro(s): " + ", ".join(alterados))
    else:
        print("Sem alterações.")

    if sem_entrada:
        print(
            f"ERRO: {len(sem_entrada)} discriminador(es) SEM entrada nas "
            f"reescritas (o utente veria o texto clínico — acrescentar a "
            f"app/data/perguntas_utente.json e voltar a correr):"
        )
        for linha in sem_entrada:
            print("   -", linha)
        return 1
    print("Todos os discriminadores ficaram com texto para o utente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
