"""Motor de triagem por discriminadores de Manchester (fluxogramas em JSON).

Modelo (v0.14.0): cada queixa é um ficheiro em app/data/rules/ com uma
lista de DISCRIMINADORES, cada um com a sua prioridade clínica (P1-P5) e
a cor de Manchester correspondente (P1 vermelho, P2 laranja, P3 amarelo,
P4 verde, P5 azul). Os discriminadores estão ordenados da prioridade mais
alta para a mais baixa.

O motor percorre-os por essa ordem e faz uma pergunta de sim/não por
discriminador: o PRIMEIRO "sim" decide a cor e termina a triagem. É a
tradução direta da lógica de Manchester: verificar primeiro os
discriminadores das prioridades mais altas.

Se todos forem "não" ("sem discriminador positivo"), o desfecho fica um
nível de prioridade abaixo do discriminador menos urgente do fluxo, sem
passar de azul (P5) - ver _resultado_sem_positivo. Na maioria dos fluxos
(cujo discriminador menos urgente é verde/P4) isto dá azul, como antes;
nos fluxos que só têm discriminadores muito urgentes, evita o salto até
azul, que seria clinicamente estranho.

O motor é *stateless*: o frontend acumula as respostas e reenvia-as todas
em cada pedido; o motor "reproduz" o percurso e devolve ou a próxima
pergunta, ou o resultado final.

Vantagens desta abordagem para o estágio:
- As regras clínicas ficam FORA do código -> um enfermeiro/médico pode
  rever e corrigir os JSON sem tocar em Python.
- Ser stateless simplifica o backend (nada de sessões) e facilita testes.
- O modelo espelha os discriminadores oficiais de Manchester, em vez de
  árvores de decisão inventadas.

O ficheiro especial red_flags.json contém sinais de emergência avaliados
ANTES de qualquer queixa: qualquer um selecionado -> vermelho / 112.

Validação no arranque (importante para quem edita os JSON à mão): o
servidor recusa arrancar se um fluxo tiver ids repetidos, cores ou
prioridades inválidas, cor que não corresponde à prioridade, ou
discriminadores fora da ordem de prioridade. É muito melhor descobrir
isto ao arrancar do que a meio da triagem de um utente. Para verificar
sem arrancar o servidor:
    python scripts/validar_dados.py

A descrição clínica de cada discriminador (campo "descricao", da coluna H
da tabela de Manchester) é mostrada ao utente como ajuda da pergunta,
para perceber o que está a ser perguntado.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

PASTA_REGRAS = Path(__file__).resolve().parent.parent / "data" / "rules"

# Aconselhamento por (fluxo, cor), gerado por scripts/importar_aconselhamento.py
# a partir da tabela de Manchester. É opcional: se o ficheiro não existir, o
# motor continua a funcionar sem aconselhamento (ver _carregar_aconselhamento).
FICHEIRO_ACONSELHAMENTO = Path(__file__).resolve().parent.parent / "data" / "aconselhamento.json"

# Reescritas das perguntas em linguagem do utente, com o estado de validação
# clínica por item (v0.15.3). O motor NÃO precisa deste ficheiro para fazer
# triagem (as perguntas leigas já vivem dentro das regras, e o clínico é o
# recuo); só o portão de produção ONDE_IR_APENAS_VALIDADO o lê, para saber
# QUAIS reescritas já foram validadas (ver _aplicar_portao_perguntas).
FICHEIRO_PERGUNTAS_UTENTE = (
    Path(__file__).resolve().parent.parent / "data" / "perguntas_utente.json"
)

CORES_VALIDAS = {"vermelho", "laranja", "amarelo", "verde", "azul"}

# Prioridade clínica de Manchester -> cor. É a correspondência canónica do
# protocolo (ver app/core/cores.py). O motor VALIDA que a cor de cada
# discriminador coincide com a da sua prioridade, para apanhar enganos.
PRIORIDADES = ("P1", "P2", "P3", "P4", "P5")
COR_DA_PRIORIDADE = {
    "P1": "vermelho",
    "P2": "laranja",
    "P3": "amarelo",
    "P4": "verde",
    "P5": "azul",
}
_RANK_PRIORIDADE = {p: i for i, p in enumerate(PRIORIDADES)}

# Valores aceites no campo opcional "destino" de um discriminador (herdado
# da v0.12.1): só é permitido em discriminadores amarelos (P3) e permite
# que esse desfecho seja encaminhado para o atendimento urgente mais
# próximo, em vez do hospital. A tabela de Manchester não o usa, mas o
# campo continua suportado para regras editadas à mão.
DESTINOS_RESULTADO = ("hospital", "atendimento_urgente")

# Textos (bilingues) do desfecho, construídos a partir da cor e do
# discriminador que ficou positivo. Ficam no código (e não nos JSON) para
# não repetir a mesma frase em milhares de discriminadores.
_MOTIVO_POR_COR = {
    "vermelho": (
        "Está presente um discriminador de prioridade máxima: «{texto}». "
        "Esta situação pode ter risco de vida.",
        "A top-priority discriminator is present: \u201c{texto}\u201d. "
        "This situation may be life-threatening.",
    ),
    "laranja": (
        "Está presente um discriminador muito urgente: «{texto}».",
        "A very urgent discriminator is present: \u201c{texto}\u201d.",
    ),
    "amarelo": (
        "Está presente um discriminador urgente: «{texto}».",
        "An urgent discriminator is present: \u201c{texto}\u201d.",
    ),
    "verde": (
        "Está presente um discriminador pouco urgente: «{texto}».",
        "A less urgent discriminator is present: \u201c{texto}\u201d.",
    ),
}
_MOTIVO_SEM_POSITIVO = (
    "Não foi identificado nenhum discriminador de maior prioridade nesta " "avaliação.",
    "No higher-priority discriminator was identified in this assessment.",
)
_NOTA_VERMELHO = (
    "Ligue já o 112 e siga as instruções do operador. Se possível, não se "
    "desloque pelos próprios meios.",
    "Call 112 now and follow the operator's instructions. If possible, do "
    "not travel by your own means.",
)


class ErroTriagem(ValueError):
    """Erro de utilização do motor (queixa inexistente, resposta inválida...)."""


class TriageEngine:
    def __init__(
        self,
        pasta_regras: Path = PASTA_REGRAS,
        ficheiro_aconselhamento: Path = FICHEIRO_ACONSELHAMENTO,
        ficheiro_perguntas_utente: Path = FICHEIRO_PERGUNTAS_UTENTE,
    ) -> None:
        self.fluxos: dict[str, dict] = {}
        self.red_flags: list[dict] = []
        # aconselhamento[fluxo_id][cor] -> {"itens": [{"texto", "texto_utente"?}]}
        self.aconselhamento: dict[str, dict] = {}
        self._carregar(Path(pasta_regras))
        self._aplicar_portao_perguntas(Path(ficheiro_perguntas_utente))
        self._carregar_aconselhamento(Path(ficheiro_aconselhamento))

    # ------------------------------------------------------------------ #
    # Carregamento e validação                                            #
    # ------------------------------------------------------------------ #

    def _carregar(self, pasta: Path) -> None:
        for caminho in sorted(pasta.glob("*.json")):
            # O erro de SINTAXE é o engano mais provável de quem edita os
            # JSON à mão (uma vírgula a mais, um "}" a menos) — e era o
            # único que escapava às mensagens amigáveis: rebentava com um
            # traceback cru no arranque e com um 500 em /api/fluxogramas
            # (que só apanha RuntimeError). Convertê-lo aqui, com o NOME
            # do ficheiro, alinha-o com as validações abaixo (v0.16.2).
            try:
                dados = json.loads(caminho.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"{caminho.name}: JSON ilegível: {exc}") from exc
            if not isinstance(dados, dict):
                raise RuntimeError(
                    f"{caminho.name}: formato inesperado (esperava um objeto JSON no topo)"
                )
            if dados.get("id") == "red_flags":
                self.red_flags = dados.get("sinais") or []
            else:
                if not dados.get("id"):
                    raise RuntimeError(f"{caminho.name}: fluxo sem 'id' no topo")
                self._validar_fluxo(dados, caminho.name)
                self.fluxos[dados["id"]] = dados

        if not self.fluxos:
            raise RuntimeError(f"Nenhum fluxo de triagem encontrado em {pasta}")
        if not self.red_flags:
            raise RuntimeError("red_flags.json em falta ou sem sinais definidos")

        n_disc = sum(len(f["perguntas"]) for f in self.fluxos.values())
        logger.info(
            "Motor de triagem: %d fluxos e %d discriminadores validados (+ %d red flags)",
            len(self.fluxos),
            n_disc,
            len(self.red_flags),
        )

    def _aplicar_portao_perguntas(self, ficheiro: Path) -> None:
        """Portão de produção das perguntas (v0.15.3).

        Com ONDE_IR_APENAS_VALIDADO=1, as reescritas leigas ainda NÃO
        validadas clinicamente saem das perguntas ANTES de o motor as
        servir: o utente passa a ver a pergunta CLÍNICA oficial (o recuo
        natural de _pergunta_out), que é a fonte validada de Manchester.
        Ao contrário do aconselhamento, aqui nada é escondido — esconder
        uma pergunta mudaria a triagem; troca-se apenas a redação proposta
        pela oficial.

        O estado por item vive só em app/data/perguntas_utente.json (as
        regras não o duplicam, de propósito — ver o cabeçalho de
        scripts/aplicar_perguntas_utente.py). Ficheiro em falta com o
        portão ligado = nenhuma reescrita provada = todas saem (recuo
        seguro, com aviso no log); ficheiro corrompido = erro no arranque,
        como no aconselhamento. Com o portão desligado (omissão), este
        método não lê nada: em desenvolvimento mostra-se tudo, marcado
        como sujeito a validação. Os fluxogramas e o documento de
        validação clínica usam os campos clínicos e não são afetados.
        """
        apenas_validado = os.environ.get("ONDE_IR_APENAS_VALIDADO", "").lower() in (
            "1",
            "true",
            "sim",
        )
        if not apenas_validado:
            return

        validadas: set[str] = set()
        if not ficheiro.exists():
            logger.warning(
                "Portão APENAS-VALIDADO ligado mas %s não existe: todas as "
                "reescritas das perguntas contam como não validadas.",
                ficheiro,
            )
        else:
            try:
                dados = json.loads(ficheiro.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"perguntas_utente.json ilegível: {exc}") from exc
            itens = dados.get("itens") if isinstance(dados, dict) else None
            if not isinstance(itens, dict):
                raise RuntimeError(
                    "perguntas_utente.json com formato inesperado: falta o " "objeto 'itens'."
                )
            # A mesma forma canónica das chaves de texto clínico do resto do
            # projeto (scripts/_manchester_comum.normalizar): espaços
            # colapsados num só. str.split() sem argumentos trata qualquer
            # espaço (incluindo \xa0) — equivalência fixada em testes.
            validadas = {
                " ".join(str(chave).split())
                for chave, item in itens.items()
                if isinstance(item, dict) and item.get("validado")
            }

        revertidas = 0
        for fluxo in self.fluxos.values():
            for disc in fluxo["perguntas"]:
                if not disc.get("texto_utente"):
                    continue
                chave = " ".join(str(disc.get("texto", "")).split())
                if chave not in validadas:
                    disc.pop("texto_utente", None)
                    disc.pop("texto_utente_en", None)
                    revertidas += 1
        logger.info(
            "Perguntas em modo APENAS-VALIDADO: %d reescrita(s) por validar "
            "revertida(s) para a pergunta clínica oficial (%d validadas).",
            revertidas,
            len(validadas),
        )

    def _carregar_aconselhamento(self, ficheiro: Path) -> None:
        """Carrega o aconselhamento por (fluxo, cor), se existir.

        É deliberadamente TOLERANTE: o aconselhamento é um extra e nunca deve
        impedir a triagem de arrancar. Se o ficheiro faltar, apenas se regista
        um aviso e o motor segue sem aconselhamento. Só se levanta erro em caso
        de rutura estrutural real (JSON inválido, ou formato de topo errado),
        para não deixar passar um ficheiro corrompido em silêncio. Chaves
        desconhecidas (fluxo ou cor que o motor não conhece) geram apenas aviso
        e são ignoradas, para que a triagem não parta se a tabela de
        aconselhamento e as regras ficarem temporariamente desalinhadas.
        """
        if not ficheiro.exists():
            logger.warning(
                "Aconselhamento não encontrado (%s); a triagem segue sem ele.",
                ficheiro,
            )
            return

        try:
            dados = json.loads(ficheiro.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"aconselhamento.json ilegível: {exc}") from exc

        if not isinstance(dados, dict) or not isinstance(dados.get("fluxos"), dict):
            raise RuntimeError(
                "aconselhamento.json com formato inesperado: falta o objeto 'fluxos'."
            )

        validado: dict[str, dict] = {}
        n_itens = 0
        for fid, blocos in dados["fluxos"].items():
            if fid not in self.fluxos:
                logger.warning("Aconselhamento para fluxo desconhecido, ignorado: %r", fid)
                continue
            if not isinstance(blocos, dict):
                logger.warning("Aconselhamento de %r ignorado: formato inválido.", fid)
                continue
            por_cor: dict[str, dict] = {}
            for cor, bloco in blocos.items():
                if cor not in CORES_VALIDAS:
                    logger.warning("Aconselhamento com cor inválida em %r, ignorado: %r", fid, cor)
                    continue
                itens = (bloco or {}).get("itens") if isinstance(bloco, dict) else None
                if not isinstance(itens, list) or not itens:
                    continue
                # manter só itens com um 'texto' não vazio
                limpos = [it for it in itens if isinstance(it, dict) and it.get("texto")]
                if limpos:
                    por_cor[cor] = {"itens": limpos}
                    n_itens += len(limpos)
            if por_cor:
                validado[fid] = por_cor

        self.aconselhamento = validado
        # Portão de produção (v0.15.2): com ONDE_IR_APENAS_VALIDADO=1, os
        # itens cuja reescrita ainda NÃO foi validada clinicamente perdem a
        # camada do utente (texto_utente/_en) ANTES de saírem do motor — o
        # utente não os vê em lado nenhum (resultado, encaminhamento, PDF),
        # mas o texto clínico continua a ir para os integradores. Desligado
        # por omissão: em desenvolvimento mostra-se tudo o que tem reescrita,
        # marcado como "sujeito a validação"; em produção liga-se o portão e
        # só passa o que a equipa clínica aprovou item a item (o estado vive
        # em app/data/aconselhamento_utente.json).
        apenas_validado = os.environ.get("ONDE_IR_APENAS_VALIDADO", "").lower() in (
            "1",
            "true",
            "sim",
        )
        ocultados = 0
        if apenas_validado:
            for blocos in validado.values():
                for bloco in blocos.values():
                    for it in bloco["itens"]:
                        if it.get("texto_utente") and not it.get("validado"):
                            it.pop("texto_utente", None)
                            it.pop("texto_utente_en", None)
                            ocultados += 1
        com_utente = sum(
            1
            for blocos in validado.values()
            for bloco in blocos.values()
            for it in bloco["itens"]
            if it.get("texto_utente")
        )
        if apenas_validado:
            logger.info(
                "Aconselhamento em modo APENAS-VALIDADO: %d item(ns) por "
                "validar ocultados ao utente.",
                ocultados,
            )
        logger.info(
            "Aconselhamento: %d fluxos, %d itens (%d com versão de utente).",
            len(validado),
            n_itens,
            com_utente,
        )

    def _aconselhamento_para(self, fluxo_id: str, cor: str) -> dict | None:
        """Devolve {'itens': [...]} para (fluxo, cor), ou None se não houver.

        Os itens trazem sempre 'texto' (conselho clínico, para integradores) e,
        quando existe versão leiga segura, 'texto_utente' (mostrado ao utente).
        A decisão de o que mostrar é do frontend; o motor só entrega os dados.
        """
        bloco = self.aconselhamento.get(fluxo_id, {}).get(cor)
        if not bloco:
            return None
        return {"itens": [dict(it) for it in bloco["itens"]]}

    def _validar_fluxo(self, fluxo: dict, origem: str) -> None:
        perguntas = fluxo.get("perguntas") or []
        if not perguntas:
            raise RuntimeError(f"{origem}: fluxo sem discriminadores")

        ids = [p.get("id") for p in perguntas]
        if None in ids:
            raise RuntimeError(f"{origem}: discriminador sem 'id'")
        if len(ids) != len(set(ids)):
            raise RuntimeError(f"{origem}: ids de discriminador repetidos")

        rank_anterior = -1
        for p in perguntas:
            pid = p["id"]
            if not (p.get("texto") or "").strip():
                raise RuntimeError(f"{origem}: discriminador {pid!r} sem texto")

            prioridade = p.get("prioridade")
            if prioridade not in PRIORIDADES:
                raise RuntimeError(
                    f"{origem}: prioridade inválida {prioridade!r} em {pid!r} "
                    f"(usar {', '.join(PRIORIDADES)})"
                )

            cor = p.get("cor")
            if cor not in CORES_VALIDAS:
                raise RuntimeError(f"{origem}: cor inválida {cor!r} em {pid!r}")
            esperada = COR_DA_PRIORIDADE[prioridade]
            if cor != esperada:
                raise RuntimeError(
                    f"{origem}: {pid!r} tem prioridade {prioridade} mas cor "
                    f"{cor!r} (esperada {esperada!r})"
                )

            # Discriminadores têm de estar ordenados da prioridade mais alta
            # para a mais baixa (P1 antes de P2...). Uma inversão é quase
            # sempre um engano de edição e mudaria a cor atribuída.
            rank = _RANK_PRIORIDADE[prioridade]
            if rank < rank_anterior:
                raise RuntimeError(
                    f"{origem}: discriminador {pid!r} ({prioridade}) aparece "
                    f"depois de uma prioridade mais baixa; ordene de P1 para P5"
                )
            rank_anterior = rank

            # Campo opcional "destino": só em amarelos (P3).
            destino = p.get("destino")
            if destino is not None:
                if destino not in DESTINOS_RESULTADO:
                    raise RuntimeError(
                        f"{origem}: destino inválido {destino!r} em {pid!r} "
                        f"(usar {' ou '.join(repr(d) for d in DESTINOS_RESULTADO)})"
                    )
                if cor != "amarelo":
                    raise RuntimeError(
                        f"{origem}: 'destino' só é permitido em discriminadores "
                        f"amarelos, mas {pid!r} é {cor!r}"
                    )

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
                "pediatrico": bool(f.get("pediatrico", False)),
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
        """Qualquer sinal de emergência selecionado -> vermelho, ligar 112."""
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

    @staticmethod
    def _pergunta_out(disc: dict, respondidas: int, total: int, queixa_id: str) -> dict:
        """Formata um discriminador como a próxima pergunta para o frontend.

        Mostra o texto em linguagem do utente (``texto_utente``), que já
        integra a descrição clínica na própria pergunta. Recua para o texto
        clínico (``texto``) se, por algum motivo, faltar a versão do utente.

        A prioridade e a cor NÃO seguem para o frontend: a cor só deve
        aparecer no resultado final, e não durante as perguntas (v0.14.1).
        Também já não se envia texto de 'ajuda' à parte, porque a descrição
        passou a estar dentro da própria pergunta.
        """
        pergunta = {
            "id": disc["id"],
            "texto": disc.get("texto_utente") or disc["texto"],
        }
        # Tradução opcional; o frontend recua para o PT quando falta.
        texto_en = disc.get("texto_utente_en") or disc.get("texto_en")
        if texto_en:
            pergunta["texto_en"] = texto_en
        return {
            "tipo": "pergunta",
            "queixa": queixa_id,
            "pergunta": pergunta,
            "progresso": {"respondidas": respondidas, "maximo": total},
        }

    @staticmethod
    def _resultado_positivo(disc: dict) -> dict:
        """Desfecho quando um discriminador fica positivo ('sim')."""
        cor = disc["cor"]
        motivo_pt, motivo_en = _MOTIVO_POR_COR[cor]
        # O resultado é mostrado ao utente, por isso usa a linguagem do
        # utente (com recuo para o texto clínico se faltar).
        texto_pt = disc.get("texto_utente") or disc["texto"]
        texto_en = disc.get("texto_utente_en") or disc.get("texto_en", texto_pt)
        resultado = {
            "cor": cor,
            "motivo": motivo_pt.format(texto=texto_pt),
            "motivo_en": motivo_en.format(texto=texto_en),
            "discriminador": texto_pt,
            "prioridade": disc.get("prioridade"),
        }
        if cor == "vermelho":
            resultado["nota"], resultado["nota_en"] = _NOTA_VERMELHO
        # Exceção de encaminhamento herdada (só amarelos): viaja até ao
        # encaminhamento tal e qual.
        if disc.get("destino"):
            resultado["destino"] = disc["destino"]
        return resultado

    @staticmethod
    def _resultado_sem_positivo(discriminadores: list[dict]) -> dict:
        """Desfecho quando nenhum discriminador ficou positivo (todos 'não').

        Regra (v0.14.1): a triagem fica UM nível de prioridade ABAIXO do
        discriminador menos urgente que o fluxo tem, sem nunca ultrapassar
        o azul (P5).

        Porquê: alguns fluxos (sobretudo os de apoio/pedidos) só têm
        discriminadores muito urgentes. Em «Pedido para terceiros», por
        exemplo, o menos urgente é laranja (P2); responder «não» a tudo dava
        antes azul (P5), um salto de três níveis que não faz sentido clínico
        para um pedido destes. Com esta regra, esse fluxo termina em amarelo
        (P3). Nos fluxos habituais, cujo discriminador menos urgente é verde
        (P4), o desfecho continua a ser azul (P5), tal como antes.
        """
        idx_mais_baixo = max(_RANK_PRIORIDADE[d["prioridade"]] for d in discriminadores)
        idx_desfecho = min(idx_mais_baixo + 1, len(PRIORIDADES) - 1)
        prioridade = PRIORIDADES[idx_desfecho]
        cor = COR_DA_PRIORIDADE[prioridade]
        motivo_pt, motivo_en = _MOTIVO_SEM_POSITIVO
        return {
            "cor": cor,
            "motivo": motivo_pt,
            "motivo_en": motivo_en,
            "prioridade": prioridade,
        }

    def avaliar(self, queixa_id: str, respostas: dict[str, str]) -> dict:
        """Reproduz o fluxo com as respostas dadas.

        Devolve:
          {"tipo": "pergunta", "pergunta": {...}, "progresso": {...}}
          ou
          {"tipo": "resultado", "resultado": {"cor": ..., "motivo": ..., ...}}
        """
        fluxo = self.fluxos.get(queixa_id)
        if fluxo is None:
            raise ErroTriagem(f"Queixa desconhecida: {queixa_id!r}")

        discriminadores = fluxo["perguntas"]
        total = len(discriminadores)
        respondidas = 0

        for disc in discriminadores:
            resposta = respostas.get(disc["id"])
            if resposta is None:
                # Primeiro discriminador ainda sem resposta -> é a próxima
                # pergunta a fazer.
                return self._pergunta_out(disc, respondidas, total, queixa_id)

            if resposta not in ("sim", "nao"):
                raise ErroTriagem(f"Resposta inválida para {disc['id']!r}: {resposta!r}")

            respondidas += 1
            if resposta == "sim":
                resultado = self._resultado_positivo(disc)
                resultado["aconselhamento"] = self._aconselhamento_para(queixa_id, resultado["cor"])
                return {
                    "tipo": "resultado",
                    "queixa": queixa_id,
                    "resultado": resultado,
                }

        # Todos os discriminadores tiveram resposta "não": desfecho um nível
        # abaixo do discriminador menos urgente do fluxo (ver método).
        resultado = self._resultado_sem_positivo(discriminadores)
        resultado["aconselhamento"] = self._aconselhamento_para(queixa_id, resultado["cor"])
        return {
            "tipo": "resultado",
            "queixa": queixa_id,
            "resultado": resultado,
        }
