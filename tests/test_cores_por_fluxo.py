"""Garante que cada fluxo consegue realmente produzir várias cores.

No modelo por discriminadores (v0.14.0), as cores atingíveis de um fluxo
são as cores dos seus discriminadores mais o azul (o desfecho quando
nenhum discriminador fica positivo). Assim, se alguém editar as regras e
deixar um fluxo preso a uma só prioridade, o teste avisa.
"""

from app.core.triage_engine import TriageEngine

engine = TriageEngine()


def cores_atingiveis(fluxo: dict) -> set[str]:
    cores = {p["cor"] for p in fluxo["perguntas"]}
    cores.add("azul")  # desfecho "sem discriminador positivo"
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


def test_cada_fluxo_tem_discriminadores_suficientes():
    # A tabela de Manchester tem fluxos ricos (a maioria com 16 a 32
    # discriminadores); só os dois fluxos administrativos ("pedido de
    # medicação" e "pedido para terceiros") são curtos, com 4 cada.
    for fluxo in engine.fluxos.values():
        assert len(fluxo["perguntas"]) >= 4, (
            f"O fluxo {fluxo['id']!r} tem só {len(fluxo['perguntas'])} " f"discriminadores."
        )


def test_grande_maioria_dos_fluxos_e_detalhada():
    detalhados = sum(1 for f in engine.fluxos.values() if len(f["perguntas"]) >= 10)
    assert detalhados >= len(engine.fluxos) - 2  # só os 2 administrativos ficam de fora
