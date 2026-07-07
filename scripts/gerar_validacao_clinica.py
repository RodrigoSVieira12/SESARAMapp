#!/usr/bin/env python3
"""Gera um documento imprimível para a VALIDAÇÃO CLÍNICA das regras.

Uso, a partir da pasta do projeto:

    python scripts/gerar_validacao_clinica.py

Cria docs/validacao_clinica.html, abre no navegador e imprime (Ctrl+P).
Cada queixa fica numa página própria, com as perguntas numeradas, os
desfechos de cada resposta, espaço para correções manuscritas e um bloco
de assinatura/data para o profissional que validar.

A ideia: o clínico corrige NO PAPEL; tu passas as correções para os JSON
em app/data/rules/, atualizas o campo "fonte" com quem validou e quando,
e voltas a correr `python scripts/validar_dados.py` e `python -m pytest`.
"""

from __future__ import annotations

import html
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core import fluxogramas  # noqa: E402
from app.core.cores import CORES  # noqa: E402
from app.core.routing import TEXTOS_AUTOCUIDADO  # noqa: E402
from app.core.triage_engine import TriageEngine  # noqa: E402

SAIDA = RAIZ / "docs" / "validacao_clinica.html"

ESTILO = """
  body { font-family: Georgia, "Times New Roman", serif; color: #1c1c1c;
         max-width: 820px; margin: 2rem auto; padding: 0 1.5rem; line-height: 1.5; }
  h1, h2, h3 { font-family: Arial, Helvetica, sans-serif; }
  h1 { font-size: 1.6rem; }
  h2 { font-size: 1.3rem; border-bottom: 2px solid #1c1c1c; padding-bottom: 0.3rem; }
  .capa p { font-size: 1.05rem; }
  .aviso { border: 2px solid #b00; padding: 0.75rem 1rem; background: #fff5f5; }
  table.cores { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  table.cores th, table.cores td { border: 1px solid #999; padding: 0.4rem 0.6rem;
         font-size: 0.95rem; text-align: left; }
  .amostra { display: inline-block; width: 2.2rem; height: 1rem; border-radius: 3px;
         vertical-align: middle; border: 1px solid #0003; }
  section.queixa { page-break-before: always; }
  .meta { color: #555; font-size: 0.9rem; }
  .pergunta { margin: 1.1rem 0; padding-left: 0.5rem; border-left: 3px solid #ccc; }
  .pergunta p { margin: 0.25rem 0; }
  .ajuda { color: #555; font-style: italic; }
  .ramo { margin-left: 1rem; }
  .cor-tag { font-weight: bold; text-transform: uppercase; }
  .caixa-validacao { border: 1.5px solid #1c1c1c; padding: 0.9rem 1rem; margin-top: 1.5rem; }
  .caixa-validacao .linha { margin: 1.1rem 0 0; }
  .caixa-validacao .espaco { display: inline-block; border-bottom: 1px solid #1c1c1c;
         min-width: 260px; height: 1rem; }
  .obs { border: 1px dashed #888; min-height: 90px; margin-top: 0.75rem; }
  .diagrama { margin: 1rem 0; break-inside: avoid; }
  .diagrama svg { max-width: 100%; height: auto; }
  pre.mermaid { background: none; border: 0; padding: 0; }
  @media print { body { margin: 0.5rem auto; } .no-print { display: none; } }
"""


def descrever_ramo(ramo: dict, numeros: dict[str, int]) -> str:
    if "resultado" in ramo:
        r = ramo["resultado"]
        cor = r.get("cor", "?")
        partes = [f'<span class="cor-tag">{html.escape(cor)}</span>']
        if r.get("motivo"):
            partes.append(html.escape(r["motivo"]))
        texto = "RESULTADO: " + ", ".join(partes)
        if r.get("nota"):
            texto += f'<br /><span class="meta">Nota mostrada ao utente: '
            texto += f'{html.escape(r["nota"])}</span>'
        return texto
    return f"seguir para a pergunta {numeros[ramo['proxima']]}"


