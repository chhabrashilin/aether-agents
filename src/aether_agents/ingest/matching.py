"""Station matching between CPCB OGD names and OpenAQ locations.

Matching combines normalized name similarity with optional geographic
distance. CPCB Real-time AQI rows often lack coordinates, so name+city is the
primary signal; when both sides have lat/lon, a distance gate is applied.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional, Sequence

from aether_agents.ingest.cpcb import CpcbRecord
from aether_agents.ingest.openaq import OpenAqLocation

# Agency / network suffixes only; do NOT list place acronyms like "ITO"
# (Income Tax Office is a real Delhi station name).
_SUFFIX_RE = re.compile(
    r"\b(cpcb|dpcc|imd|namp|uppcb|hspcb|rspcb|ppcb|manual|continuous|"
    r"air\s*quality|monitoring\s*station|station|s\.?t\.?n\.?)\b",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")
_SPACE_RE = re.compile(r"\s+")


def normalize_station_name(name: str) -> str:
    """Lowercase, strip agency suffixes, collapse whitespace."""
    text = (name or "").lower().strip()
    text = _SUFFIX_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class StationMatch:
    cpcb_station: str
    cpcb_city: str
    openaq_location_id: str
    openaq_name: str
    name_score: float
    distance_km: Optional[float]
    score: float


def score_pair(
    cpcb_name: str,
    openaq_name: str,
    *,
    cpcb_city: str = "",
    openaq_city: Optional[str] = None,
    cpcb_lat: Optional[float] = None,
    cpcb_lon: Optional[float] = None,
    openaq_lat: Optional[float] = None,
    openaq_lon: Optional[float] = None,
    max_distance_km: float = 5.0,
) -> tuple[float, float, Optional[float]]:
    """Return (combined_score, name_score, distance_km)."""
    n1 = normalize_station_name(cpcb_name)
    n2 = normalize_station_name(openaq_name)
    name_score = SequenceMatcher(None, n1, n2).ratio() if n1 and n2 else 0.0

    # Soft city bonus / penalty
    city_bonus = 0.0
    c_city = (cpcb_city or "").strip().lower()
    o_city = (openaq_city or "").strip().lower()
    if c_city and o_city:
        if c_city == o_city or c_city in o_city or o_city in c_city:
            city_bonus = 0.05
        else:
            city_bonus = -0.05

    distance_km: Optional[float] = None
    geo_factor = 1.0
    if None not in (cpcb_lat, cpcb_lon, openaq_lat, openaq_lon):
        distance_km = haversine_km(cpcb_lat, cpcb_lon, openaq_lat, openaq_lon)  # type: ignore[arg-type]
        if distance_km > max_distance_km:
            return 0.0, name_score, distance_km
        # Decay score with distance inside the gate
        geo_factor = max(0.0, 1.0 - (distance_km / max_distance_km) * 0.25)

    combined = max(0.0, min(1.0, (name_score + city_bonus) * geo_factor))
    return combined, name_score, distance_km


def match_stations(
    cpcb_records: Sequence[CpcbRecord],
    openaq_locations: Sequence[OpenAqLocation],
    *,
    min_score: float = 0.72,
    max_distance_km: float = 5.0,
) -> list[StationMatch]:
    """Greedy 1:1 matching of unique CPCB station names to OpenAQ locations."""
    # Unique CPCB stations (name + city)
    cpcb_unique: dict[tuple[str, str], CpcbRecord] = {}
    for rec in cpcb_records:
        key = (rec.station, rec.city)
        if key[0] and key not in cpcb_unique:
            cpcb_unique[key] = rec

    used_openaq: set[str] = set()
    matches: list[StationMatch] = []

    # Score all pairs then greedy-assign by descending score
    candidates: list[tuple[float, float, Optional[float], CpcbRecord, OpenAqLocation]] = []
    for rec in cpcb_unique.values():
        for loc in openaq_locations:
            combined, name_score, dist = score_pair(
                rec.station,
                loc.name,
                cpcb_city=rec.city,
                openaq_city=loc.city or loc.locality,
                openaq_lat=loc.latitude,
                openaq_lon=loc.longitude,
                max_distance_km=max_distance_km,
            )
            if combined >= min_score:
                candidates.append((combined, name_score, dist, rec, loc))

    candidates.sort(key=lambda t: t[0], reverse=True)
    used_cpcb: set[tuple[str, str]] = set()
    for combined, name_score, dist, rec, loc in candidates:
        ckey = (rec.station, rec.city)
        if ckey in used_cpcb or loc.id in used_openaq:
            continue
        used_cpcb.add(ckey)
        used_openaq.add(loc.id)
        matches.append(
            StationMatch(
                cpcb_station=rec.station,
                cpcb_city=rec.city,
                openaq_location_id=loc.id,
                openaq_name=loc.name,
                name_score=name_score,
                distance_km=dist,
                score=combined,
            )
        )
    return matches
