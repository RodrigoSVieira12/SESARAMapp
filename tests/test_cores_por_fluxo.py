"""Garante que cada fluxo consegue realmente produzir várias cores.

Este teste percorre estaticamente todos os ramos de cada fluxograma e
recolhe as cores atingíveis. Assim, se alguém editar as regras e deixar
um fluxo a dar quase sempre a mesma cor, o teste falha e avisa.
"""

from app.core.triage_engine import TriageEngine

engine = TriageEngine()


def cores_atingiveis(fluxo: dict) -> set[str]:
    por_id = {p["id"]: p for p in fluxo["perguntas"]}
    cores: set[str] = set()

    def visitar(pergunta_id: str) -> None:
        pergunta = por_id[pergunta_id]
        for nome_ramo in ("sim", "nao"):
            ramo = pergunta[nome_ramo]
            if "resultado" in ramo:
                cores.add(ramo["resultado"]["cor"])
            else:
                visitar(ramo["proxima"])

    visitar(fluxo["perguntas"][0]["id"])
    return cores


def test_cada_fluxo_atinge_pelo_menos_tres_cores():
    for fluxo in engine.fluxos.values():
        cores = cores_atingiveis(fluxo)
        assert len(cores) >= 3, (
            f"O fluxo {fluxo['id']!r} só atinge {sorted(cores)}; "
            f"devia oferecer pelo menos 3 cores diferentes."
        )


def test_todas_as_cinco_cores_existem_no_conjunto():
    todas: set[str] = set()
    for fluxo in engine.fluxos.values():
        todas |= cores_atingiveis(fluxo)
    assert todas == {"vermelho", "laranja", "amarelo", "verde", "azul"}


def test_cada_fluxo_tem_profundidade_suficiente():
    for fluxo in engine.fluxos.values():
        assert len(fluxo["perguntas"]) >= 10, (
            f"O fluxo {fluxo['id']!r} tem só {len(fluxo['perguntas'])} "
            f"perguntas; o objetivo são fluxos detalhados (10 ou mais)."
        )
