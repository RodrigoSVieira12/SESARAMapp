#!/usr/bin/env python3
"""Verificador dos ficheiros de dados, para usar depois de editar os JSON.

Não é preciso saber programar: basta correr, a partir da pasta do projeto,

    python scripts/validar_dados.py

O script verifica:
  1. As regras de triagem (app/data/rules/): estrutura, cores, ramos,
     referências, ciclos e perguntas inalcançáveis.
  2. As unidades (app/data/unidades.json): campos obrigatórios, ids
     únicos, coordenadas dentro da RAM, serviços conhecidos e formato
     dos horários — incluindo alertas para horários de fim de semana
     suspeitos e a regra dos feriados (fechado por omissão).

No fim, lista as unidades que ainda têm dados por confirmar, útil como
checklist do trabalho de levantamento.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core.horarios import DIAS  # noqa: E402
from app.core.triage_engine import TriageEngine  # noqa: E402

CAMINHO_UNIDADES = RAIZ / "app" / "data" / "unidades.json"

SERVICOS_CONHECIDOS = {
    "urgencia_polivalente",
    "urgencia_basica",
    "atendimento_urgente",
    "consulta_aberta",
}
TIPOS_CONHECIDOS = {"hospital", "centro_saude"}

# Caixa aproximada que engloba a Madeira, o Porto Santo e as Desertas.
LAT_MIN, LAT_MAX = 32.3, 33.3
LNG_MIN, LNG_MAX = -17.5, -16.0

PADRAO_FAIXA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


def _minutos(hhmm: str) -> int:
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def validar_regras() -> list[str]:
    """O motor já valida tudo ao carregar: aproveitamos isso."""
    try:
        motor = TriageEngine()
    except Exception as erro:  # noqa: BLE001, queremos mostrar qualquer erro
        return [str(erro)]
    print(f"  OK: {len(motor.fluxos)} fluxos de queixas carregados sem erros")
    print(f"  OK: {len(motor.red_flags)} sinais de emergência (red flags)")
    return []


def _validar_horario(
    prefixo: str, horario: dict, erros: list[str], avisos: list[str]
) -> None:
    tipo = horario.get("tipo")
    if tipo == "24h":
        return
    if tipo != "semanal":
        erros.append(f"{prefixo}: tipo de horário desconhecido {tipo!r} "
                     f"(use \"24h\" ou \"semanal\")")
        return
    horas = horario.get("horas", {})
    dias_validos = DIAS + ["feriado"]

    # Fim de semana igual à segunda-feira: quase sempre copy-paste.
    # (Se for mesmo verdade, ignora o aviso — é só um alerta.)
    seg = horas.get("seg", [])
    for dia_fds in ("sab", "dom"):
        if seg and horas.get(dia_fds) == seg:
            avisos.append(
                f"{prefixo}: o horário de {dia_fds!r} é igual ao de segunda "
                f"({seg}); confirmar se abre mesmo ao fim de semana"
            )
    for dia_fds in ("sab", "dom"):
        if dia_fds not in horas:
            avisos.append(
                f"{prefixo}: sem chave {dia_fds!r}; assume-se FECHADO nesse "
                f"dia. Para ficar explícito, acrescenta \"{dia_fds}\": []"
            )

    for dia, faixas in horas.items():
        if dia not in dias_validos:
            erros.append(f"{prefixo}: dia inválido {dia!r} (use {dias_validos})")
            continue
        for faixa in faixas:
            if "\u2013" in faixa or "\u2014" in faixa:
                erros.append(f"{prefixo}: a faixa {faixa!r} usa um travessao "
                             f"tipografico; escreva com o traco simples do "
                             f"teclado, por exemplo 08:30-17:00")
                continue
            if not PADRAO_FAIXA.match(faixa):
                erros.append(f"{prefixo}: faixa {faixa!r} não está no formato "
                             f"HH:MM-HH:MM")
                continue
            inicio, fim = faixa.split("-")
            if _minutos(inicio) >= _minutos(fim):
                erros.append(f"{prefixo}: faixa {faixa!r} tem início depois do "
                             f"fim (faixas não podem atravessar a meia-noite; "
                             f"use ...-23:59)")


def validar_unidades() -> tuple[list[str], list[str], list[str]]:
    erros: list[str] = []
    avisos: list[str] = []
    por_confirmar: list[str] = []

    try:
        unidades = json.loads(CAMINHO_UNIDADES.read_text(encoding="utf-8"))
    except Exception as erro:  # noqa: BLE001
        return [f"unidades.json não é JSON válido: {erro}"], [], []

    ids_vistos: set[str] = set()
    for i, u in enumerate(unidades):
        nome = u.get("nome") or f"(unidade na posição {i})"
        prefixo = f"unidades.json → {nome}"

        for campo in ("id", "nome", "tipo", "concelho", "ilha", "lat", "lng", "servicos"):
            if campo not in u:
                erros.append(f"{prefixo}: falta o campo obrigatório {campo!r}")

        uid = u.get("id")
        if uid in ids_vistos:
            erros.append(f"{prefixo}: id repetido {uid!r}")
        if uid:
            ids_vistos.add(uid)

        if u.get("ilha") not in ("madeira", "porto_santo"):
            erros.append(f"{prefixo}: ilha {u.get('ilha')!r} invalida "
                         f"(usar \"madeira\" ou \"porto_santo\")")

        if u.get("tipo") not in TIPOS_CONHECIDOS:
            erros.append(f"{prefixo}: tipo {u.get('tipo')!r} desconhecido "
                         f"(use {sorted(TIPOS_CONHECIDOS)})")

        lat, lng = u.get("lat"), u.get("lng")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            if not (LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX):
                erros.append(f"{prefixo}: coordenadas ({lat}, {lng}) fora da "
                             f"RAM. Copie-as do Google Maps com o botão "
                             f"direito sobre o local")
        else:
            erros.append(f"{prefixo}: lat/lng têm de ser números")

        for nome_servico, horario in (u.get("servicos") or {}).items():
            if nome_servico not in SERVICOS_CONHECIDOS:
                avisos.append(f"{prefixo}: serviço {nome_servico!r} não é usado "
                              f"pelo encaminhamento (conhecidos: "
                              f"{sorted(SERVICOS_CONHECIDOS)})")
            if not horario.get("texto"):
                avisos.append(f"{prefixo}: o serviço {nome_servico!r} não tem "
                              f"\"texto\" (é o que o utente vê)")
            _validar_horario(f"{prefixo}, {nome_servico}", horario, erros, avisos)

        confirmada = bool(u.get("dados_confirmados"))
        tem_marcas = "(CONFIRMAR)" in json.dumps(u, ensure_ascii=False)
        if not confirmada or tem_marcas:
            por_confirmar.append(nome)

    # Coordenadas exatamente iguais em unidades diferentes: quase sempre
    # copia e cola por engano.
    vistos: dict[tuple, str] = {}
    for u in unidades:
        chave = (u.get("lat"), u.get("lng"))
        if chave in vistos:
            avisos.append(f"unidades.json: {u.get('nome')} tem coordenadas "
                          f"exatamente iguais a {vistos[chave]}; confirmar "
                          f"qual esta errada")
        else:
            vistos[chave] = u.get("nome")

    # Unidade sem nenhuma vizinha a menos de 10 km (na mesma ilha): na
    # densidade da Madeira, e sinal de coordenadas provavelmente erradas.
    from app.core.geo import haversine_km
    for u in unidades:
        vizinhas = [
            haversine_km(u["lat"], u["lng"], v["lat"], v["lng"])
            for v in unidades
            if v is not u and v.get("ilha") == u.get("ilha")
        ]
        if vizinhas and min(vizinhas) > 10:
            avisos.append(f"unidades.json: {u.get('nome')} esta a mais de "
                          f"10 km de qualquer outra unidade; verificar as "
                          f"coordenadas no Google Maps")

    if not erros:
        print(f"  OK: {len(unidades)} unidades com estrutura válida")
    return erros, avisos, por_confirmar


def validar_autocuidado() -> list[str]:
    """app/data/autocuidado.json: cores válidas e listas bem formadas."""
    erros: list[str] = []
    caminho = RAIZ / "app" / "data" / "autocuidado.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))["cores"]
    except Exception as exc:  # noqa: BLE001 — mensagem legível para quem edita
        return [f"autocuidado.json: não consegui ler o ficheiro ({exc})"]

    cores_validas = {"vermelho", "laranja", "amarelo", "verde", "azul"}
    obrigatorios = ("titulo", "intro", "fazer", "alerta_titulo", "alerta")
    for cor, bloco in dados.items():
        prefixo = f"autocuidado.json ({cor})"
        if cor not in cores_validas:
            erros.append(f"{prefixo}: cor desconhecida (use {sorted(cores_validas)})")
        for campo in obrigatorios:
            if campo not in bloco:
                erros.append(f"{prefixo}: falta o campo obrigatório {campo!r}")
        for lista in ("fazer", "evitar", "alerta"):
            if lista in bloco and not isinstance(bloco[lista], list):
                erros.append(f"{prefixo}: {lista!r} tem de ser uma LISTA de frases")
        for base in ("fazer", "evitar", "alerta"):
            pt, en = bloco.get(base), bloco.get(f"{base}_en")
            if isinstance(pt, list) and isinstance(en, list) and len(pt) != len(en):
                erros.append(f"{prefixo}: {base!r} tem {len(pt)} itens mas "
                             f"{base}_en tem {len(en)} — devem corresponder um a um")
    return erros


def validar_sinonimos() -> tuple[list[str], list[str]]:
    """app/data/sinonimos.json: cada chave tem de ser uma queixa que existe."""
    erros: list[str] = []
    avisos: list[str] = []
    caminho = RAIZ / "app" / "data" / "sinonimos.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))["sinonimos"]
    except Exception as exc:  # noqa: BLE001
        return [f"sinonimos.json: não consegui ler o ficheiro ({exc})"], []

    ids_fluxos = set(TriageEngine().fluxos)
    for queixa_id, termos in dados.items():
        if queixa_id not in ids_fluxos:
            erros.append(f"sinonimos.json: {queixa_id!r} não corresponde a nenhum "
                         f"fluxo em app/data/rules/ (existem: {sorted(ids_fluxos)})")
        if not isinstance(termos, list) or not termos:
            erros.append(f"sinonimos.json ({queixa_id}): o valor tem de ser uma "
                         "lista de palavras/expressões")
    for queixa_id in sorted(ids_fluxos - set(dados)):
        avisos.append(f"sinonimos.json: a queixa {queixa_id!r} não tem sinónimos — "
                      "a pesquisa em texto livre só a encontra pelo nome")
    return erros, avisos


def validar_espera_nomes() -> list[str]:
    """Confirma que cada id em espera_nomes.json existe em unidades.json."""
    caminho = RAIZ / "app" / "data" / "espera_nomes.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []  # ficheiro opcional
    except Exception as exc:  # noqa: BLE001
        return [f"espera_nomes.json: não consegui ler o ficheiro ({exc})"]

    ids_unidades = {u["id"] for u in json.loads(CAMINHO_UNIDADES.read_text(encoding="utf-8"))}
    erros = []
    for nome_site, unidade_id in dados.get("nomes", {}).items():
        if unidade_id not in ids_unidades:
            erros.append(
                f"espera_nomes.json: {nome_site!r} aponta para {unidade_id!r}, "
                "que não existe em unidades.json"
            )
    return erros


def validar_rede_viagem() -> tuple[list[str], list[str]]:
    """app/data/rede_viagem.json: estrutura, ilhas, conetividade — e um
    aviso de cobertura (unidade longe de qualquer nó da rede indica que
    falta um ponto de referência nessa zona)."""
    from app.core import viagem
    from app.core.geo import haversine_km

    try:
        dados = json.loads(viagem.FICHEIRO_REDE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"rede_viagem.json: não consegui ler o ficheiro ({exc})"], []

    erros = [f"rede_viagem.json: {p}" for p in viagem.validar_rede(dados)]
    avisos: list[str] = []

    if not erros:
        unidades = json.loads(CAMINHO_UNIDADES.read_text(encoding="utf-8"))
        for u in unidades:
            distancias = [
                haversine_km(u["lat"], u["lng"], no["lat"], no["lng"])
                for no in dados["nos"]
                if no.get("ilha") == u.get("ilha")
            ]
            if distancias and min(distancias) > 12:
                avisos.append(
                    f"rede_viagem.json: {u.get('nome')} está a mais de 12 km de "
                    f"qualquer nó da rede na sua ilha — considerar acrescentar "
                    f"um ponto de referência nessa zona"
                )
        print(
            f"  OK: rede de viagem com {len(dados['nos'])} nós, "
            f"{len(dados['ligacoes'])} ligações e "
            f"{len(dados.get('barreiras', []))} barreiras"
        )
    return erros, avisos


def validar_localidades() -> tuple[list[str], list[str]]:
    """app/data/localidades.json: estrutura, limites por ilha e suspeitas.

    Os erros impedem o arranque (o módulo valida o mesmo no import); os
    avisos são para olhos humanos: sítios demasiado longe do centro do
    concelho, quase-duplicados, freguesias por confirmar. Também cruza
    os nomes de concelho com os das unidades — uma grafia diferente não
    parte nada, mas denuncia um engano.
    """
    from app.core import localidades

    try:
        dados = json.loads(localidades.FICHEIRO.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"localidades.json: não consegui ler o ficheiro ({exc})"], []

    erros = [f"localidades.json: {p}" for p in localidades.validar(dados)]
    avisos: list[str] = []

    if not erros:
        prep = localidades.carregar(recarregar=True)
        avisos.extend(f"localidades.json: {a}" for a in localidades.avisos(prep))

        unidades = json.loads(CAMINHO_UNIDADES.read_text(encoding="utf-8"))
        nomes_localidades = {c["nome"] for c in prep["concelhos"]}
        nomes_unidades = {u.get("concelho") for u in unidades}
        for nome in sorted(nomes_unidades - nomes_localidades):
            avisos.append(
                f"localidades.json: o concelho '{nome}' aparece em unidades.json "
                f"mas não nas localidades — grafias diferentes?"
            )
        for nome in sorted(nomes_localidades - nomes_unidades):
            avisos.append(
                f"localidades.json: o concelho '{nome}' não tem nenhuma unidade "
                f"em unidades.json — confirmar a grafia"
            )

        n_freg = sum(len(c["freguesias"]) for c in prep["concelhos"])
        n_sitios = sum(len(f["sitios"]) for c in prep["concelhos"] for f in c["freguesias"])
        print(
            f"  OK: {len(prep['concelhos'])} concelhos, {n_freg} freguesias "
            f"e {n_sitios} sítios para o modo manual de localização"
        )
    return erros, avisos


def validar_tempos_medidos() -> tuple[list[str], list[str]]:
    """app/data/tempos_medidos.json: a tabela AMOVÍVEL de tempos por estrada.

    Ficheiro ausente não é erro (o módulo é um paliativo que se remove
    apagando o ficheiro); presente, valida-se com o próprio módulo:
    origens únicas, destinos existentes e na mesma ilha, valores dentro
    de limites de sanidade. Os avisos incluem o progresso do
    preenchimento e os pares com distância mas sem tempo.
    """
    from app.core import tempos_medidos

    if not tempos_medidos.FICHEIRO.exists():
        print(
            "  OK: sem tempos_medidos.json (funcionalidade desligada; para a "
            "criar, correr scripts/atualizar_tempos_medidos.py)"
        )
        return [], []
    try:
        dados = json.loads(tempos_medidos.FICHEIRO.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"tempos_medidos.json: não consegui ler o ficheiro ({exc})"], []

    erros = [f"tempos_medidos.json: {p}" for p in tempos_medidos.validar(dados)]
    avisos: list[str] = []
    if not erros:
        avisos = [f"tempos_medidos.json: {a}" for a in tempos_medidos.avisos(dados)]
        n_origens = len(dados.get("medicoes", []))
        n_pares = sum(len(m.get("destinos") or {}) for m in dados.get("medicoes", []))
        print(
            f"  OK: tempos por estrada com {n_origens} origens e "
            f"{n_pares} pares origem/destino"
        )
    return erros, avisos


def main() -> int:
    print("A verificar as regras de triagem (app/data/rules/)…")
    erros = validar_regras()

    print("A verificar as unidades (app/data/unidades.json)…")
    erros_unidades, avisos, por_confirmar = validar_unidades()
    erros.extend(erros_unidades)

    print("A verificar a rede de tempos de viagem (app/data/rede_viagem.json)…")
    erros_rede, avisos_rede = validar_rede_viagem()
    erros.extend(erros_rede)
    avisos.extend(avisos_rede)

    print("A verificar as localidades (app/data/localidades.json)…")
    erros_loc, avisos_loc = validar_localidades()
    erros.extend(erros_loc)
    avisos.extend(avisos_loc)

    print("A verificar os tempos por estrada (app/data/tempos_medidos.json)…")
    erros_tm, avisos_tm = validar_tempos_medidos()
    erros.extend(erros_tm)
    avisos.extend(avisos_tm)

    print("A verificar os textos de autocuidado (app/data/autocuidado.json)…")
    erros.extend(validar_autocuidado())

    print("A verificar os sinónimos da pesquisa (app/data/sinonimos.json)…")
    erros_sin, avisos_sin = validar_sinonimos()
    erros.extend(erros_sin)
    avisos.extend(avisos_sin)

    print("A verificar os nomes de tempo de espera (app/data/espera_nomes.json)…")
    erros.extend(validar_espera_nomes())

    if avisos:
        print("\nAvisos (não impedem o funcionamento):")
        for aviso in avisos:
            print(f"  AVISO: {aviso}")

    if por_confirmar:
        print(f"\nUnidades com dados ainda por confirmar ({len(por_confirmar)}):")
        for nome in por_confirmar:
            print(f"    {nome}")
        print("  (Quando confirmares uma, remove os \"(CONFIRMAR)\" e muda "
              "\"dados_confirmados\" para true.)")

    if erros:
        print("\nERROS a corrigir antes de arrancar o servidor:")
        for erro in erros:
            print(f"  ERRO: {erro}")
        return 1

    print("\nNota sobre feriados: nos feriados nacionais e regionais da RAM")
    print("(ver GET /api/feriados) os horários \"semanal\" contam como FECHADOS,")
    print("salvo se o serviço tiver a chave \"feriado\" com faixas próprias.")

    print("\nTudo certo. Podes arrancar o servidor com confiança.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
