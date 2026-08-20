# -*- coding: utf-8 -*-
"""Testes da v0.16 — o frontend "aplicação de saúde".

A v0.16 é uma entrega de INTERFACE: nenhum texto clínico muda (perguntas,
conselhos e regras ficam intactos nos dados; os testes de conteúdo das
versões anteriores garantem-no). O que se fixa aqui é a camada de
apresentação nova:

  - barra de progresso HONESTA nas perguntas ("Pergunta N · no máximo M",
    porque o total exato não é prometível: a avaliação pode terminar antes);
  - botões de resposta Sim/Não gigantes e NEUTROS (sem verde/vermelho:
    na triagem, "sim" costuma significar pior, e pintar o "sim" de verde
    daria o sinal errado);
  - guia de prioridade tingida na cor da triagem, compacta de propósito
    (o elemento-assinatura);
  - cartão da unidade com blocos de estatística e mapa em acordeão,
    aberto por defeito e com o Leaflet a arrancar só lá dentro;
  - lista de queixas agrupada (adultos / bebés e crianças) pela flag
    `pediatrico` que a API já enviava;
  - todas as chaves novas de texto existem em PT e EN.

Como nos testes anteriores de frontend, verifica-se o que é verificável
sem browser: presença e coerência de marcação/chaves nos ficheiros. A
auditoria de acessibilidade (contrastes, alvos de toque) corre à parte em
scripts/auditar_acessibilidade.py e já é exigida pelo test_v15_2.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
INDEX = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
APPJS = (RAIZ / "static" / "js" / "app.js").read_text(encoding="utf-8")
TEXTOS = (RAIZ / "static" / "js" / "textos.js").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "css" / "style.css").read_text(encoding="utf-8")


# ------------------------------------------------------------- versão --


def test_versao_0_16():
    from app.versao import VERSAO

    assert tuple(int(x) for x in VERSAO.split(".")) >= (0, 16, 0)


def test_index_html_cache_atual_e_sem_cracha_de_versao():
    # O crachá de versão saiu do frontend do utente (v0.16.2): a versão do
    # build confirma-se em /api/saude e nas páginas internas (/fluxogramas,
    # /revisao), não no ecrã do utente. Este teste impede que o crachá
    # reapareça e fixa o cache-busting atual.
    assert "app-versao" not in INDEX
    assert 'class="versao"' not in INDEX
    assert INDEX.count("?v=23") == 4


# ------------------------------------------------- chaves bilingues novas --


def test_chaves_novas_em_pt_e_en():
    # Cada chave nova tem de existir exatamente duas vezes: bloco pt e bloco
    # en (o padrão fixado desde o test_v11_2 para as chaves de chips).
    novas = (
        "pergunta_max:",
        "progresso_aria:",
        "ler_pergunta_aria:",
        "res_intro:",
        "ver_mapa:",
        "ocultar_mapa:",
        "horarios_titulo:",
        "qx_grupo_geral:",
        "qx_grupo_ped:",
        "atalho_112_desc:",
        "atalho_sns_desc:",
        "atalho_112_aria:",
        "atalho_sns_aria:",
        "inicio_como:",
        "estado_aberto:",
        "estado_fechado:",
        "stat_carro:",
        "stat_espera:",
        "stat_agora:",
        "minutos_aprox:",
    )
    for chave in novas:
        assert TEXTOS.count(chave) == 2, f"esperava {chave} em pt e en"


# ------------------------------------------------------ ecrã da pergunta --


def test_pergunta_tem_barra_de_progresso_honesta():
    # A barra volta (saíra na v0.14.0) mas com o MÁXIMO do fluxo, nunca um
    # total exato que não se pode prometer.
    assert "progresso__barra" in APPJS
    assert 't("pergunta_max"' in APPJS
    assert 't("progresso_aria"' in APPJS
    assert "aria-valuemax" in APPJS


def test_pergunta_sem_cor_de_manchester():
    # Decisão da v0.14.1 mantida: nenhuma classe pulseira--<cor> no ecrã da
    # pergunta (a função ecraPergunta não pinta prioridade nem cor).
    inicio = APPJS.find("function ecraPergunta")
    fim = APPJS.find("/* ----", inicio + 1)
    corpo = APPJS[inicio:fim]
    assert "pulseira--" not in corpo
    assert "cor_info" not in corpo


def test_respostas_gigantes_e_neutras():
    assert "botao--resposta" in APPJS
    # Alvo de toque dos botões de resposta: pelo menos 72px (bem acima do
    # mínimo de 48px que o auditor exige aos .botao).
    m = re.search(r"\.botao--resposta\s*\{[^}]*min-height:\s*(\d+)px", CSS)
    assert m and int(m.group(1)) >= 72, "Sim/Não deviam ser gigantes"
    # Neutros: nada de pintar o "sim" com a paleta de triagem.
    bloco = re.search(r"\.botao--resposta\s*\{[^}]*\}", CSS).group(0)
    assert "--verde" not in bloco and "--vermelho" not in bloco


def test_ouvir_a_pergunta_em_voz_alta():
    assert "btn-ler--pergunta" in APPJS
    assert "function lerPergunta" in APPJS


# ------------------------------------------------------ guia de prioridade --


def test_guia_tingida_por_cor_com_texto_acessivel():
    # As cinco variantes têm tinta de fundo e cor de texto próprias; os
    # valores de --cor-texto são verificados (>= 4.5:1) pelo auditor.
    for cor in ("vermelho", "laranja", "amarelo", "verde", "azul"):
        assert f".pulseira--{cor}" in CSS
    assert CSS.count("--tinta-fundo:") >= 5
    assert CSS.count("--cor-texto:") >= 5
    assert 't("res_intro")' in APPJS


# ------------------------------------------------------ ecrã de unidades --


def test_unidade_com_blocos_de_estatistica_e_chips():
    assert "stat__valor" in APPJS and "stats" in APPJS
    # Os chips de contexto continuam (invariante do test_v11_2, reafirmado):
    assert "unidade__trajeto" in APPJS
    assert 't("chip_km"' in APPJS and 't("chip_viagem"' in APPJS


def test_horarios_em_acordeao_abertos_quando_fechada():
    assert "detalhes-horarios" in APPJS
    # Aberto por defeito quando a unidade está fechada (é quando interessa).
    assert re.search(r'aberta_agora \? "" : " open"', APPJS)


def test_mapa_aberto_por_defeito_em_acordeao():
    # O mapa arranca VISÍVEL e o botão oferece "Ocultar o mapa"; o
    # acordeão mantém-se para quem preferir o ecrã curto, e o Leaflet
    # arranca só dentro dele (nunca no corpo do render do ecrã).
    assert "ligarMapaAcordeao" in APPJS
    assert "mapa-envelope" in APPJS
    assert "estado.mapaVisivel = true" in APPJS
    assert 't("ver_mapa"' in APPJS or '"ver_mapa"' in APPJS
    assert "aria-expanded" in APPJS
    assert "invalidateSize" in APPJS
    corpo_ecra = APPJS[
        APPJS.find("function ecraEncaminhamento") : APPJS.find("function ligarMapaAcordeao")
    ]
    assert "iniciarMapa(" not in corpo_ecra


# ------------------------------------------------------- lista de queixas --


def test_queixas_agrupadas_por_pediatrico():
    assert 't("qx_grupo_geral")' in APPJS and 't("qx_grupo_ped")' in APPJS
    assert "q.pediatrico" in APPJS


# ------------------------------------------------------------- início --


def test_inicio_com_atalhos_e_passos_recolhidos():
    assert 't("atalho_112_aria")' in APPJS
    assert 't("inicio_como")' in APPJS
    # Os três passos continuam (recolhidos), com os mesmos textos.
    for chave in ("passo1_t", "passo2_t", "passo3_t"):
        assert f't("{chave}")' in APPJS


# ------------------------------------------------------- movimento reduzido --


def test_microinteracoes_respeitam_movimento_reduzido():
    assert "MOVIMENTO_OK" in APPJS
    assert "prefers-reduced-motion" in APPJS
    assert "prefers-reduced-motion" in CSS
