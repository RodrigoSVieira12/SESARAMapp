"""Testes dos feriados, do comportamento ao fim de semana e do bloco
de autocuidado (v0.4).

Datas de referência usadas (verificar num calendário, se mudares algo):
  2026-07-04 sábado          2026-07-01 quarta, Dia da RAM (feriado)
  2026-07-06 segunda-feira   2026-12-25 sexta, Natal
  2026-12-26 sábado, Primeira Oitava (feriado regional)
"""

from datetime import date, datetime

from fastapi.testclient import TestClient

from app.core import feriados, horarios, routing
from app.main import app

cliente = TestClient(app)

FUNCHAL = (32.6496, -16.9086)

SABADO_15H = datetime(2026, 7, 4, 15, 0)
FERIADO_RAM_15H = datetime(2026, 7, 1, 15, 0)   # quarta-feira
SEGUNDA_10H = datetime(2026, 7, 6, 10, 0)

HORARIO_DIAS_UTEIS = {
    "tipo": "semanal",
    "horas": {
        "seg": ["08:00-20:00"], "ter": ["08:00-20:00"], "qua": ["08:00-20:00"],
        "qui": ["08:00-20:00"], "sex": ["08:00-20:00"], "sab": [], "dom": [],
    },
}


# ------------------------------------------------------------ feriados --

def test_pascoa_em_datas_conhecidas():
    assert feriados.pascoa(2024) == date(2024, 3, 31)
    assert feriados.pascoa(2025) == date(2025, 4, 20)
    assert feriados.pascoa(2026) == date(2026, 4, 5)


def test_feriados_moveis_de_2026():
    lista = feriados.feriados(2026)
    assert lista[date(2026, 4, 3)] == "Sexta-feira Santa"
    assert lista[date(2026, 6, 4)] == "Corpo de Deus"


def test_feriados_regionais_da_madeira():
    lista = feriados.feriados(2026)
    assert "Madeira" in lista[date(2026, 7, 1)]
    assert "Oitava" in lista[date(2026, 12, 26)]


def test_tipo_de_dia():
    assert feriados.tipo_de_dia(date(2026, 7, 4)) == "sabado"
    assert feriados.tipo_de_dia(date(2026, 7, 5)) == "domingo"
    assert feriados.tipo_de_dia(date(2026, 7, 6)) == "dia_util"
    assert feriados.tipo_de_dia(date(2026, 7, 1)) == "feriado"
    # Feriado que calha ao sábado continua a ser "feriado".
    assert feriados.tipo_de_dia(date(2026, 12, 26)) == "feriado"


def test_descricao_do_dia_inclui_o_nome_do_feriado():
    descricao = feriados.descricao_do_dia(date(2026, 7, 1))
    assert "quarta-feira" in descricao and "Madeira" in descricao


# ---------------------------------------------- horários com feriados --

def test_feriado_a_meio_da_semana_conta_como_fechado():
    # Era este o bug: 1 de julho (quarta) aparecia aberto como um dia útil.
    assert not horarios.esta_aberto(HORARIO_DIAS_UTEIS, FERIADO_RAM_15H)
    assert horarios.esta_aberto(HORARIO_DIAS_UTEIS, SEGUNDA_10H)


def test_servico_pode_abrir_num_feriado_com_chave_propria():
    com_feriado = {
        "tipo": "semanal",
        "horas": {**HORARIO_DIAS_UTEIS["horas"], "feriado": ["09:00-13:00"]},
    }
    assert horarios.esta_aberto(com_feriado, datetime(2026, 7, 1, 10, 0))
    assert not horarios.esta_aberto(com_feriado, datetime(2026, 7, 1, 15, 0))


def test_proxima_abertura_salta_o_fim_de_semana():
    abre = horarios.proxima_abertura(HORARIO_DIAS_UTEIS, SABADO_15H)
    assert abre == datetime(2026, 7, 6, 8, 0)


def test_proxima_abertura_salta_natal_oitava_e_domingo():
    # sex 25 (Natal) → sáb 26 (Oitava) → dom 27 → abre segunda 28 às 08:00.
    abre = horarios.proxima_abertura(HORARIO_DIAS_UTEIS, datetime(2026, 12, 25, 9, 0))
    assert abre == datetime(2026, 12, 28, 8, 0)


def test_proxima_abertura_no_proprio_dia():
    abre = horarios.proxima_abertura(HORARIO_DIAS_UTEIS, datetime(2026, 7, 6, 3, 0))
    assert abre == datetime(2026, 7, 6, 8, 0)


def test_proxima_abertura_de_24h_e_none():
    assert horarios.proxima_abertura({"tipo": "24h"}, SABADO_15H) is None


# ------------------------------------------------- routing: verde/azul --

def test_verde_ao_sabado_explica_o_dia_e_oferece_esperar_em_casa():
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=SABADO_15H)
    assert saida["dia"]["tipo"] == "sabado"
    assert "sábado" in saida["mensagem"]
    assert "autocuidado" in saida
    # A unidade recomendada está mesmo aberta (atendimento urgente).
    assert saida["unidade"]["aberta_agora"] is True
    # E o centro de saúde do utente diz quando reabre.
    centro = saida["centro_saude_proximo"]
    assert centro and "segunda-feira" in centro["proxima_abertura_texto"]


def test_verde_num_feriado_nao_assume_dia_util():
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=FERIADO_RAM_15H)
    assert saida["dia"]["tipo"] == "feriado"
    assert "feriado" in saida["mensagem"]
    # Nenhuma consulta de centro de saúde pode contar como aberta.
    assert "consulta_aberta" not in saida["unidade"]["servicos_abertos"]


def test_verde_em_dia_util_mantem_recomendacao_direta_com_autocuidado():
    saida = routing.decidir_encaminhamento("verde", *FUNCHAL, quando=SEGUNDA_10H)
    assert saida["dia"]["tipo"] == "dia_util"
    assert saida["mensagem"].startswith("Dirija-se")
    assert saida["autocuidado"]["titulo"]


def test_azul_tem_bloco_de_autocuidado_e_reabertura():
    domingo = datetime(2026, 7, 5, 15, 0)
    saida = routing.decidir_encaminhamento("azul", *FUNCHAL, quando=domingo)
    assert saida["acao"] == "autocuidado"
    assert saida["autocuidado"]["alerta"]
    assert saida["unidade"]["aberta_agora"] is False
    assert "abre" in saida["unidade"]["proxima_abertura_texto"]


# ---------------------------------------------------------------- API --

def test_api_feriados_inclui_o_dia_da_madeira():
    resposta = cliente.get("/api/feriados", params={"ano": 2026})
    assert resposta.status_code == 200
    nomes = [f["nome"] for f in resposta.json()["feriados"]]
    assert any("Madeira" in n for n in nomes)


def test_api_encaminhamento_devolve_dia_e_autocuidado():
    resposta = cliente.post("/api/encaminhamento", json={
        "cor": "verde", "lat": FUNCHAL[0], "lng": FUNCHAL[1],
        "quando": "2026-07-04T15:00:00",
    })
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["dia"]["tipo"] == "sabado"
    assert corpo["autocuidado"]["titulo"]
