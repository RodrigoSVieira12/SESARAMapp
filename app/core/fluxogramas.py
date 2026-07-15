"""Fluxogramas Mermaid gerados a partir dos ficheiros de regras.

O protocolo de Manchester é publicado como FLUXOGRAMAS — este módulo
devolve os fluxos do projeto nesse formato nativo dos clínicos, para:

  1. o documento de validação clínica (scripts/gerar_validacao_clinica.py),
     onde cada queixa inclui a árvore desenhada;
  2. a pré-visualização viva em /fluxogramas (GET /api/fluxogramas), que
     relê as regras do disco a cada pedido — edita-se o JSON, guarda-se,
     e a árvore aparece redesenhada no navegador;
  3. os ficheiros docs/fluxogramas/*.mmd, que podem ser abertos e editados
     visualmente em https://mermaid.live.

Sem dependências no servidor: aqui gera-se apenas o TEXTO Mermaid; o
desenho acontece no navegador com a biblioteca mermaid EMBUTIDA no
projeto (static/vendor/mermaid.min.js). Desde a v0.12 não há CDN em
runtime — o documento de validação leva a biblioteca dentro do próprio
ficheiro e desenha offline. Os desfechos usam as cinco cores de
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
    "pt": {"inicio": "Início", "sim": "Sim", "nao": "Não"},
    "en": {"inicio": "Start", "sim": "Yes", "nao": "No"},
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


def _t(obj: dict, campo: str, idioma: str) -> str:
    """Valor do campo no idioma pedido; sem tradução, recua para o PT.

    O recuo é deliberado: um fluxograma inglês com uma pergunta ainda em
    português é útil (e denuncia a falta ao auditor de traduções); um
    fluxograma com buracos não é.
    """
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
    """Texto Mermaid (flowchart TD) de um fluxo de triagem completo.

    As perguntas são numeradas com os mesmos números das listas do
    documento de validação, para o clínico cruzar as duas vistas.
    """
    rot = _ROTULOS.get(idioma, _ROTULOS["pt"])
    linhas = [
        "flowchart TD",
        f'  inicio(["{rot["inicio"]}: {_quebrar(_t(fluxo, "nome", idioma), 26)}"])',
    ]

    numeros = {p["id"]: i + 1 for i, p in enumerate(fluxo["perguntas"])}
    for p in fluxo["perguntas"]:
        rotulo_p = _quebrar(_t(p, "texto", idioma))
        linhas.append(f'  {p["id"]}["{numeros[p["id"]]}. {rotulo_p}"]')

    linhas.append(f'  inicio --> {fluxo["perguntas"][0]["id"]}')

    cores_usadas: set[str] = set()
    for p in fluxo["perguntas"]:
        for resposta, rotulo in (("sim", rot["sim"]), ("nao", rot["nao"])):
            ramo = p[resposta]
            if "proxima" in ramo:
                linhas.append(f'  {p["id"]} -->|{rotulo}| {ramo["proxima"]}')
            else:
                r = ramo["resultado"]
                cor = r.get("cor", "desconhecida")
                cores_usadas.add(cor)
                no_id = f'{p["id"]}_{resposta}'
                texto = _nome_da_cor(cor, idioma)
                motivo = _t(r, "motivo", idioma)
                if motivo:
                    texto += f"<br/>{_quebrar(motivo)}"
                linhas.append(f'  {no_id}(["{texto}"]):::{cor}')
                linhas.append(f'  {p["id"]} -->|{rotulo}| {no_id}')

    for cor in sorted(cores_usadas):
        fundo, letra = _ESTILOS_COR.get(cor, ("#666666", "#ffffff"))
        linhas.append(f"  classDef {cor} fill:{fundo},color:{letra},stroke:#333;")

    return "\n".join(linhas)


def gerar_todos(fluxos: dict[str, dict], idioma: str = "pt") -> dict[str, str]:
    """{id_do_fluxo: texto mermaid} para todos os fluxos carregados."""
    return {fid: mermaid_do_fluxo(f, idioma) for fid, f in fluxos.items()}
