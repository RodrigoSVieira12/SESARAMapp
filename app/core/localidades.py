"""Localidades da RAM: concelho → freguesia → sítio (v0.11.1).

Para que serve
--------------
Quando a localização automática falha (ou o utente vê que está errada),
a app deixava escolher apenas o CONCELHO — e "concelho" é grosseiro
demais: alguém na Camacha ou no Caniço que escolhe "Santa Cruz" fica com
as coordenadas da vila, a vários quilómetros (e vários minutos de carro)
da realidade. Este módulo serve a árvore concelho → freguesia → sítio,
com as coordenadas de cada nível, para o utente afinar a posição com
nomes que conhece de cor — sem mapa, sem GPS, sem dados pessoais.

Filosofia (a mesma dos fluxogramas e da rede de viagem)
-------------------------------------------------------
Tudo o que é conhecimento local vive em app/data/localidades.json,
EDITÁVEL por qualquer pessoa da equipa: nomes, coordenadas, freguesias
novas. Nada de lógica escondida no código. O ficheiro é validado no
arranque do servidor — um id repetido, um ponto no mar ou na ilha errada,
uma freguesia sem coordenadas rebentam logo, com mensagem clara.

Dois níveis de verificação:
  - validar(dados)  → ERROS que impedem o arranque (estrutura, limites);
  - avisos(...)     → suspeitas que não impedem nada mas merecem olhos
    humanos (ex.: um sítio a >12 km do centro do concelho — foi assim
    que se apanhou um "Outeiro" da Camacha com coordenadas nos Canhas).
"""

from __future__ import annotations

import json
import unicodedata
from copy import deepcopy
from pathlib import Path

from .geo import haversine_km
from .viagem import ilha_do_ponto

FICHEIRO = Path(__file__).resolve().parent.parent / "data" / "localidades.json"

ILHAS_CONHECIDAS = {"madeira", "porto_santo"}

# Caixas aproximadas POR ILHA: mais apertadas do que a caixa única da RAM,
# apanham pontos "no mar" ou trocados de ilha logo no arranque.
_LIMITES = {
    "madeira": (32.55, 32.95, -17.35, -16.60),
    "porto_santo": (32.95, 33.15, -16.45, -16.25),
}

# Avisos brandos (não impedem o arranque):
_LIMIAR_SUSPEITO_KM = 12.0        # sítio demasiado longe do centro do concelho
_LIMIAR_QUASE_DUPLICADO_KM = 0.1  # dois sítios praticamente no mesmo ponto


class ErroLocalidades(ValueError):
    """localidades.json inválido (apanhado no arranque, como nos fluxogramas)."""


_cache: dict | None = None


def carregar(recarregar: bool = False) -> dict:
    """Carrega e VALIDA as localidades uma única vez (erros rebentam no arranque)."""
    global _cache
    if _cache is None or recarregar:
        dados = json.loads(FICHEIRO.read_text(encoding="utf-8"))
        problemas = validar(dados)
        if problemas:
            raise ErroLocalidades(
                "localidades.json inválido:\n- " + "\n- ".join(problemas)
            )
        _cache = _preparar(dados)
    return _cache


# ------------------------------------------------------------ validação -- #

