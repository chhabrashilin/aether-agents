"""Open-Meteo meteorology client (wind, BLH, humidity). No API key required."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True)
class MeteoSnapshot:
    valid_at: datetime
    wind_speed_ms: float | None
    wind_direction_deg: float | None
    boundary_layer_height_m: float | None
    relative_humidity_pct: float | None


class MeteoClientProtocol(Protocol):
    def fetch_snapshot(
        self,
        *,
        latitude: float,
        longitude: float,
        as_of: datetime | None = None,
    ) -> MeteoSnapshot:
        ...


def _parse_iso(ts: str) -> datetime:
    # Open-Meteo returns local or UTC ISO without Z sometimes.
    if ts.endswith("Z"):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class MeteoClient:
    """Open-Meteo forecast/archive-style hourly snapshot."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        timeout_s: float = 30.0,
        base_url: str = _FORECAST_URL,
    ) -> None:
        self.base_url = base_url
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> MeteoClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_snapshot(
        self,
        *,
        latitude: float,
        longitude: float,
        as_of: datetime | None = None,
    ) -> MeteoSnapshot:
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(
                [
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "relative_humidity_2m",
                    "boundary_layer_height",
                ]
            ),
            "wind_speed_unit": "ms",
            "timezone": "UTC",
            "forecast_days": 1,
        }
        response = self._client.get(self.base_url, params=params)
        response.raise_for_status()
        payload = response.json()
        return self._select_hour(payload, as_of=as_of)

    @staticmethod
    def _select_hour(payload: dict[str, Any], *, as_of: datetime | None) -> MeteoSnapshot:
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        if not times:
            ref = as_of or datetime.now(timezone.utc)
            return MeteoSnapshot(
                valid_at=ref,
                wind_speed_ms=None,
                wind_direction_deg=None,
                boundary_layer_height_m=None,
                relative_humidity_pct=None,
            )

        target = as_of or datetime.now(timezone.utc)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)

        parsed = [_parse_iso(t) for t in times]
        idx = min(range(len(parsed)), key=lambda i: abs((parsed[i] - target).total_seconds()))

        def _get(name: str) -> float | None:
            series = hourly.get(name) or []
            if idx >= len(series) or series[idx] is None:
                return None
            return float(series[idx])

        return MeteoSnapshot(
            valid_at=parsed[idx],
            wind_speed_ms=_get("wind_speed_10m"),
            wind_direction_deg=_get("wind_direction_10m"),
            boundary_layer_height_m=_get("boundary_layer_height"),
            relative_humidity_pct=_get("relative_humidity_2m"),
        )


class MockMeteoClient:
    """Injected meteorology for deterministic tests."""

    def __init__(self, snapshot: MeteoSnapshot) -> None:
        self.snapshot = snapshot

    def fetch_snapshot(
        self,
        *,
        latitude: float,
        longitude: float,
        as_of: datetime | None = None,
    ) -> MeteoSnapshot:
        del latitude, longitude, as_of
        return self.snapshot
