"""Testes das alterações da v0.14.2.

O que estes testes prendem:
- Feriados MUNICIPAIS por concelho (app/core/feriados.py), aplicados só
  às unidades desse concelho, com as urgências 24h sempre abertas — e o
  caso do Santo da Serra (concelho «Machico»), que fecha a 8 de maio e
  não a 15 de janeiro.
- Compatibilidade: as funções de horário/feriado continuam a funcionar
  sem o argumento `concelho` (feriados nacionais e regionais iguais).
- Vermelho (emergente) NÃO traz tempo de espera nem pessoas em espera.
- Azul passa a ter alternativas (o principal + os dois seguintes), como
  o verde; no Porto Santo a regra da ilha mantém só a unidade local.
- As trocas de nome/descrição das queixas e o «xixi» -> «urina» na
  pergunta das 24 horas.

Datas escolhidas de propósito (todas em dia útil, para isolar o efeito
do feriado municipal): 8 e 15 de janeiro de 2026 são quintas-feiras; 8 e
15 de maio de 2026 são sextas-feiras.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from app.core import espera, feriados, horarios, routing

RAIZ = Path(__file__).resolve().parents[1]

# Dias úteis (quinta e sexta), sem feriado nacional, às 10:00.
QUINTA_08JAN_10H = datetime(2026, 1, 8, 10, 0)  # normal (controlo)
QUINTA_15JAN_10H = datetime(2026, 1, 15, 10, 0)  # feriado de Santa Cruz
SEXTA_08MAI_10H = datetime(2026, 5, 8, 10, 0)  # feriado de Machico
SEXTA_15MAI_10H = datetime(2026, 5, 15, 10, 0)  # normal (controlo)

FUNCHAL = (32.6496, -16.9086)
SANTA_CRUZ = (32.68960137504053, -16.794276586899944)
PORTO_SANTO = (33.05975933528906, -16.332505659904278)

_UNIDADES = {
    u["id"]: u for u in json.loads((RAIZ / "app" / "data" / "unidades.json").read_text("utf-8"))
}


def _unidade_aberta(uid: str, quando: datetime) -> bool:
    u = _UNIDADES[uid]
    return any(horarios.esta_aberto(cfg, quando, u["concelho"]) for cfg in u["servicos"].values())


@pytest.fixture()
def sem_esperas(monkeypatch):
    monkeypatch.setattr(
        espera,
        "do_cache",
        lambda: {"disponivel": False, "desatualizado": False, "unidades": {}, "obtido_em": None},
    )


# --------------------------------------------------------------------- #
# Feriados municipais — a lógica pura em feriados.py                      #
# --------------------------------------------------------------------- #


def test_feriado_municipal_so_com_concelho():
    # Sem concelho, um feriado municipal nunca conta.
    assert feriados.feriado_em(date(2026, 1, 15)) is None
    # Com o concelho certo, conta.
    assert feriados.feriado_em(date(2026, 1, 15), "Santa Cruz") == "Feriado Municipal de Santa Cruz"
    # Concelho errado nesse dia: não conta.
    assert feriados.feriado_em(date(2026, 1, 15), "Funchal") is None


def test_todos_os_onze_concelhos_tem_feriado():
    assert set(feriados.FERIADOS_MUNICIPAIS) == {
        "Funchal",
        "Santa Cruz",
        "Machico",
        "Santana",
        "Calheta",
        "Ponta do Sol",
        "Ribeira Brava",
        "Câmara de Lobos",
        "São Vicente",
        "Porto Moniz",
        "Porto Santo",
    }
    # As datas dadas pelo SESARAM (mês, dia).
    esperado = {
        "Funchal": (8, 21),
        "Santa Cruz": (1, 15),
        "Machico": (5, 8),
        "Santana": (5, 25),
        "Calheta": (6, 24),
        "Ponta do Sol": (9, 8),
        "Ribeira Brava": (6, 29),
        "Câmara de Lobos": (10, 4),
        "São Vicente": (1, 22),
        "Porto Moniz": (7, 22),
        "Porto Santo": (6, 24),
    }
    for concelho, (mes, dia) in esperado.items():
        m, d, _nome = feriados.FERIADOS_MUNICIPAIS[concelho]
        assert (m, d) == (mes, dia), concelho


def test_feriado_nacional_tem_precedencia_no_nome():
    # 1 de julho é feriado regional (nacional/regional > municipal no nome).
    assert feriados.feriado_em(date(2026, 7, 1), "Funchal") == "Dia da Região Autónoma da Madeira"


def test_tipo_de_dia_com_e_sem_concelho():
    # 15 jan 2026 é quinta-feira; só é "feriado" para Santa Cruz.
    assert feriados.tipo_de_dia(date(2026, 1, 15)) == "dia_util"
    assert feriados.tipo_de_dia(date(2026, 1, 15), "Santa Cruz") == "feriado"
    assert feriados.tipo_de_dia(date(2026, 1, 15), "Funchal") == "dia_util"


def test_descricao_do_dia_menciona_feriado_municipal():
    d = feriados.descricao_do_dia(date(2026, 8, 21), "Funchal")
    assert "feriado: Feriado Municipal do Funchal" in d


# --------------------------------------------------------------------- #
# Feriados municipais — efeito nos horários das unidades                 #
# --------------------------------------------------------------------- #


def test_consultas_de_santa_cruz_fecham_no_seu_feriado():
    # 15 jan: consultas de Santa Cruz fechadas; num dia útil normal, abertas.
    for uid in ("cs_santa_cruz", "cs_canico", "cs_camacha", "cs_gaula"):
        assert _unidade_aberta(uid, QUINTA_08JAN_10H), f"{uid} devia estar aberto a 8 jan"
        assert not _unidade_aberta(uid, QUINTA_15JAN_10H), f"{uid} devia estar fechado a 15 jan"


def test_santo_da_serra_segue_machico_nao_santa_cruz():
    # O Santo da Serra tem concelho «Machico»: abre a 15 jan (feriado de
    # Santa Cruz) e fecha a 8 mai (feriado de Machico).
    assert _unidade_aberta("cs_santo_da_serra", QUINTA_15JAN_10H)
    assert not _unidade_aberta("cs_santo_da_serra", SEXTA_08MAI_10H)
    # Controlo: num dia útil normal de maio está aberto.
    assert _unidade_aberta("cs_santo_da_serra", SEXTA_15MAI_10H)


def test_urgencias_nao_fecham_no_feriado_municipal():
    # Unidades com atendimento urgente / urgência 24h ficam sempre abertas.
    assert _unidade_aberta("hnm", QUINTA_15JAN_10H)  # urgência polivalente
    assert _unidade_aberta("cs_machico", SEXTA_08MAI_10H)  # atendimento urgente 24h
    assert _unidade_aberta("cs_camara_lobos", QUINTA_15JAN_10H)


def test_horarios_compatibilidade_sem_concelho():
    # Sem `concelho`, o comportamento antigo mantém-se: um feriado
    # nacional fecha um horário "semanal" e um dia útil normal abre-o.
    horario = _UNIDADES["cs_santa_cruz"]["servicos"]["consulta_aberta"]
    assert horarios.esta_aberto(horario, QUINTA_08JAN_10H)  # dia útil
    assert not horarios.esta_aberto(horario, datetime(2026, 7, 1, 10, 0))  # feriado regional
    # 24h continua sempre aberto.
    assert horarios.esta_aberto({"tipo": "24h"}, QUINTA_15JAN_10H)


def test_proxima_abertura_salta_feriado_municipal():
    # Uma consulta de Santa Cruz fechada a 15 jan não "reabre" nesse dia.
    horario = _UNIDADES["cs_santa_cruz"]["servicos"]["consulta_aberta"]
    abre = horarios.proxima_abertura(horario, QUINTA_15JAN_10H, concelho="Santa Cruz")
    assert abre is not None
    assert abre.date() > date(2026, 1, 15)


# --------------------------------------------------------------------- #
# Feriados municipais — integração no encaminhamento                     #
# --------------------------------------------------------------------- #


def test_dia_do_encaminhamento_reconhece_feriado_do_utente(sem_esperas):
    # Utente junto de Santa Cruz, a 15 jan: o bloco "dia" nomeia o feriado.
    saida = routing.decidir_encaminhamento("verde", *SANTA_CRUZ, QUINTA_15JAN_10H)
    assert saida["dia"]["feriado"] == "Feriado Municipal de Santa Cruz"
    assert saida["dia"]["tipo"] == "feriado"
    # A recomendação continua a apontar para uma unidade ABERTA.
    assert saida["unidade"] is not None and saida["unidade"]["aberta_agora"]


# --------------------------------------------------------------------- #
# Vermelho: sem tempo de espera nem pessoas em espera                    #
# --------------------------------------------------------------------- #


def _esperas_hnm():
    return {
        "disponivel": True,
        "desatualizado": False,
        "obtido_em": "2026-01-08T10:00",
        "unidades": {
            "hnm": {
                "tipo_dados": "por_cor",
                "atualizado_no_site": "2026-01-08 10:00",
                "fonte": "teste",
                "por_cor": {
                    "vermelho": {"tempo_medio_min": 0, "em_espera": 1, "atendidos": 3},
                    "laranja": {"tempo_medio_min": 30, "em_espera": 5, "atendidos": 9},
                },
                "geral": {"tempo_medio_min": 50, "em_espera": 12, "atendidos": 20},
            }
        },
    }


def test_vermelho_nao_traz_tempo_de_espera(monkeypatch):
    monkeypatch.setattr(espera, "do_cache", _esperas_hnm)
    saida = routing.decidir_encaminhamento("vermelho", *FUNCHAL, QUINTA_08JAN_10H)
    assert saida["unidade"] is not None
    # Nem tempo de espera nem pessoas em espera no cartão de referência.
    assert "tempo_espera" not in saida["unidade"]


def test_laranja_ainda_traz_tempo_de_espera(monkeypatch):
    # Controlo: a supressão é SÓ no vermelho. No laranja a espera aparece.
    monkeypatch.setattr(espera, "do_cache", _esperas_hnm)
    saida = routing.decidir_encaminhamento("laranja", *FUNCHAL, QUINTA_08JAN_10H)
    assert saida["unidade"] is not None
    assert saida["unidade"].get("tempo_espera", {}).get("minutos") == 30


# --------------------------------------------------------------------- #
# Azul: agora com secção de alternativas (como o verde)                  #
# --------------------------------------------------------------------- #


def test_azul_recomenda_principal_e_duas_alternativas(sem_esperas):
    saida = routing.decidir_encaminhamento("azul", *FUNCHAL, QUINTA_08JAN_10H)
    assert saida["acao"] == "autocuidado"
    assert saida["unidade"] is not None
    assert len(saida["alternativas"]) == 2
    # O principal não se repete nas alternativas.
    ids_alt = {a["id"] for a in saida["alternativas"]}
    assert saida["unidade"]["id"] not in ids_alt


def test_azul_no_porto_santo_sem_alternativas(sem_esperas):
    saida = routing.decidir_encaminhamento("azul", *PORTO_SANTO, QUINTA_08JAN_10H)
    assert saida["unidade"] is not None
    assert saida["alternativas"] == []


# --------------------------------------------------------------------- #
# Textos das queixas: trocas e "xixi" -> "urina"                         #
# --------------------------------------------------------------------- #


def _regra(fid: str) -> dict:
    return json.loads((RAIZ / "app" / "data" / "rules" / f"{fid}.json").read_text("utf-8"))


def test_linguagem_simples_no_titulo_das_queixas():
    esperado = {
        "t_c_e_trauma_cranio_encefalico": (
            "Pancada ou traumatismo na cabeça",
            "T.C.E. – Trauma crânio-encefálico.",
        ),
        "problemas_oftalmologicos": ("Problema nos olhos ou na visão", "Problemas oftalmológicos."),
        "palpitacoes": ("Sensação de batimentos cardíacos rápidos ou irregulares", "Palpitações."),
        "hemorragia_gastrointestinal": (
            "Sangue nos vómitos ou nas fezes",
            "Hemorragia gastrointestinal.",
        ),
        "grande_traumatismo": ("Acidente ou lesão grave", "Grande traumatismo."),
        "erupcoes_cutaneas": ("Manchas, borbulhas ou erupção na pele", "Erupções cutâneas."),
    }
    for fid, (nome, descricao) in esperado.items():
        r = _regra(fid)
        assert r["nome"] == nome, fid
        assert r["descricao"] == descricao, fid


def test_rn_passa_a_recem_nascido_no_titulo():
    r = _regra("rn_que_nao_esta_bem_28_dias")
    assert r["nome"] == "Recém-nascido que não está bem (< 28 dias)"
    assert not r["nome"].startswith("RN ")


def test_pergunta_24h_usa_urina_e_nao_xixi():
    # A pergunta das 24 horas passou a "urina"; as perguntas de criança
    # mantêm "xixi".
    r = _regra("t_c_e_trauma_cranio_encefalico")
    perguntas = json.dumps(r, ensure_ascii=False)
    assert "controlar a urina ou as fezes" in perguntas
    assert "controlar o xixi ou as fezes" not in perguntas
