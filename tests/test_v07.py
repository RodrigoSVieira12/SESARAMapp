"""Testes das novidades da v0.7: fluxogramas Mermaid gerados das regras.

Não há renderizador Mermaid nos testes — validamos a ESTRUTURA do texto
gerado: todos os nós referenciados existem, cada ramo terminal produz um
desfecho com a classe da cor certa, e os rótulos não têm aspas cruas
(que rebentariam a sintaxe Mermaid).
"""

import re

from app.core import fluxogramas
from app.core.triage_engine import TriageEngine

motor = TriageEngine()

RE_NO = re.compile(r"^\s{2}(\w+)[\[\(]", re.M)
RE_ARESTA = re.compile(r"^\s{2}(\w+) -->(?:\|[^|]+\|)? (\w+)$", re.M)


def test_fluxograma_da_febre_tem_a_estrutura_esperada():
    texto = fluxogramas.mermaid_do_fluxo(motor.fluxos["febre"])
    assert texto.startswith("flowchart TD")
    assert "fe_q1[" in texto
    assert "fe_q1 -->|Sim| fe_q10" in texto  # o salto que só se vê desenhado
    assert "classDef verde" in texto and "classDef laranja" in texto


def test_todas_as_arestas_apontam_para_nos_que_existem():
    for fid, fluxo in motor.fluxos.items():
        texto = fluxogramas.mermaid_do_fluxo(fluxo)
        nos = set(RE_NO.findall(texto))
        for origem, destino in RE_ARESTA.findall(texto):
            assert origem in nos, (fid, origem)
            assert destino in nos, (fid, destino)


def test_cada_ramo_terminal_gera_um_desfecho_colorido():
    for fid, fluxo in motor.fluxos.items():
        texto = fluxogramas.mermaid_do_fluxo(fluxo)
        terminais = sum(
            1
            for p in fluxo["perguntas"]
            for resposta in ("sim", "nao")
            if "resultado" in p[resposta]
        )
        assert texto.count(":::") == terminais, fid


def test_rotulos_sem_aspas_cruas():
    # Cada linha com um rótulo deve ter exatamente as 2 aspas que o
    # delimitam; aspas do texto clínico têm de sair como #quot;.
    for fluxo in motor.fluxos.values():
        texto = fluxogramas.mermaid_do_fluxo(fluxo)
        for linha in texto.splitlines():
            if '["' in linha or '(["' in linha:
                assert linha.count('"') == 2, linha


def test_gerar_todos_cobre_todos_os_fluxos():
    todos = fluxogramas.gerar_todos(motor.fluxos)
    assert set(todos) == set(motor.fluxos)
    assert all(t.startswith("flowchart TD") for t in todos.values())
