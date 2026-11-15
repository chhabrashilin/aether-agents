"""QA flag helpers for ingest observations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

# CPCB AQI sub-index and OpenAQ concentration sanity bounds (soft checks).
SUB_INDEX_MAX = 500.0
PM25_UGM3_MAX = 2000.0
PM10_UGM3_MAX = 3000.0
STALE_HOURS = 6.0


def flag_missing(value: Optional[float]) -> list[str]:
    return ["missing_value"] if value is None else []


def flag_non_numeric(raw: object) -> list[str]:
    if raw is None or raw == "":
        return ["missing_value"]
    try:
        float(raw)  # type: ignore[arg-type]
        return []
    except (TypeError, ValueError):
        return ["non_numeric"]


def flag_out_of_range(
    value: Optional[float],
    *,
    pollutant: str,
    value_semantics: str,
) -> list[str]:
    if value is None:
        return []
    if value < 0:
        return ["out_of_range"]
    if value_semantics == "sub_index" and value > SUB_INDEX_MAX:
        return ["out_of_range"]
    pol = pollutant.upper().replace(".", "").replace("_", "")
    if value_semantics == "concentration":
        if pol in {"PM25", "PM2.5"} and value > PM25_UGM3_MAX:
            return ["out_of_range"]
        if pol in {"PM10"} and value > PM10_UGM3_MAX:
            return ["out_of_range"]
    return []


def flag_stale(observed_at: Optional[datetime], *, now: Optional[datetime] = None) -> list[str]:
    if observed_at is None:
        return ["missing_timestamp"]
    ref = now or datetime.now(timezone.utc)
    ts = observed_at if observed_at.tzinfo else observed_at.replace(tzinfo=timezone.utc)
    age_h = (ref - ts).total_seconds() / 3600.0
    return ["stale_timestamp"] if age_h > STALE_HOURS else []


def merge_flags(*groups: list[str]) -> list[str]:
    seen: list[str] = []
    for group in groups:
        for flag in group:
            if flag not in seen:
                seen.append(flag)
    return seen
