"""OpenAQ v3 client for hourly station history.

Gaps stay gaps: this client never interpolates missing hours. Callers that
need complete time bases must leave absent timestamps as missing data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from aether_agents.ingest.qa import (
    flag_missing,
    flag_non_numeric,
    flag_out_of_range,
    merge_flags,
)

OPENAQ_BASE_URL = "https://api.openaq.org/v3"

# Approximate Delhi–NCR bounding box (west, south, east, north).
DELHI_NCR_BBOX = (76.50, 28.20, 77.85, 29.05)


@dataclass(frozen=True)
class OpenAqLocation:
    id: str
    name: str
    locality: Optional[str]
    city: Optional[str]
    country: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class OpenAqMeasurement:
    location_id: str
    location_name: str
    pollutant: str
    value: Optional[float]
    unit: Optional[str]
    observed_at: Optional[datetime]
    value_semantics: str = "concentration"
    qa_flags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def parse_openaq_datetime(value: Optional[str | datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    # OpenAQ returns ISO-8601; tolerate trailing Z.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _coords_from_location(row: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    coords = row.get("coordinates") or {}
    if isinstance(coords, dict):
        lat = coords.get("latitude", coords.get("lat"))
        lon = coords.get("longitude", coords.get("lon"))
        try:
            return (
                float(lat) if lat is not None else None,
                float(lon) if lon is not None else None,
            )
        except (TypeError, ValueError):
            return None, None
    return None, None


def parse_openaq_locations(payload: dict[str, Any]) -> list[OpenAqLocation]:
    results = payload.get("results") or payload.get("data") or []
    out: list[OpenAqLocation] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        lat, lon = _coords_from_location(row)
        loc_id = row.get("id")
        if loc_id is None:
            continue
        out.append(
            OpenAqLocation(
                id=str(loc_id),
                name=str(row.get("name") or "").strip(),
                locality=(str(row["locality"]).strip() if row.get("locality") else None),
                city=(str(row["city"]).strip() if row.get("city") else None),
                country=(
                    (row.get("country") or {}).get("code")
                    if isinstance(row.get("country"), dict)
                    else (str(row["country"]).strip() if row.get("country") else None)
                ),
                latitude=lat,
                longitude=lon,
                raw=row,
            )
        )
    return out


def _measurement_datetime(row: dict[str, Any]) -> Optional[datetime]:
    period = row.get("period") or {}
    if isinstance(period, dict):
        dt_from = period.get("datetimeFrom") or period.get("datetime_from")
        if isinstance(dt_from, dict):
            return parse_openaq_datetime(dt_from.get("utc") or dt_from.get("local"))
        return parse_openaq_datetime(dt_from)
    return parse_openaq_datetime(row.get("datetime") or row.get("date", {}).get("utc")
                                 if isinstance(row.get("date"), dict)
                                 else row.get("date"))


def _pollutant_from_row(row: dict[str, Any]) -> str:
    param = row.get("parameter") or row.get("pollutant") or {}
    if isinstance(param, dict):
        return str(param.get("name") or param.get("id") or "").strip()
    return str(param).strip()


def parse_openaq_measurements(
    payload: dict[str, Any],
    *,
    location_id: str = "",
    location_name: str = "",
) -> list[OpenAqMeasurement]:
    """Parse OpenAQ v3 hourly/measurement payloads.

    Missing values become ``None`` with QA flags; no gap filling is performed.
    """
    results = payload.get("results") or payload.get("data") or []
    out: list[OpenAqMeasurement] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        raw_value = row.get("value")
        if raw_value is None and isinstance(row.get("summary"), dict):
            raw_value = row["summary"].get("avg") or row["summary"].get("mean")
        flags = flag_non_numeric(raw_value)
        value: Optional[float]
        if flags:
            value = None
        elif raw_value is None or raw_value == "":
            value = None
            flags = ["missing_value"]
        else:
            value = float(raw_value)

        pollutant = _pollutant_from_row(row)
        unit = None
        param = row.get("parameter")
        if isinstance(param, dict):
            unit = param.get("units") or param.get("unit")
        unit = unit or row.get("unit") or row.get("units")

        observed_at = _measurement_datetime(row)
        if observed_at is None:
            flags = merge_flags(flags, ["missing_timestamp"])

        flags = merge_flags(
            flags,
            flag_missing(value),
            flag_out_of_range(value, pollutant=pollutant, value_semantics="concentration"),
        )
        # Explicit gap marker when value absent; do not invent a fill.
        if value is None and "gap" not in flags:
            flags = merge_flags(flags, ["gap"])

        loc_id = str(row.get("location_id") or location_id or "")
        loc_name = str(row.get("location") or location_name or "")
        if isinstance(row.get("location"), dict):
            loc_name = str(row["location"].get("name") or loc_name)
            loc_id = str(row["location"].get("id") or loc_id)

        out.append(
            OpenAqMeasurement(
                location_id=loc_id,
                location_name=loc_name,
                pollutant=pollutant,
                value=value,
                unit=str(unit) if unit else None,
                observed_at=observed_at,
                qa_flags=flags,
                raw=row,
            )
        )
    return out


class OpenAqClient:
    """HTTP client for OpenAQ API v3."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = OPENAQ_BASE_URL,
        timeout: float = 60.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAqClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ValueError("OPENAQ_API_KEY is required for live OpenAQ fetches")
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    def fetch_locations(
        self,
        *,
        bbox: tuple[float, float, float, float] = DELHI_NCR_BBOX,
        limit: int = 100,
        page: int = 1,
    ) -> dict[str, Any]:
        """Fetch OpenAQ locations inside a bounding box (Delhi–NCR by default)."""
        west, south, east, north = bbox
        params = {
            "bbox": f"{west},{south},{east},{north}",
            "limit": limit,
            "page": page,
        }
        response = self._client.get(
            f"{self.base_url}/locations",
            params=params,
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected OpenAQ locations response")
        return data

    def fetch_location_hours(
        self,
        location_id: str | int,
        *,
        limit: int = 100,
        page: int = 1,
        datetime_from: Optional[str] = None,
        datetime_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch hourly averages for a location.

        OpenAQ may omit hours with no data; those hours are **gaps** and must
        remain absent in storage (no silent fill).
        """
        params: dict[str, Any] = {"limit": limit, "page": page}
        if datetime_from:
            params["datetime_from"] = datetime_from
        if datetime_to:
            params["datetime_to"] = datetime_to
        response = self._client.get(
            f"{self.base_url}/locations/{location_id}/hours",
            params=params,
            headers=self._headers(),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected OpenAQ hours response")
        return data

    def list_delhi_ncr_locations(
        self,
        *,
        bbox: tuple[float, float, float, float] = DELHI_NCR_BBOX,
        max_pages: int = 10,
    ) -> tuple[dict[str, Any], list[OpenAqLocation]]:
        merged: dict[str, Any] = {"results": []}
        locations: list[OpenAqLocation] = []
        for page in range(1, max_pages + 1):
            payload = self.fetch_locations(bbox=bbox, page=page)
            rows = payload.get("results") or []
            if isinstance(rows, list):
                merged["results"].extend(rows)
            locations.extend(parse_openaq_locations(payload))
            meta = payload.get("meta") or {}
            found = meta.get("found")
            limit = meta.get("limit") or len(rows) or 1
            if not rows:
                break
            if isinstance(found, int) and page * limit >= found:
                break
            if len(rows) < (meta.get("limit") or 100):
                break
        return merged, locations
