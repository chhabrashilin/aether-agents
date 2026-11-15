"""NASA FIRMS client (MAP_KEY from env). Mockable for tests without live keys."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from aether_agents.config import get_settings

# FIRMS area CSV endpoint pattern (VIIRS SNPP last N days).
_FIRMS_AREA_URL = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
    "{map_key}/VIIRS_SNPP_NRT/{west},{south},{east},{north}/{days}"
)


@dataclass(frozen=True)
class FirmsFireEvent:
    latitude: float
    longitude: float
    brightness: float | None = None
    acq_datetime: datetime | None = None
    confidence: str | None = None


class FirmsClientProtocol(Protocol):
    def fetch_fires(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float = 250.0,
        days: int = 3,
        as_of: datetime | None = None,
    ) -> list[FirmsFireEvent]:
        ...


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2 (degrees, 0=N)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def angle_difference_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two compass angles."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def is_upwind(
    *,
    station_lat: float,
    station_lon: float,
    fire_lat: float,
    fire_lon: float,
    wind_direction_deg: float | None,
    sector_half_width_deg: float = 60.0,
) -> bool:
    """True if fire lies in the upwind sector relative to wind_from direction.

    Meteorological wind direction is the direction wind comes *from*.
    A fire upwind of the station lies roughly along that incoming bearing.
    If wind is unknown, all fires within the search radius count as upwind.
    """
    if wind_direction_deg is None:
        return True
    fire_bearing = _bearing_deg(station_lat, station_lon, fire_lat, fire_lon)
    return angle_difference_deg(fire_bearing, wind_direction_deg) <= sector_half_width_deg


class FirmsClient:
    """Live FIRMS area CSV client. Requires ``FIRMS_MAP_KEY`` for network calls."""

    def __init__(
        self,
        map_key: str | None = None,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        settings = get_settings()
        self.map_key = map_key if map_key is not None else settings.firms_map_key
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FirmsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_fires(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float = 250.0,
        days: int = 3,
        as_of: datetime | None = None,
    ) -> list[FirmsFireEvent]:
        del as_of  # live endpoint is "last N days"; as_of reserved for archives
        if not self.map_key:
            return []

        # Approximate bounding box (~111 km per degree latitude).
        dlat = radius_km / 111.0
        dlon = radius_km / (111.0 * max(0.2, math.cos(math.radians(latitude))))
        west = longitude - dlon
        east = longitude + dlon
        south = latitude - dlat
        north = latitude + dlat
        url = _FIRMS_AREA_URL.format(
            map_key=self.map_key,
            west=f"{west:.4f}",
            south=f"{south:.4f}",
            east=f"{east:.4f}",
            north=f"{north:.4f}",
            days=max(1, min(int(days), 10)),
        )
        response = self._client.get(url)
        response.raise_for_status()
        text = response.text.strip()
        if not text or text.lower().startswith("invalid") or "no data" in text.lower():
            return []
        return self._parse_csv(text, latitude, longitude, radius_km)

    @staticmethod
    def _parse_csv(
        text: str,
        center_lat: float,
        center_lon: float,
        radius_km: float,
    ) -> list[FirmsFireEvent]:
        reader = csv.DictReader(io.StringIO(text))
        events: list[FirmsFireEvent] = []
        for row in reader:
            try:
                lat = float(row.get("latitude") or row.get("Latitude") or "")
                lon = float(row.get("longitude") or row.get("Longitude") or "")
            except ValueError:
                continue
            if _haversine_km(center_lat, center_lon, lat, lon) > radius_km:
                continue
            brightness = None
            raw_b = row.get("bright_ti4") or row.get("brightness")
            if raw_b:
                try:
                    brightness = float(raw_b)
                except ValueError:
                    brightness = None
            acq_dt = None
            acq_date = row.get("acq_date") or ""
            acq_time = (row.get("acq_time") or "0000").zfill(4)
            if acq_date:
                try:
                    acq_dt = datetime(
                        int(acq_date[0:4]),
                        int(acq_date[5:7]),
                        int(acq_date[8:10]),
                        int(acq_time[0:2]),
                        int(acq_time[2:4]),
                        tzinfo=timezone.utc,
                    )
                except (ValueError, IndexError):
                    acq_dt = None
            events.append(
                FirmsFireEvent(
                    latitude=lat,
                    longitude=lon,
                    brightness=brightness,
                    acq_datetime=acq_dt,
                    confidence=row.get("confidence"),
                )
            )
        return events


class MockFirmsClient:
    """Deterministic FIRMS stand-in for tests (no network / no MAP_KEY)."""

    def __init__(self, events: list[FirmsFireEvent] | None = None) -> None:
        self.events = list(events or [])

    def fetch_fires(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float = 250.0,
        days: int = 3,
        as_of: datetime | None = None,
    ) -> list[FirmsFireEvent]:
        del days
        cutoff = None
        if as_of is not None:
            cutoff = as_of - timedelta(hours=0)
        out: list[FirmsFireEvent] = []
        for ev in self.events:
            if _haversine_km(latitude, longitude, ev.latitude, ev.longitude) > radius_km:
                continue
            if cutoff is not None and ev.acq_datetime is not None and ev.acq_datetime > cutoff:
                continue
            out.append(ev)
        return out
