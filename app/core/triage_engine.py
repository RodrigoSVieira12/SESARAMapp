"""Motor de triagem baseado em regras (fluxogramas em JSON).

Cada queixa é um ficheiro em app/data/rules/, com perguntas de sim/não
encadeadas. O motor é *stateless*: o frontend acumula as respostas e
reenvia-as todas em cada pedido; o motor "reproduz" o percurso e devolve
ou a próxima pergunta, ou o resultado final.

Vantagens desta abordagem para o estágio:
- As regras clínicas ficam FORA do código → um enfermeiro/médico pode
  rever e corrigir os JSON sem tocar em Python.
- Ser stateless simplifica o backend (nada de sessões) e facilita testes.

O ficheiro especial red_flags.json contém sinais de emergência avaliados
ANTES de qualquer queixa: qualquer um selecionado → vermelho / 112.

Validação no arranque (importante para quem edita os JSON à mão):
o servidor recusa arrancar se um fluxo tiver ids repetidos, ramos em
falta, cores inválidas, referências a perguntas inexistentes, CICLOS
(perguntas que se apontam em círculo) ou perguntas INALCANÇÁVEIS a
partir da primeira. É muito melhor descobrir isto ao arrancar do que a
meio da triagem de um utente. Para verificar sem arrancar o servidor:
    python scripts/validar_dados.py
"""

from __future__ import annotations

import json
from pathlib import Path

PASTA_REGRAS = Path(__file__).resolve().parent.parent / "data" / "rules"

CORES_VALIDAS = {"vermelho", "laranja", "amarelo", "verde", "azul"}


class ErroTriagem(ValueError):
    """Erro de utilização do motor (queixa inexistente, resposta inválida...)."""


