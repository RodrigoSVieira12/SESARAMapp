# -*- coding: utf-8 -*-
"""Testes da v0.11.3: a tabela local de tempos por estrada.

Cobrem quatro camadas:
  1. o FICHEIRO entregue (app/data/tempos_medidos.json) e o gerador do
     esqueleto (scripts/atualizar_tempos_medidos.py);
  2. o MÓDULO de procura (app/core/tempos_medidos.py): âncoras, raio,
     desvio, barreiras, interruptores para desligar;
  3. a INTEGRAÇÃO no estimador (app/core/viagem.py), no encaminhamento
     e no /api/viagem, incluindo a prioridade OSRM > medido > rede;
  4. o script de preenchimento automático
     (scripts/calcular_tempos_medidos.py), com o motor de rotas SIMULADO
     (os testes não fazem pedidos à rede).

Os testes do módulo montam tabelas sintéticas diretamente no cache
(tm._cache = tm._preparar(...)): o ficheiro entregue segue por
preencher, e assim os testes não dependem de medições reais.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import localidades, unidades, viagem
from app.core import tempos_medidos as tm
from app.main import app

cliente = TestClient(app)

RAIZ = Path(__file__).resolve().parent.parent
DADOS_FICHEIRO = json.loads(
    (RAIZ / "app" / "data" / "tempos_medidos.json").read_text(encoding="utf-8")
)


def test_versao_0_11_3():
    from app import versao

    assert versao.VERSAO == "0.11.3"


def _carregar_script(nome: str):
    caminho = RAIZ / "scripts" / f"{nome}.py"
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


calc = _carregar_script("calcular_tempos_medidos")
atualizar = _carregar_script("atualizar_tempos_medidos")


# --------------------------------------------------------------------- #
# Utilitários                                                            #
# --------------------------------------------------------------------- #

@pytest.fixture(autouse=True)
def _estado_limpo():
    """Cada teste parte sem cache da tabela e sem estado OSRM."""
    tm._cache = None
    viagem._repor_estado_osrm()
    yield
    tm._cache = None
    viagem._repor_estado_osrm()


def _medicao(origem, nome, lat, lng, destinos, ilha="madeira"):
    return {
        "origem": origem,
        "nome": nome,
        "nivel": "sitio",
        "ilha": ilha,
        "lat": lat,
        "lng": lng,
        "destinos": destinos,
    }


def _tabela(medicoes, raio=3.0):
    return {
        "versao": 1,
        "parametros": {"raio_ancoragem_km": raio},
        "medicoes": medicoes,
    }


def _ativar(medicoes, raio=3.0):
    tm._cache = tm._preparar(_tabela(medicoes, raio=raio))


def _unidade(uid: str) -> dict:
    return next(u for u in unidades.todas() if u["id"] == uid)


def _centro_freguesia(cid: str, fid: str) -> tuple[float, float]:
    prep = localidades.carregar()
    concelho = next(c for c in prep["concelhos"] if c["id"] == cid)
    freguesia = next(f for f in concelho["freguesias"] if f["id"] == fid)
    centro = freguesia["centro"]
    return float(centro["lat"]), float(centro["lng"])


def _par(tempo=None, dist=None, **extras):
    par = {"tempo_min": tempo, "distancia_km": dist}
    par.update(extras)
    return par


# --------------------------------------------------------------------- #
# 1a. O ficheiro entregue                                                 #
# --------------------------------------------------------------------- #

def test_ficheiro_entregue_passa_a_validacao():
    assert tm.validar(DADOS_FICHEIRO) == []


def test_origens_cobrem_freguesias_e_sitios():
    prep = localidades.carregar()
    n_freg = sum(len(c["freguesias"]) for c in prep["concelhos"])
    n_sitios = sum(
        len(f["sitios"]) for c in prep["concelhos"] for f in c["freguesias"]
    )
    assert len(DADOS_FICHEIRO["medicoes"]) == n_freg + n_sitios


def test_destinos_existem_e_ficam_na_mesma_ilha():
    ilha_por_unidade = {
        u["id"]: u.get("ilha", "madeira") for u in unidades.todas()
    }
    for m in DADOS_FICHEIRO["medicoes"]:
        for uid in m["destinos"]:
            assert uid in ilha_por_unidade, f"{m['origem']} -> {uid}"
            assert ilha_por_unidade[uid] == m["ilha"], f"{m['origem']} -> {uid}"


def test_toda_origem_da_madeira_inclui_o_hospital():
    for m in DADOS_FICHEIRO["medicoes"]:
        if m["ilha"] == "madeira":
            assert "hnm" in m["destinos"], m["origem"]


# --------------------------------------------------------------------- #
# 1b. Validação apanha enganos de edição                                  #
# --------------------------------------------------------------------- #

def test_validar_apanha_unidade_inexistente():
    dados = copy.deepcopy(DADOS_FICHEIRO)
    dados["medicoes"][0]["destinos"]["cs_que_nao_existe"] = _par(10, 5.0)
    assert any("cs_que_nao_existe" in p for p in tm.validar(dados))


def test_validar_apanha_tempo_negativo():
    dados = copy.deepcopy(DADOS_FICHEIRO)
    primeiro = next(iter(dados["medicoes"][0]["destinos"]))
    dados["medicoes"][0]["destinos"][primeiro] = _par(-3, 5.0)
    assert any("tempo_min" in p for p in tm.validar(dados))


def test_validar_apanha_fonte_que_nao_e_texto():
    dados = copy.deepcopy(DADOS_FICHEIRO)
    primeiro = next(iter(dados["medicoes"][0]["destinos"]))
    dados["medicoes"][0]["destinos"][primeiro] = _par(10, 5.0, fonte=123)
    assert any("fonte" in p for p in tm.validar(dados))


# --------------------------------------------------------------------- #
# 1c. O gerador do esqueleto                                              #
# --------------------------------------------------------------------- #

def test_gerador_produz_esqueleto_todo_por_preencher():
    dados, resumo = atualizar.gerar(None)
    assert resumo["pares"] > 0
    for m in dados["medicoes"]:
        for valores in m["destinos"].values():
            assert valores["tempo_min"] is None
            assert valores["distancia_km"] is None


def test_gerador_preserva_medicoes_preenchidas():
    dados, _ = atualizar.gerar(None)
    origem = dados["medicoes"][0]["origem"]
    uid = next(iter(dados["medicoes"][0]["destinos"]))
    dados["medicoes"][0]["destinos"][uid] = _par(17, 9.9, fonte="manual")
    de_novo, resumo = atualizar.gerar(dados)
    m = next(x for x in de_novo["medicoes"] if x["origem"] == origem)
    assert m["destinos"][uid]["tempo_min"] == 17
    assert m["destinos"][uid]["fonte"] == "manual"
    assert resumo["preservados"] == 1


def test_gerador_com_todos_cobre_a_ilha_inteira():
    dados, _ = atualizar.gerar(None, todos=True)
    da_madeira = [
        u["id"] for u in unidades.todas() if u.get("ilha", "madeira") == "madeira"
    ]
    exemplo = next(m for m in dados["medicoes"] if m["ilha"] == "madeira")
    assert set(exemplo["destinos"]) == set(da_madeira) | {"hnm"}


# --------------------------------------------------------------------- #
# 2. O módulo de procura                                                  #
# --------------------------------------------------------------------- #

def test_tabela_sem_medicoes_fica_inativa():
    _ativar([_medicao("x/a", "A", 32.70, -16.90, {"hnm": _par()})])
    assert tm.carregar()["ativo"] is False
    assert tm.procurar(32.70, -16.90, "hnm") is None


def test_procurar_na_ancora_exata_devolve_o_valor_medido():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"hnm": _par(22, 14.6)})])
    resultado = tm.procurar(lat, lng, "hnm")
    assert resultado is not None
    assert resultado["minutos"] == pytest.approx(22.0)
    assert resultado["distancia_km"] == pytest.approx(14.6)
    assert resultado["desvio_km"] == pytest.approx(0.0, abs=0.01)


def test_procurar_ajusta_pelo_desvio_ate_a_ancora():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"hnm": _par(22, 14.6)})])
    resultado = tm.procurar(lat + 0.005, lng, "hnm")  # ~0.56 km a norte
    assert resultado is not None
    assert resultado["minutos"] > 22.0
    assert resultado["distancia_km"] > 14.6
    assert 0.4 < resultado["desvio_km"] < 0.8


def test_procurar_fora_do_raio_devolve_none():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"hnm": _par(22, 14.6)})])
    assert tm.procurar(lat + 0.05, lng, "hnm") is None  # ~5.6 km


def test_procurar_nao_atravessa_barreiras():
    """Uma âncora do outro lado de uma barreira da rede não vale: usa a
    geometria REAL da primeira barreira de rede_viagem.json (pontos
    perpendiculares ao seu ponto médio), para não depender de sítios."""
    rede = viagem.carregar_rede()
    (lat_a, lng_a), (lat_b, lng_b) = rede["barreiras"][0]  # segmento preparado
    lat_m, lng_m = (lat_a + lat_b) / 2, (lng_a + lng_b) / 2

    ancora = (lat_m + 0.008, lng_m)   # a norte da crista
    do_outro_lado = (lat_m - 0.008, lng_m)
    do_mesmo_lado = (lat_m + 0.010, lng_m)

    _ativar(
        [_medicao("sintetico/norte", "Norte", ancora[0], ancora[1], {"hnm": _par(15, 8.0)})],
        raio=5.0,
    )
    assert tm.procurar(*do_outro_lado, "hnm") is None
    perto = tm.procurar(*do_mesmo_lado, "hnm")
    assert perto is not None and perto["minutos"] >= 15.0


def test_variavel_de_ambiente_desliga_a_tabela(monkeypatch):
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"hnm": _par(22, 14.6)})])
    monkeypatch.setenv("VIAGEM_TEMPOS_MEDIDOS", "0")
    assert tm.procurar(lat, lng, "hnm") is None


def test_ficheiro_ausente_desliga_sem_erro(monkeypatch, tmp_path):
    monkeypatch.setattr(tm, "FICHEIRO", tmp_path / "nao_existe.json")
    tm._cache = None
    assert tm.carregar(recarregar=True)["ativo"] is False
    assert tm.procurar(32.70, -16.90, "hnm") is None


# --------------------------------------------------------------------- #
# 3a. Integração no estimador                                             #
# --------------------------------------------------------------------- #

def test_estimar_com_destino_id_usa_a_tabela():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    alvo = _unidade("cs_gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"cs_gaula": _par(5, 2.0)})])
    est = viagem.estimar(lat, lng, alvo["lat"], alvo["lng"], destino_id="cs_gaula")
    assert est["metodo"] == "medido"
    assert est["minutos"] == 5
    assert est["distancia_km"] == pytest.approx(2.0)


def test_estimar_sem_destino_id_cai_na_rede():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    alvo = _unidade("cs_gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"cs_gaula": _par(5, 2.0)})])
    est = viagem.estimar(lat, lng, alvo["lat"], alvo["lng"])
    assert est["metodo"] == "rede"


def test_osrm_quando_ligado_ganha_a_tabela(monkeypatch):
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    alvo = _unidade("cs_gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"cs_gaula": _par(5, 2.0)})])
    monkeypatch.setenv(viagem.VARIAVEL_OSRM, "http://osrm.exemplo")
    monkeypatch.setattr(
        viagem, "_pedir_osrm", lambda url: {"code": "Ok", "durations": [[0.0, 540.0]]}
    )
    est = viagem.estimar(lat, lng, alvo["lat"], alvo["lng"], destino_id="cs_gaula")
    assert est["metodo"] == "osrm"
    assert est["minutos"] == 9


def test_osrm_em_falha_recua_para_a_tabela(monkeypatch):
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    alvo = _unidade("cs_gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"cs_gaula": _par(5, 2.0)})])
    monkeypatch.setenv(viagem.VARIAVEL_OSRM, "http://osrm.exemplo")

    def _explode(url):
        raise RuntimeError("osrm em baixo")

    monkeypatch.setattr(viagem, "_pedir_osrm", _explode)
    est = viagem.estimar(lat, lng, alvo["lat"], alvo["lng"], destino_id="cs_gaula")
    assert est["metodo"] == "medido"
    assert est["minutos"] == 5


def test_tempos_para_unidades_mistura_metodos():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar(
        [
            _medicao(
                "santa_cruz/gaula",
                "Gaula",
                lat,
                lng,
                {"cs_gaula": _par(5, 2.0), "cs_camacha": _par(9, 5.5)},
            )
        ]
    )
    lista = [_unidade("cs_gaula"), _unidade("cs_camacha"), _unidade("cs_santa_cruz")]
    tempos = viagem.tempos_para_unidades(lat, lng, lista)
    assert tempos["cs_gaula"]["metodo"] == "medido"
    assert tempos["cs_camacha"]["metodo"] == "medido"
    assert tempos["cs_santa_cruz"]["metodo"] == "rede"


# --------------------------------------------------------------------- #
# 3b. Encaminhamento e API                                                #
# --------------------------------------------------------------------- #

def test_encaminhamento_usa_a_tabela_e_di_lo():
    """Com a tabela preenchida para as unidades plausíveis da zona, o
    principal (seja ele qual for: o encaminhamento decide) tem de vir
    com o método "medido", a distância da tabela e a frase por estrada.
    Não se fixa a unidade vencedora: isso é decisão do routing e dos
    dados, não deste módulo."""
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    tabela = {
        "hnm": (22, 14.6),
        "cs_machico": (13, 9.0),
        "cs_santa_cruz": (11, 6.0),
        "cs_gaula": (5, 2.0),
        "cs_camacha": (9, 5.5),
    }
    _ativar(
        [
            _medicao(
                "santa_cruz/gaula",
                "Gaula",
                lat,
                lng,
                {uid: _par(t, d) for uid, (t, d) in tabela.items()},
            )
        ]
    )
    resposta = cliente.post(
        "/api/encaminhamento", json={"cor": "laranja", "lat": lat, "lng": lng}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    principal = corpo["unidade"]
    assert principal["id"] in tabela
    assert principal["tempo_viagem"]["metodo"] == "medido"
    assert principal["tempo_viagem"]["distancia_km"] == pytest.approx(
        tabela[principal["id"]][1]
    )
    assert corpo["viagem_info"]["metodo"] == "medido"
    assert "km por estrada" in corpo["mensagem"]
    assert "min de carro" in corpo["mensagem"]


def test_api_viagem_com_unidade_devolve_medido():
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar([_medicao("santa_cruz/gaula", "Gaula", lat, lng, {"cs_gaula": _par(5, 2.0)})])
    resposta = cliente.get(
        "/api/viagem", params={"lat": lat, "lng": lng, "unidade": "cs_gaula"}
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["destino"]["unidade"] == "cs_gaula"
    assert corpo["estimativa"]["metodo"] == "medido"
    assert corpo["estimativa"]["distancia_km"] == pytest.approx(2.0)


def test_api_viagem_unidade_desconhecida_da_404():
    resposta = cliente.get(
        "/api/viagem", params={"lat": 32.7, "lng": -16.9, "unidade": "cs_fantasma"}
    )
    assert resposta.status_code == 404


def test_api_viagem_sem_destino_da_422():
    resposta = cliente.get("/api/viagem", params={"lat": 32.7, "lng": -16.9})
    assert resposta.status_code == 422


def test_resposta_com_tabela_continua_sem_travessoes():
    """A política da v0.11.2 (sem travessões em textos visíveis) cobre
    também os textos novos do método medido."""
    lat, lng = _centro_freguesia("santa_cruz", "gaula")
    _ativar(
        [
            _medicao(
                "santa_cruz/gaula",
                "Gaula",
                lat,
                lng,
                {"hnm": _par(22, 14.6), "cs_gaula": _par(5, 2.0)},
            )
        ]
    )
    resposta = cliente.post(
        "/api/encaminhamento", json={"cor": "laranja", "lat": lat, "lng": lng}
    )
    texto = json.dumps(resposta.json(), ensure_ascii=False)
    assert "\u2014" not in texto  # —
    assert "\u2013" not in texto  # –


# --------------------------------------------------------------------- #
# 4. O script de preenchimento automático (motor simulado)                #
# --------------------------------------------------------------------- #

def _falso_motor(segundos=300.0, metros=5000.0, celulas_nulas=()):
    """Motor simulado: devolve matrizes constantes; certas células (linha,
    coluna) podem vir a None, como num par sem rota."""
    chamadas: list[tuple[int, int]] = []

    def pedir(motor, origens, destinos, chave, url):
        chamadas.append((len(origens), len(destinos)))
        duracoes = [[segundos for _ in destinos] for _ in origens]
        distancias = [[metros for _ in destinos] for _ in origens]
        for linha, coluna in celulas_nulas:
            if linha < len(origens) and coluna < len(destinos):
                duracoes[linha][coluna] = None
        return duracoes, distancias

    return pedir, chamadas


def test_calcular_preenche_nulls_e_preserva_o_resto():
    dados = _tabela(
        [
            _medicao("m/a", "A", 32.70, -16.90, {"hnm": _par(), "cs_gaula": _par()}),
            _medicao("m/b", "B", 32.71, -16.91, {"hnm": _par(7, 3.0, fonte="manual")}),
            _medicao("ps/c", "C", 33.06, -16.34, {"cs_porto_santo": _par()}, ilha="porto_santo"),
        ]
    )
    pedir, chamadas = _falso_motor()
    gravados: list[int] = []
    estatisticas = calc.preencher(
        dados, pedir, "ors", lote=5, pausa=0, gravar=lambda d: gravados.append(1)
    )
    assert estatisticas == {"pedidos": 2, "preenchidos": 3, "sem_rota": 0}
    assert len(gravados) == 2  # grava depois de cada lote (retoma barata)
    par = dados["medicoes"][0]["destinos"]["hnm"]
    assert par["tempo_min"] == 5 and par["distancia_km"] == 5.0
    assert par["fonte"] == "ors"
    assert par["calculado_em"] == date.today().isoformat()
    intocado = dados["medicoes"][1]["destinos"]["hnm"]
    assert intocado["tempo_min"] == 7 and intocado["fonte"] == "manual"


def test_calcular_com_forcar_recalcula_tudo():
    dados = _tabela(
        [_medicao("m/b", "B", 32.71, -16.91, {"hnm": _par(7, 3.0, fonte="manual")})]
    )
    pedir, _ = _falso_motor()
    calc.preencher(dados, pedir, "osrm", lote=5, pausa=0, forcar=True)
    par = dados["medicoes"][0]["destinos"]["hnm"]
    assert par["tempo_min"] == 5 and par["fonte"] == "osrm"


def test_calcular_arredonda_com_pisos_e_conta_sem_rota():
    dados = _tabela(
        [_medicao("m/a", "A", 32.70, -16.90, {"hnm": _par(), "cs_gaula": _par()})]
    )
    pedir, _ = _falso_motor(segundos=20.0, metros=40.0, celulas_nulas=[(0, 0)])
    estatisticas = calc.preencher(dados, pedir, "ors", lote=5, pausa=0)
    destinos = dados["medicoes"][0]["destinos"]
    # A união de destinos é ordenada: coluna 0 = cs_gaula (anulada),
    # coluna 1 = hnm. 20 s e 40 m nunca viram "0 min" nem "0.0 km":
    # pisos de 1 min e 0.1 km.
    assert destinos["hnm"]["tempo_min"] == 1
    assert destinos["hnm"]["distancia_km"] == 0.1
    assert destinos["cs_gaula"]["tempo_min"] is None  # célula sem rota
    assert estatisticas["sem_rota"] == 1


def test_calcular_lotes_respeitam_tamanho_e_ilhas():
    medicoes = [
        _medicao(f"m/{i}", f"M{i}", 32.70 + i / 100, -16.90, {"hnm": _par()})
        for i in range(7)
    ] + [
        _medicao("ps/c", "C", 33.06, -16.34, {"cs_porto_santo": _par()}, ilha="porto_santo")
    ]
    pendentes = calc._pendentes(_tabela(medicoes), forcar=False, filtro=None)
    lotes = calc._lotes_por_ilha(pendentes, lote=3)
    assert [len(grupo) for grupo in lotes] == [3, 3, 1, 1]
    for grupo in lotes:
        assert len({m["ilha"] for m, _ in grupo}) == 1


def test_calcular_aplicar_limite_trunca_pelos_pares():
    pendentes = calc._pendentes(
        _tabela(
            [
                _medicao("m/a", "A", 32.70, -16.90, {"hnm": _par(), "cs_gaula": _par()}),
                _medicao("m/b", "B", 32.71, -16.91, {"hnm": _par(), "cs_gaula": _par()}),
            ]
        ),
        forcar=False,
        filtro=None,
    )
    recortado = calc._aplicar_limite(pendentes, 3)
    assert sum(len(uids) for _, uids in recortado) == 3
    assert len(recortado[0][1]) == 2 and len(recortado[1][1]) == 1
