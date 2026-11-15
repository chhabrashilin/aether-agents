"""CPCB Real-time AQI client via data.gov.in Open Government Data.

Resource: 3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69
(CPCB Real time Air Quality Index from various locations)

--------------------------------------------------------------------
VALUE SEMANTICS: sub-index vs concentration (read carefully)
--------------------------------------------------------------------
The data.gov.in CPCB Real-time AQI resource returns per-pollutant fields
``pollutant_min``, ``pollutant_max``, and ``pollutant_avg``.

These fields are **AQI sub-index values** on the Indian CPCB 0–500 scale,
**not** mass concentrations in µg/m³ (or ppm for gases).

- Station-level AQI is conventionally the maximum of pollutant sub-indices.
- Do **not** treat ``pollutant_avg`` as PM₂.₅ µg/m³ when computing health
  metrics or comparing to OpenAQ concentration series.
- Downstream code must set ``value_semantics="sub_index"`` for CPCB rows
  and keep OpenAQ rows as ``value_semantics="concentration"``.
- Cross-source joins should be done on station identity and timestamp, not
  by naively equating numeric values across semantics.
--------------------------------------------------------------------
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
    flag_stale,
    merge_flags,
)

CPCB_RESOURCE_ID = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
CPCB_BASE_URL = f"https://api.data.gov.in/resource/{CPCB_RESOURCE_ID}"

# Delhi–NCT and adjoining NCR cities commonly present in CPCB OGD feeds.
DELHI_NCR_CITIES = frozenset(
    {
        "delhi",
        "new delhi",
        "ghaziabad",
        "noida",
        "greater noida",
        "faridabad",
        "gurugram",
        "gurgaon",
        "meerut",
        "baghpat",
        "bulandshahr",
        "hapur",
        "muzaffarnagar",
        "sonipat",
        "rohtak",
        "jhajjar",
        "panipat",
        "alwar",
        "bhiwadi",
    }
)

DELHI_NCR_STATES = frozenset(
    {
        "delhi",
        "nct of delhi",
        "haryana",
        "uttar pradesh",
        "rajasthan",
    }
)


@dataclass(frozen=True)
class CpcbRecord:
    """One pollutant reading from a CPCB station snapshot."""

    station: str
    city: str
    state: str
    country: str
    pollutant_id: str
    pollutant_avg: Optional[float]
    pollutant_min: Optional[float]
    pollutant_max: Optional[float]
    last_update: Optional[datetime]
    # Always sub_index for this resource; see module docstring.
    value_semantics: str = "sub_index"
    qa_flags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _parse_float(raw: object) -> tuple[Optional[float], list[str]]:
    flags = flag_non_numeric(raw)
    if flags:
        return None, flags
    if raw is None or raw == "":
        return None, ["missing_value"]
    return float(raw), []  # type: ignore[arg-type]


def parse_cpcb_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse CPCB ``last_update`` strings such as ``15-11-2024 14:00:00``."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    for fmt in (
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(text.replace("Z", ""), fmt.replace("Z", ""))
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def is_delhi_ncr(city: str, state: str = "") -> bool:
    """Return True if city/state falls in the Delhi–NCR filter set."""
    c = (city or "").strip().lower()
    s = (state or "").strip().lower()
    if c in DELHI_NCR_CITIES:
        return True
    # Delhi state with any city name
    if s in {"delhi", "nct of delhi"}:
        return True
    # NCR fringe: keep Haryana/UP/Rajasthan only when city is known NCR
    if s in DELHI_NCR_STATES and c in DELHI_NCR_CITIES:
        return True
    return False


def parse_cpcb_records(
    payload: dict[str, Any],
    *,
    delhi_ncr_only: bool = True,
    now: Optional[datetime] = None,
) -> list[CpcbRecord]:
    """Parse a data.gov.in JSON payload into typed CPCB records."""
    records_raw = payload.get("records") or payload.get("data") or []
    out: list[CpcbRecord] = []
    for row in records_raw:
        if not isinstance(row, dict):
            continue
        city = str(row.get("city") or "").strip()
        state = str(row.get("state") or "").strip()
        if delhi_ncr_only and not is_delhi_ncr(city, state):
            continue

        avg, avg_flags = _parse_float(row.get("pollutant_avg"))
        mn, _ = _parse_float(row.get("pollutant_min"))
        mx, _ = _parse_float(row.get("pollutant_max"))
        pollutant = str(row.get("pollutant_id") or row.get("pollutant") or "").strip()
        last_update = parse_cpcb_timestamp(row.get("last_update"))

        flags = merge_flags(
            avg_flags,
            flag_missing(avg),
            flag_out_of_range(avg, pollutant=pollutant, value_semantics="sub_index"),
            flag_stale(last_update, now=now),
            ["cpcb_sub_index"],  # provenance marker for semantics
        )
        out.append(
            CpcbRecord(
                station=str(row.get("station") or "").strip(),
                city=city,
                state=state,
                country=str(row.get("country") or "India").strip(),
                pollutant_id=pollutant,
                pollutant_avg=avg,
                pollutant_min=mn,
                pollutant_max=mx,
                last_update=last_update,
                qa_flags=flags,
                raw=row,
            )
        )
    return out


class CpcbClient:
    """HTTP client for the CPCB Real-time AQI data.gov.in resource."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = CPCB_BASE_URL,
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

    def __enter__(self) -> CpcbClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def fetch_raw(
        self,
        *,
        limit: int = 1000,
        offset: int = 0,
        filters: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Fetch one page of raw JSON from data.gov.in.

        Requires ``DATA_GOV_IN_API_KEY``. When calling live APIs, pass the key
        via settings; unit tests inject fixtures and never hit the network.
        """
        if not self.api_key:
            raise ValueError("DATA_GOV_IN_API_KEY is required for live CPCB fetches")

        params: dict[str, Any] = {
            "api-key": self.api_key,
            "format": "json",
            "limit": limit,
            "offset": offset,
        }
        if filters:
            for key, value in filters.items():
                params[f"filters[{key}]"] = value

        response = self._client.get(self.base_url, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected CPCB response type")
        return data

    def fetch_delhi_ncr(
        self,
        *,
        limit: int = 1000,
        max_pages: int = 20,
    ) -> tuple[dict[str, Any], list[CpcbRecord]]:
        """Fetch and filter Delhi/NCR records across pages.

        Server-side city filters are inconsistent across OGD mirrors, so we
        page broadly and apply :func:`is_delhi_ncr` client-side.
        """
        all_records: list[CpcbRecord] = []
        merged_payload: dict[str, Any] = {"records": [], "resource_id": CPCB_RESOURCE_ID}
        offset = 0
        for _ in range(max_pages):
            page = self.fetch_raw(limit=limit, offset=offset)
            page_rows = page.get("records") or page.get("data") or []
            if isinstance(page_rows, list):
                merged_payload["records"].extend(page_rows)
            parsed = parse_cpcb_records(page, delhi_ncr_only=True)
            all_records.extend(parsed)
            if not page_rows or len(page_rows) < limit:
                break
            offset += limit
        return merged_payload, all_records
