"""Fluxogramas Mermaid gerados a partir dos ficheiros de regras.

No modelo por discriminadores (v0.14.0), cada fluxo é uma sequência de
discriminadores ordenados por prioridade (P1->P5). O desenho reflete
exatamente a lógica do motor: para cada discriminador, "Sim" leva ao
desfecho da sua cor e "Não" segue para o discriminador seguinte; se todos
forem "Não", o desfecho é azul ("sem discriminador positivo").

Serve para:
  1. o documento de validação clínica (scripts/gerar_validacao_clinica.py),
     onde cada queixa inclui a sequência desenhada;
  2. a pré-visualização viva em /fluxogramas (GET /api/fluxogramas), que
     relê as regras do disco a cada pedido — edita-se o JSON, guarda-se,
     e o fluxograma aparece redesenhado no navegador;
  3. os ficheiros docs/fluxogramas/*.mmd, abríveis em https://mermaid.live.

Sem dependências no servidor: aqui gera-se apenas o TEXTO Mermaid; o
desenho acontece no navegador com a biblioteca EMBUTIDA no projeto
(static/vendor/mermaid.min.js). Os desfechos usam as cinco cores de
Manchester do projeto.

Idiomas: por defeito gera-se em português. Com idioma="en" usam-se os
campos *_en das regras (com recuo seguro para PT onde faltarem), os
rótulos Sim/Não passam a Yes/No e os desfechos ao nome inglês da cor.
"""

from __future__ import annotations

from .cores import CORES

# Cores dos desfechos = as 5 cores do projeto (ver app/core/cores.py).
# (fundo, cor da letra) — letra escura só no amarelo, por contraste.
_ESTILOS_COR = {
    "vermelho": ("#D32F2F", "#ffffff"),
    "laranja": ("#EF6C00", "#ffffff"),
    "amarelo": ("#F9A825", "#1c1c1c"),
    "verde": ("#2E7D32", "#ffffff"),
    "azul": ("#1565C0", "#ffffff"),
}

_LARGURA = 34  # caracteres por linha dentro de cada caixa

# Rótulos fixos do desenho por idioma (os textos clínicos vêm das regras).
_ROTULOS = {
    "pt": {
        "inicio": "Início",
        "sim": "Sim",
        "nao": "Não",
        # Marca dos amarelos com "destino": "atendimento_urgente" (v0.12.1):
        # visível no fluxograma para a validação clínica apanhar a exceção.
        "atendimento": "pode ir ao atendimento urgente",
        "sem_positivo": "Sem discriminador positivo",
    },
    "en": {
        "inicio": "Start",
        "sim": "Yes",
        "nao": "No",
        "atendimento": "may go to urgent care",
        "sem_positivo": "No positive discriminator",
    },
}


def _escapar(texto: str) -> str:
    """Aspas dentro de rótulos Mermaid têm de virar #quot;."""
    return str(texto).replace('"', "#quot;")


def _quebrar(texto: str, largura: int = _LARGURA) -> str:
    """Parte o texto em linhas (<br/>) para as caixas não ficarem quilométricas."""
    palavras = _escapar(texto).split()
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        candidata = f"{atual} {palavra}".strip()
        if len(candidata) > largura and atual:
            linhas.append(atual)
            atual = palavra
        else:
            atual = candidata
    if atual:
        linhas.append(atual)
    return "<br/>".join(linhas)


# Espelha a regra do motor (app/core/triage_engine.py): o desfecho "sem
# discriminador positivo" fica um nível abaixo do discriminador menos
# urgente do fluxo, sem passar de P5/azul. Mantido aqui para o desenho e o
# motor mostrarem o mesmo desfecho.
_ORDEM_PRIORIDADE = ("P1", "P2", "P3", "P4", "P5")
_COR_DA_PRIORIDADE = {
    "P1": "vermelho",
    "P2": "laranja",
    "P3": "amarelo",
    "P4": "verde",
    "P5": "azul",
}