def seccao_queixa(fluxo: dict) -> str:
    numeros = {p["id"]: i + 1 for i, p in enumerate(fluxo["perguntas"])}
    blocos: list[str] = []
    for pergunta in fluxo["perguntas"]:
        n = numeros[pergunta["id"]]
        ajuda = (
            f'<p class="ajuda">Ajuda mostrada ao utente: '
            f'{html.escape(pergunta["ajuda"])}</p>'
            if pergunta.get("ajuda")
            else ""
        )
        fase = pergunta.get("fase", 2)
        blocos.append(f"""
        <div class="pergunta">
          <p class="meta">Fase {fase}</p>
          <p><strong>{n}.</strong> {html.escape(pergunta["texto"])}</p>
          {ajuda}
          <p class="ramo">Se <strong>SIM</strong>: {descrever_ramo(pergunta["sim"], numeros)}</p>
          <p class="ramo">Se <strong>NÃO</strong>: {descrever_ramo(pergunta["nao"], numeros)}</p>
        </div>""")

    return f"""
    <section class="queixa">
      <h2>{html.escape(fluxo["nome"])} <span class="meta">({html.escape(fluxo["id"])})</span></h2>
      <p class="meta">Descrição mostrada ao utente: {html.escape(fluxo.get("descricao", "(vazio)"))}<br />
      Estado atual do campo "fonte": {html.escape(fluxo.get("fonte", "(vazio)"))}</p>
      <h3>Fluxograma</h3>
      <p class="meta">Desenhado automaticamente a partir do ficheiro de regras —
      é a mesma informação das perguntas numeradas abaixo, no formato dos
      protocolos de triagem. (O desenho precisa de ligação à internet ao abrir
      este documento; sem ela, valem as perguntas numeradas.)</p>
      <pre class="mermaid diagrama">{html.escape(fluxogramas.mermaid_do_fluxo(fluxo))}</pre>
      <h3>Perguntas</h3>
      {''.join(blocos)}
      <div class="caixa-validacao">
        <strong>Validação clínica desta queixa</strong>
        <p class="linha">Correções necessárias? &nbsp; ☐ Não &nbsp;&nbsp; ☐ Sim (anotadas acima / abaixo)</p>
        <div class="obs"></div>
        <p class="linha">Validado por (nome e função): <span class="espaco"></span></p>
        <p class="linha">Data: <span class="espaco" style="min-width:120px"></span>
           &nbsp;&nbsp; Assinatura: <span class="espaco"></span></p>
      </div>
    </section>"""


def main() -> int:
    motor = TriageEngine()

    linhas_cores = "".join(
        f"""<tr><td><span class="amostra" style="background:{c['hex']}"></span>
        {c['nome']}</td><td>{c['classificacao']}</td><td>{c['tempo_alvo']}</td></tr>"""
        for c in CORES.values()
    )

    sinais = "".join(
        f"<li>{html.escape(s['texto'])}</li>" for s in motor.listar_red_flags()
    )

    seccoes = "".join(seccao_queixa(f) for f in motor.fluxos.values())

    def _lista(itens: list) -> str:
        return "<ul>" + "".join(f"<li>{html.escape(str(i))}</li>" for i in itens) + "</ul>"

    blocos_autocuidado = "".join(
        f"""
        <div class="pergunta">
          <p class="meta">Cor: <span class="cor-tag">{html.escape(cor)}</span></p>
          <p><strong>Título:</strong> {html.escape(t["titulo"])}</p>
          <p><strong>Introdução:</strong> {html.escape(t["intro"])}</p>
          <p><strong>Fazer (lista com visto ✓):</strong></p>{_lista(t.get("fazer", []))}
          <p><strong>Evitar (lista com cruz ✕):</strong></p>{_lista(t.get("evitar", []))}
          <p><strong>{html.escape(t.get("alerta_titulo", "Procure ajuda se:"))}</strong></p>{_lista(t.get("alerta", []))}
        </div>"""
        for cor, t in TEXTOS_AUTOCUIDADO.items()
    )

    seccao_textos = f"""
    <section class="queixa">
      <h2>Textos de encaminhamento e autocuidado <span class="meta">(routing)</span></h2>
      <p class="meta">Estes textos aparecem no ecrã final. Não são regras de
      triagem, mas orientam decisões do utente — por isso pedem a mesma
      validação. Regras de contexto já implementadas: ao fim de semana,
      em feriados (nacionais e regionais da RAM) e fora de horas, o verde
      apresenta explicitamente a opção de vigiar em casa com o apoio do
      SNS 24, além do atendimento urgente aberto; e as unidades fechadas
      indicam quando reabrem.</p>
      {blocos_autocuidado}
      <div class="pergunta">
        <p class="meta">Mensagem do verde fora de horas / fim de semana / feriado (modelo)</p>
        <p>"É sábado e os centros de saúde estão fechados (o mais próximo de
        si abre segunda-feira às 08:00). Numa situação pouco urgente tem duas
        opções razoáveis: vigiar em casa com o apoio do SNS 24, ou, se
        preferir ser observado hoje, dirigir-se a [unidade] ([X] km), com
        atendimento aberto."</p>
      </div>
      <div class="caixa-validacao">
        <strong>Validação clínica destes textos</strong>
        <p class="linha">Correções necessárias? &nbsp; ☐ Não &nbsp;&nbsp; ☐ Sim (anotadas abaixo)</p>
        <div class="obs"></div>
        <p class="linha">Validado por (nome e função): <span class="espaco"></span></p>
        <p class="linha">Data: <span class="espaco" style="min-width:120px"></span>
           &nbsp;&nbsp; Assinatura: <span class="espaco"></span></p>
      </div>
    </section>"""
    seccoes += seccao_textos

    documento = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="utf-8" />