class TriageEngine:
    def __init__(self, pasta_regras: Path = PASTA_REGRAS) -> None:
        self.fluxos: dict[str, dict] = {}
        self.red_flags: list[dict] = []
        self._carregar(Path(pasta_regras))

    # ------------------------------------------------------------------ #
    # Carregamento e validação                                            #
    # ------------------------------------------------------------------ #

    def _carregar(self, pasta: Path) -> None:
        for caminho in sorted(pasta.glob("*.json")):
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            if dados.get("id") == "red_flags":
                self.red_flags = dados["sinais"]
            else:
                self._validar_fluxo(dados, caminho.name)
                self.fluxos[dados["id"]] = dados

        if not self.fluxos:
            raise RuntimeError(f"Nenhum fluxo de triagem encontrado em {pasta}")
        if not self.red_flags:
            raise RuntimeError("red_flags.json em falta ou sem sinais definidos")

    def _validar_fluxo(self, fluxo: dict, origem: str) -> None:
        perguntas = fluxo.get("perguntas") or []
        if not perguntas:
            raise RuntimeError(f"{origem}: fluxo sem perguntas")

        ids = [p["id"] for p in perguntas]
        if len(ids) != len(set(ids)):
            raise RuntimeError(f"{origem}: ids de pergunta repetidos")
        conhecidos = set(ids)

        # 1) Cada ramo aponta para um resultado válido ou pergunta existente.
        #    De caminho, construímos o grafo pergunta → perguntas seguintes.
        destinos: dict[str, list[str]] = {i: [] for i in ids}
        for pergunta in perguntas:
            fase = pergunta.get("fase")
            if fase is not None and fase not in (1, 2, 3):
                raise RuntimeError(
                    f"{origem}: fase invalida {fase!r} em {pergunta['id']!r} "
                    f"(usar 1, 2 ou 3)"
                )
            for nome_ramo in ("sim", "nao"):
                ramo = pergunta.get(nome_ramo)
                if ramo is None:
                    raise RuntimeError(
                        f"{origem}: pergunta {pergunta['id']!r} sem ramo {nome_ramo!r}"
                    )
                if "resultado" in ramo:
                    cor = ramo["resultado"].get("cor")
                    if cor not in CORES_VALIDAS:
                        raise RuntimeError(
                            f"{origem}: cor inválida {cor!r} em {pergunta['id']!r}"
                        )
                elif ramo.get("proxima") in conhecidos:
                    destinos[pergunta["id"]].append(ramo["proxima"])
                else:
                    raise RuntimeError(
                        f"{origem}: {pergunta['id']!r} aponta para pergunta "
                        f"inexistente {ramo.get('proxima')!r}"
                    )

        # 2) Todas as perguntas têm de ser alcançáveis a partir da primeira
        #    (uma pergunta "solta" é quase sempre um engano de edição).
        alcancaveis: set[str] = set()
        pilha = [perguntas[0]["id"]]
        while pilha:
            atual = pilha.pop()
            if atual in alcancaveis:
                continue
            alcancaveis.add(atual)
            pilha.extend(destinos[atual])
        soltas = sorted(conhecidos - alcancaveis)
        if soltas:
            raise RuntimeError(
                f"{origem}: perguntas inalcançáveis a partir da primeira: {soltas}"
            )

        # 3) O encadeamento não pode ter ciclos (perguntas em círculo
        #    deixariam o utente preso para sempre).
        estado_no = {i: 0 for i in ids}  # 0 = por visitar, 1 = em curso, 2 = concluído
        for raiz in ids:
            if estado_no[raiz]:
                continue
            pilha_dfs = [(raiz, iter(destinos[raiz]))]
            estado_no[raiz] = 1
            while pilha_dfs:
                no, filhos = pilha_dfs[-1]
                for filho in filhos:
                    if estado_no[filho] == 1:
                        raise RuntimeError(
                            f"{origem}: ciclo detetado no encadeamento das "
                            f"perguntas (envolve {filho!r})"
                        )
                    if estado_no[filho] == 0:
                        estado_no[filho] = 1
                        pilha_dfs.append((filho, iter(destinos[filho])))
                        break
                else:
                    estado_no[no] = 2
                    pilha_dfs.pop()

    # ------------------------------------------------------------------ #
    # Consultas                                                            #
    # ------------------------------------------------------------------ #

    def listar_queixas(self) -> list[dict]:
        saida = []
        for f in self.fluxos.values():
            item = {
                "id": f["id"],
                "nome": f["nome"],
                "descricao": f.get("descricao", ""),
            }
            # Tradução opcional (inglês), com o português como omissão.
            for extra in ("nome_en", "descricao_en"):
                if f.get(extra):
                    item[extra] = f[extra]
            saida.append(item)
        return saida

    def listar_red_flags(self) -> list[dict]:
        return self.red_flags

    # ------------------------------------------------------------------ #
    # Avaliação                                                            #
    # ------------------------------------------------------------------ #

    def resultado_red_flags(self, selecionados: list[str]) -> dict:
        """Qualquer sinal de emergência selecionado → vermelho, ligar 112."""
        ids_validos = {s["id"] for s in self.red_flags}
        reconhecidos = [s for s in selecionados if s in ids_validos]
        if not reconhecidos:
            raise ErroTriagem("Nenhum sinal de emergência reconhecido.")

        textos = [s["texto"] for s in self.red_flags if s["id"] in reconhecidos]
        return {
            "cor": "vermelho",
            "motivo": "Sinais de emergência identificados: " + "; ".join(textos) + ".",
            "nota": (
                "Ligue já o 112 e siga as instruções do operador. "
                "Se possível, não se desloque pelos próprios meios."
            ),
        }

    def avaliar(self, queixa_id: str, respostas: dict[str, str]) -> dict:
        """Reproduz o fluxo com as respostas dadas.

        Devolve:
          {"tipo": "pergunta", "pergunta": {...}, "progresso": {...}}
          ou
          {"tipo": "resultado", "resultado": {"cor": ..., "motivo": ..., "nota": ...}}
        """
        fluxo = self.fluxos.get(queixa_id)
        if fluxo is None:
            raise ErroTriagem(f"Queixa desconhecida: {queixa_id!r}")

        por_id = {p["id"]: p for p in fluxo["perguntas"]}
        atual = fluxo["perguntas"][0]
        respondidas = 0
        visitadas: set[str] = set()

        while True:
            if atual["id"] in visitadas:
                # Rede de segurança em runtime; com a validação de ciclos no
                # arranque, isto não deve acontecer nunca.
                raise ErroTriagem(f"Ciclo detetado no fluxo {queixa_id!r}")
            visitadas.add(atual["id"])

            resposta = respostas.get(atual["id"])
            if resposta is None:
                pergunta_out = {
                    "id": atual["id"],
                    "texto": atual["texto"],
                    "fase": atual.get("fase", 2),
                }
                if "ajuda" in atual:
                    pergunta_out["ajuda"] = atual["ajuda"]
                # Tradução opcional (inglês): passa tal e qual se existir
                # no ficheiro de regras; o frontend usa o português quando
                # o campo falta.
                for extra in ("texto_en", "ajuda_en"):
                    if extra in atual:
                        pergunta_out[extra] = atual[extra]
                return {
                    "tipo": "pergunta",
                    "queixa": queixa_id,
                    "pergunta": pergunta_out,
                    "progresso": {
                        "respondidas": respondidas,
                        "maximo": len(fluxo["perguntas"]),
                    },
                }

            if resposta not in ("sim", "nao"):
                raise ErroTriagem(
                    f"Resposta inválida para {atual['id']!r}: {resposta!r}"
                )

            respondidas += 1
            ramo = atual[resposta]
            if "resultado" in ramo:
                resultado = dict(ramo["resultado"])
                resultado.setdefault("motivo", None)
                resultado.setdefault("nota", None)
                return {
                    "tipo": "resultado",
                    "queixa": queixa_id,
                    "resultado": resultado,
                }
            atual = por_id[ramo["proxima"]]
