"""Cálculos geográficos simples (sem dependências externas).

A distância de Haversine é "em linha reta". Na Madeira, com a orografia,
a distância por estrada pode ser bastante maior. Para o protótipo chega,
mas fica anotado como melhoria futura (usar uma API de direções).
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

RAIO_TERRA_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância em quilómetros entre dois pontos (lat/lng em graus)."""
    rlat1, rlng1, rlat2, rlng2 = map(radians, (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    return 2 * RAIO_TERRA_KM * asin(sqrt(a))


def ordenar_por_distancia(unidades: list[dict], lat: float, lng: float) -> list[dict]:
    """Devolve cópias das unidades com o campo `distancia_km`, ordenadas."""
    com_distancia = [
        {**u, "distancia_km": round(haversine_km(lat, lng, u["lat"], u["lng"]), 1)}
        for u in unidades
    ]
    return sorted(com_distancia, key=lambda u: u["distancia_km"])