<title>Validação clínica, Onde ir? (protótipo SESARAM)</title>
<style>{ESTILO}</style>
</head>
<body>
  <div class="capa">
    <h1>Onde ir?, Documento de validação clínica das regras de triagem</h1>
    <p class="meta">Gerado automaticamente a partir de app/data/rules/ em {date.today().isoformat()}.
    Protótipo académico, SESARAM, Região Autónoma da Madeira.</p>
    <div class="aviso"><strong>Estado atual:</strong> todos os fluxos abaixo são
    EXEMPLOS de desenvolvimento e ainda não foram validados clinicamente.
    Este documento existe precisamente para essa revisão: por favor risque,
    corrija e anote diretamente no papel.</div>
    <p><strong>Como ler:</strong> cada queixa tem perguntas de sim/não numeradas.
    Cada resposta ou remete para outra pergunta, ou termina numa cor de
    prioridade (inspirada na Triagem de Manchester). Cada queixa inclui também
    o <strong>fluxograma desenhado</strong> — a mesma árvore em formato visual,
    com os desfechos nas cinco cores e os números a cruzar com a lista. Em caso
    de dúvida, a regra do projeto é errar por excesso de urgência.</p>
    <p><strong>Tempos de espera:</strong> o encaminhamento pode ainda considerar
    os tempos de espera em tempo real do SESARAM (regra experimental com
    salvaguardas: só troca a unidade mais próxima se poupar ≥30 min e o desvio
    for ≤15 km) — igualmente por validar.</p>
    <table class="cores">
      <tr><th>Cor</th><th>Classificação</th><th>Tempo-alvo de observação</th></tr>
      {linhas_cores}
    </table>
    <p><strong>Fases:</strong> cada pergunta pertence a uma fase: 1 perguntas gerais, 2 perguntas específicas, 3 avaliação da gravidade. A ordem real depende das respostas.</p>
    <h2>Sinais de emergência (avaliados antes de qualquer queixa)</h2>
    <p class="meta">Qualquer um selecionado ⇒ VERMELHO e indicação para ligar 112.</p>
    <ul>{sinais}</ul>
    <p class="no-print"><em>Para imprimir: Ctrl+P (cada queixa sai numa página própria).</em></p>
  </div>
  {seccoes}
  <script src="https://unpkg.com/mermaid@10.9.1/dist/mermaid.min.js"></script>
  <script>
    if (window.mermaid) {{
      mermaid.initialize({{ startOnLoad: true, theme: "neutral", flowchart: {{ useMaxWidth: true }} }});
    }}
  </script>
</body>
</html>"""

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(documento, encoding="utf-8")

    # Fontes Mermaid em ficheiros próprios: abrem-se em https://mermaid.live
    # para ver e editar cada árvore, e ficam com histórico legível no Git.
    pasta_mmd = RAIZ / "docs" / "fluxogramas"
    pasta_mmd.mkdir(parents=True, exist_ok=True)
    for fid, texto in fluxogramas.gerar_todos(motor.fluxos).items():
        (pasta_mmd / f"{fid}.mmd").write_text(texto + "\n", encoding="utf-8")

    print(f"Documento criado: {SAIDA.relative_to(RAIZ)}")
    print(f"Fluxogramas Mermaid: {pasta_mmd.relative_to(RAIZ)}/*.mmd (editáveis em mermaid.live)")
    print("Abre-o no navegador e imprime com Ctrl+P.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