def _cor_sem_positivo(perguntas: list[dict]) -> str:
    """Cor do desfecho quando todos os discriminadores dão 'não'."""
    idx = max(_ORDEM_PRIORIDADE.index(p["prioridade"]) for p in perguntas)
    idx = min(idx + 1, len(_ORDEM_PRIORIDADE) - 1)
    return _COR_DA_PRIORIDADE[_ORDEM_PRIORIDADE[idx]]


def _t(obj: dict, campo: str, idioma: str) -> str:
    """Valor do campo no idioma pedido; sem tradução, recua para o PT."""
    if idioma == "en":
        valor = obj.get(f"{campo}_en")
        if valor:
            return str(valor)
    return str(obj.get(campo, ""))


def _nome_da_cor(cor: str, idioma: str) -> str:
    """Nome do desfecho em maiúsculas (VERMELHO… / RED…), com recuo."""
    if idioma == "en":
        info = CORES.get(cor)
        if info and info.get("nome_en"):
            return str(info["nome_en"]).upper()
    return cor.upper()


def mermaid_do_fluxo(fluxo: dict, idioma: str = "pt") -> str:
    """Texto Mermaid (flowchart TD) de um fluxo de discriminadores.

    Os discriminadores são numerados com os mesmos números das listas do
    documento de validação, para o clínico cruzar as duas vistas.
    """
    rot = _ROTULOS.get(idioma, _ROTULOS["pt"])
    perguntas = fluxo["perguntas"]
    linhas = [
        "flowchart TD",
        f'  inicio(["{rot["inicio"]}: {_quebrar(_t(fluxo, "nome", idioma), 26)}"])',
    ]

    numeros = {p["id"]: i + 1 for i, p in enumerate(perguntas)}
    for p in perguntas:
        rotulo = _quebrar(f'[{p["prioridade"]}] {_t(p, "texto", idioma)}')
        linhas.append(f'  {p["id"]}["{numeros[p["id"]]}. {rotulo}"]')

    linhas.append(f'  inicio --> {perguntas[0]["id"]}')

    cores_usadas: set[str] = set()
    for indice, p in enumerate(perguntas):
        cor = p["cor"]
        cores_usadas.add(cor)
        # Ramo "Sim" -> desfecho da cor do discriminador.
        no_sim = f'{p["id"]}_sim'
        texto = _nome_da_cor(cor, idioma)
        if p.get("destino") == "atendimento_urgente":
            texto += f"<br/>({rot['atendimento']})"
        linhas.append(f'  {no_sim}(["{texto}"]):::{cor}')
        linhas.append(f'  {p["id"]} -->|{rot["sim"]}| {no_sim}')
        # Ramo "Não" -> discriminador seguinte, ou desfecho final se for o
        # último (cor calculada como no motor: um nível abaixo do menos
        # urgente, sem passar de azul).
        if indice + 1 < len(perguntas):
            linhas.append(f'  {p["id"]} -->|{rot["nao"]}| {perguntas[indice + 1]["id"]}')
        else:
            cor_sp = _cor_sem_positivo(perguntas)
            cores_usadas.add(cor_sp)
            texto_sp = f'{_nome_da_cor(cor_sp, idioma)}<br/>{_quebrar(rot["sem_positivo"])}'
            linhas.append(f'  sem_positivo(["{texto_sp}"]):::{cor_sp}')
            linhas.append(f'  {p["id"]} -->|{rot["nao"]}| sem_positivo')

    for cor in sorted(cores_usadas):
        fundo, letra = _ESTILOS_COR.get(cor, ("#666666", "#ffffff"))
        linhas.append(f"  classDef {cor} fill:{fundo},color:{letra},stroke:#333;")

    return "\n".join(linhas)


def gerar_todos(fluxos: dict[str, dict], idioma: str = "pt") -> dict[str, str]:
    """{id_do_fluxo: texto mermaid} para todos os fluxos carregados."""
    return {fid: mermaid_do_fluxo(f, idioma) for fid, f in fluxos.items()}
