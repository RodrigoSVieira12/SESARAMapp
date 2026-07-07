"""Fluxogramas Mermaid gerados a partir dos ficheiros de regras.

O protocolo de Manchester é publicado como FLUXOGRAMAS — este módulo
devolve os fluxos do projeto nesse formato nativo dos clínicos, para:

  1. o documento de validação clínica (scripts/gerar_validacao_clinica.py),
     onde cada queixa passa a incluir a árvore desenhada;
  2. os ficheiros docs/fluxogramas/*.mmd, que podem ser abertos e editados
     visualmente em https://mermaid.live.

Sem dependências no servidor: aqui gera-se apenas o TEXTO Mermaid; o
desenho acontece no navegador (biblioteca mermaid, via CDN) ao abrir o
documento. Os desfechos usam as cinco cores de Manchester do projeto.
"""

from __future__ import annotations

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


def mermaid_do_fluxo(fluxo: dict) -> str:
    """Texto Mermaid (flowchart TD) de um fluxo de triagem completo.

    As perguntas são numeradas com os mesmos números das listas do
    documento de validação, para o clínico cruzar as duas vistas.
    """
    linhas = [
        "flowchart TD",
        f'  inicio(["Início: {_quebrar(fluxo["nome"], 26)}"])',
    ]

    numeros = {p["id"]: i + 1 for i, p in enumerate(fluxo["perguntas"])}
    for p in fluxo["perguntas"]:
        linhas.append(f'  {p["id"]}["{numeros[p["id"]]}. {_quebrar(p["texto"])}"]')

    linhas.append(f'  inicio --> {fluxo["perguntas"][0]["id"]}')

    cores_usadas: set[str] = set()
    for p in fluxo["perguntas"]:
        for resposta, rotulo in (("sim", "Sim"), ("nao", "Não")):
            ramo = p[resposta]
            if "proxima" in ramo:
                linhas.append(f'  {p["id"]} -->|{rotulo}| {ramo["proxima"]}')
            else:
                r = ramo["resultado"]
                cor = r.get("cor", "desconhecida")
                cores_usadas.add(cor)
                no_id = f'{p["id"]}_{resposta}'
                texto = cor.upper()
                if r.get("motivo"):
                    texto += f"<br/>{_quebrar(r['motivo'])}"
                linhas.append(f'  {no_id}(["{texto}"]):::{cor}')
                linhas.append(f'  {p["id"]} -->|{rotulo}| {no_id}')

    for cor in sorted(cores_usadas):
        fundo, letra = _ESTILOS_COR.get(cor, ("#666666", "#ffffff"))
        linhas.append(f"  classDef {cor} fill:{fundo},color:{letra},stroke:#333;")

    return "\n".join(linhas)


def gerar_todos(fluxos: dict[str, dict]) -> dict[str, str]:
    """{id_do_fluxo: texto mermaid} para todos os fluxos carregados."""
    return {fid: mermaid_do_fluxo(f) for fid, f in fluxos.items()}