def _coordenada(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _dentro_da_ilha(ilha: str, lat: float, lng: float) -> bool:
    lat_min, lat_max, lng_min, lng_max = _LIMITES[ilha]
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def validar(dados: dict) -> list[str]:
    """Lista de problemas (vazia = ok). Usada aqui e por validar_dados.py."""
    problemas: list[str] = []
    concelhos = dados.get("concelhos")
    if not isinstance(concelhos, list) or not concelhos:
        return ["'concelhos' em falta ou vazio"]

    ids_c: set[str] = set()
    nomes_c: set[str] = set()
    for c in concelhos:
        cid = c.get("id") or "(sem id)"
        onde = f"concelho '{cid}'"
        if not c.get("id") or not c.get("nome"):
            problemas.append(f"{onde}: falta 'id' ou 'nome'")
            continue
        if cid in ids_c:
            problemas.append(f"{onde}: id repetido")
        ids_c.add(cid)
        if c["nome"] in nomes_c:
            problemas.append(f"{onde}: nome repetido ('{c['nome']}')")
        nomes_c.add(c["nome"])

        ilha = c.get("ilha")
        if ilha not in ILHAS_CONHECIDAS:
            problemas.append(f"{onde}: ilha desconhecida ({ilha!r})")
            continue
        if not (_coordenada(c.get("lat")) and _coordenada(c.get("lng"))):
            problemas.append(f"{onde}: centro sem 'lat'/'lng' numéricos")
            continue
        problemas.extend(_validar_ponto(onde + " (centro)", ilha, c["lat"], c["lng"]))

        freguesias = c.get("freguesias")
        if not isinstance(freguesias, list) or not freguesias:
            problemas.append(f"{onde}: 'freguesias' em falta ou vazio")
            continue
        ids_f: set[str] = set()
        for f in freguesias:
            fid = f.get("id") or "(sem id)"
            onde_f = f"{onde} / freguesia '{fid}'"
            if not f.get("id") or not f.get("nome"):
                problemas.append(f"{onde_f}: falta 'id' ou 'nome'")
                continue
            if fid in ids_f:
                problemas.append(f"{onde_f}: id repetido no concelho")
            ids_f.add(fid)

            sitios = f.get("sitios")
            if not isinstance(sitios, list):
                problemas.append(f"{onde_f}: 'sitios' tem de ser uma lista (pode ser vazia)")
                sitios = []
            tem_coordenada = _coordenada(f.get("lat")) and _coordenada(f.get("lng"))
            if not tem_coordenada and not sitios:
                problemas.append(
                    f"{onde_f}: sem 'lat'/'lng' e sem sítios — não há como situar o utente"
                )
            if tem_coordenada:
                problemas.extend(_validar_ponto(onde_f, ilha, f["lat"], f["lng"]))

            ids_s: set[str] = set()
            for s in sitios:
                sid = s.get("id") or "(sem id)"
                onde_s = f"{onde_f} / sítio '{sid}'"
                if not s.get("id") or not s.get("nome"):
                    problemas.append(f"{onde_s}: falta 'id' ou 'nome'")
                    continue
                if sid in ids_s:
                    problemas.append(f"{onde_s}: id repetido na freguesia")
                ids_s.add(sid)
                if not (_coordenada(s.get("lat")) and _coordenada(s.get("lng"))):
                    problemas.append(f"{onde_s}: sem 'lat'/'lng' numéricos")
                    continue
                problemas.extend(_validar_ponto(onde_s, ilha, s["lat"], s["lng"]))

    return problemas


def _validar_ponto(onde: str, ilha: str, lat: float, lng: float) -> list[str]:
    """Um ponto tem de cair na caixa da SUA ilha e 'pertencer' a ela na rede."""
    if not _dentro_da_ilha(ilha, lat, lng):
        return [f"{onde}: ({lat}, {lng}) fora dos limites da ilha '{ilha}'"]
    # Coerência com a rede de viagem: o nó mais próximo tem de ser da mesma
    # ilha (apanha trocas Madeira ↔ Porto Santo que escapem às caixas).
    if ilha_do_ponto(lat, lng) != ilha:
        return [f"{onde}: ({lat}, {lng}) parece estar noutra ilha (ver rede_viagem.json)"]
    return []


# ----------------------------------------------------------- preparação -- #

def _chave_alfabetica(nome: str) -> str:
    """Ordena ignorando acentos e maiúsculas ('Água de Pena' fica no A)."""
    plano = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return plano.casefold()


def _preparar(dados: dict) -> dict:
    """Centros calculados + listas ordenadas alfabeticamente (uma vez)."""
    prep = deepcopy(dados)
    for c in prep["concelhos"]:
        c["centro"] = {"lat": c["lat"], "lng": c["lng"]}
        for f in c["freguesias"]:
            if _coordenada(f.get("lat")) and _coordenada(f.get("lng")):
                lat, lng = f["lat"], f["lng"]
            else:
                # Sem coordenada própria: o centro é o centroide dos sítios.
                lat = sum(s["lat"] for s in f["sitios"]) / len(f["sitios"])
                lng = sum(s["lng"] for s in f["sitios"]) / len(f["sitios"])
            f["centro"] = {"lat": round(lat, 6), "lng": round(lng, 6)}
            f.setdefault("verificado", True)
            f["sitios"] = sorted(f["sitios"], key=lambda s: _chave_alfabetica(s["nome"]))
        c["freguesias"] = sorted(c["freguesias"], key=lambda f: _chave_alfabetica(f["nome"]))
    prep["concelhos"] = sorted(prep["concelhos"], key=lambda c: _chave_alfabetica(c["nome"]))
    return prep


def arvore() -> dict:
    """Cópia da árvore preparada (para a API — quem chama pode alterar à vontade)."""
    return deepcopy(carregar())


# --------------------------------------------------------------- avisos -- #

def avisos(prep: dict | None = None) -> list[str]:
    """Suspeitas que merecem olhos humanos (não impedem o arranque).

    - sítio/freguesia a mais de 12 km do centro do concelho: quase de
      certeza um engano de transcrição;
    - dois sítios da mesma freguesia praticamente no mesmo ponto;
    - freguesias com "verificado": false (acrescentadas pelo protótipo).
    """
    prep = prep or carregar()
    saida: list[str] = []
    for c in prep["concelhos"]:
        centro = c["centro"]
        for f in c["freguesias"]:
            if not f.get("verificado", True):
                saida.append(
                    f"{c['nome']} / {f['nome']}: coordenada por confirmar "
                    f"({f.get('nota') or 'acrescentada pelo protótipo'})"
                )
            d_f = haversine_km(centro["lat"], centro["lng"], f["centro"]["lat"], f["centro"]["lng"])
            if d_f > _LIMIAR_SUSPEITO_KM and not f["sitios"]:
                saida.append(
                    f"{c['nome']} / {f['nome']}: centro a {d_f:.1f} km do centro do "
                    f"concelho — confirmar coordenadas"
                )
            for indice, s in enumerate(f["sitios"]):
                d_s = haversine_km(centro["lat"], centro["lng"], s["lat"], s["lng"])
                if d_s > _LIMIAR_SUSPEITO_KM:
                    saida.append(
                        f"{c['nome']} / {f['nome']} / {s['nome']}: a {d_s:.1f} km do "
                        f"centro do concelho — confirmar coordenadas"
                    )
                for outro in f["sitios"][indice + 1:]:
                    if haversine_km(s["lat"], s["lng"], outro["lat"], outro["lng"]) < _LIMIAR_QUASE_DUPLICADO_KM:
                        saida.append(
                            f"{c['nome']} / {f['nome']}: '{s['nome']}' e '{outro['nome']}' "
                            f"estão praticamente no mesmo ponto — confirmar"
                        )
    return saida
