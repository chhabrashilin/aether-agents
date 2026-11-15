"""Shared schemas for Episode and Context agents.

Expected observation shape for ingest alignment
-----------------------------------------------
Ingest should normalize CPCB / OpenAQ rows into :class:`Observation` records.
Gaps stay gaps: use ``value=None`` / ``aqi=None`` rather than silent fill.

**Value semantics (mandatory discipline):**

- ``aqi``: station-level CPCB National AQI (0–500), when known.
- ``value`` + ``value_semantics=concentration``: mass/mixing ratio in ``unit``
  (µg/m³ for PM). EpisodeAgent may map PM₂.₅ µg/m³ → CPCB sub-index via
  :func:`pm25_to_cpcb_aqi` (documented breakpoints; not a lab calibration).
- ``value`` + ``value_semantics=sub_index``: CPCB pollutant **sub-index**
  (0–500) as returned by data.gov.in Real-time AQI. Must **never** be passed
  through concentration→AQI conversion.
- Mixing semantics silently is a scientific error; :meth:`Observation.resolved_aqi`
  refuses unsafe conversions.

Fields:
  station_id       : stable station key (CPCB station code or OpenAQ location id)
  observed_at      : timezone-aware UTC timestamp (hourly preferred)
  pollutant        : lowercase token: pm25, pm10, no2, so2, o3, co, nh3, ...
  value            : numeric reading interpreted via ``value_semantics``
  value_semantics  : concentration | sub_index | unknown
  unit             : e.g. "ug/m3" or "aqi_sub_index"
  aqi              : CPCB station AQI integer when available; None if missing
  qa_flag          : optional quality flag from ingest (pass / suspect / ...)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ValueSemantics = Literal["concentration", "sub_index", "unknown"]


class AqiCategory(str, Enum):
    """CPCB National AQI category labels."""

    GOOD = "Good"
    SATISFACTORY = "Satisfactory"
    MODERATE = "Moderate"
    POOR = "Poor"
    VERY_POOR = "Very Poor"
    SEVERE = "Severe"
    UNKNOWN = "Unknown"


# Inclusive lower bounds for CPCB AQI categories (upper open except Severe).
CPCB_AQI_THRESHOLDS: tuple[tuple[int, AqiCategory], ...] = (
    (0, AqiCategory.GOOD),
    (51, AqiCategory.SATISFACTORY),
    (101, AqiCategory.MODERATE),
    (201, AqiCategory.POOR),
    (301, AqiCategory.VERY_POOR),
    (401, AqiCategory.SEVERE),
)

EPISODE_AQI_FLOOR = 301  # Very Poor and above

# Official CPCB PM2.5 breakpoints (National AQI). Used only for concentration→sub-index.
# Calibration note: this is the published linear breakpoint table, not a site-specific
# transfer function. OpenAQ µg/m³ vs CPCB monitors can differ by instrumentation.
PM25_CPCB_BREAKPOINTS: tuple[tuple[float, float, int, int], ...] = (
    (0.0, 30.0, 0, 50),
    (30.0, 60.0, 51, 100),
    (60.0, 90.0, 101, 200),
    (90.0, 120.0, 201, 300),
    (120.0, 250.0, 301, 400),
    (250.0, 380.0, 401, 500),
)


def aqi_category(aqi: int | None) -> AqiCategory:
    """Map a CPCB AQI integer to its category."""
    if aqi is None:
        return AqiCategory.UNKNOWN
    if aqi < 0:
        return AqiCategory.UNKNOWN
    category = AqiCategory.GOOD
    for lower, label in CPCB_AQI_THRESHOLDS:
        if aqi >= lower:
            category = label
    return category


def pm25_to_cpcb_aqi(concentration_ugm3: float) -> int:
    """Map PM₂.₅ concentration (µg/m³) to CPCB PM₂.₅ sub-index.

    Uses published National AQI breakpoints (:data:`PM25_CPCB_BREAKPOINTS`).
    Call only for ``value_semantics="concentration"`` inputs.
    """
    c = max(0.0, float(concentration_ugm3))
    if c > 380.0:
        return 500
    for c_lo, c_hi, i_lo, i_hi in PM25_CPCB_BREAKPOINTS:
        if c <= c_hi:
            if c_hi == c_lo:
                return i_hi
            frac = (c - c_lo) / (c_hi - c_lo)
            return int(round(i_lo + frac * (i_hi - i_lo)))
    return 500


class Observation(BaseModel):
    """Normalized hourly (or sub-hourly) station observation with typed semantics."""

    station_id: str
    observed_at: datetime
    pollutant: str = "pm25"
    value: float | None = None
    value_semantics: ValueSemantics = "unknown"
    unit: str = "ug/m3"
    aqi: int | None = None
    qa_flag: str | None = None
    resolution_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_semantics_from_unit(self) -> Observation:
        """Infer semantics from unit when left as unknown (never invent values)."""
        if self.value_semantics != "unknown":
            return self
        unit = (self.unit or "").lower().replace("µ", "u")
        if unit in {"aqi_sub_index", "sub_index", "aqi"}:
            self.value_semantics = "sub_index"
        elif unit in {"ug/m3", "ug/m^3", "µg/m3", "µg/m³", "ugm3", "ppm", "ppb"}:
            self.value_semantics = "concentration"
        return self

    def resolved_aqi(self) -> int | None:
        """Resolve a CPCB-scale AQI integer without mixing units.

        Priority:
        1. Explicit station ``aqi``.
        2. ``value`` already a pollutant ``sub_index`` (use as-is, clipped).
        3. PM₂.₅ ``concentration`` → :func:`pm25_to_cpcb_aqi`.
        4. Otherwise None (do not guess).
        """
        self.resolution_notes = []
        if self.aqi is not None:
            self.resolution_notes.append("used_explicit_station_aqi")
            return int(self.aqi)

        if self.value is None:
            return None

        semantics = self.value_semantics
        pollutant = self.pollutant.lower().replace(".", "")

        if semantics == "sub_index":
            # CPCB pollutant sub-index is already on the 0–500 AQI scale.
            idx = int(round(float(self.value)))
            self.resolution_notes.append("used_cpcb_pollutant_sub_index_as_aqi_proxy")
            return max(0, min(500, idx))

        if semantics == "concentration":
            if pollutant in {"pm25", "pm2.5"}:
                mapped = pm25_to_cpcb_aqi(float(self.value))
                self.resolution_notes.append(
                    "mapped_pm25_ugm3_via_cpcb_national_aqi_breakpoints"
                )
                return mapped
            self.resolution_notes.append(
                f"no_aqi_mapping_for_concentration_pollutant={self.pollutant}"
            )
            return None

        # unknown semantics: refuse silent conversion (scientific integrity).
        self.resolution_notes.append(
            "refused_aqi_resolution_unknown_value_semantics"
        )
        return None


class StationStub(BaseModel):
    """Stub-friendly station metadata for read APIs before ingest is wired."""

    station_id: str
    name: str
    city: str = "Delhi"
    latitude: float
    longitude: float
    source: str = "stub"
    active: bool = True


class ContextFeatureVector(BaseModel):
    """Structured meteorology / fire / calendar context for a location-time."""

    location_id: str
    latitude: float
    longitude: float
    valid_at: datetime
    upwind_fire_count_24h: int = 0
    upwind_fire_count_72h: int = 0
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None
    boundary_layer_height_m: float | None = None
    relative_humidity_pct: float | None = None
    is_delhi_winter_season: bool = False
    is_festival: bool = False
    festival_name: str | None = None
    is_holiday: bool = False
    holiday_name: str | None = None
    feature_completeness: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of non-null met/fire inputs used in the vector.",
    )
    extras: dict[str, Any] = Field(default_factory=dict)


class EpisodeObject(BaseModel):
    """Detected Very Poor / Severe smog episode window."""

    episode_id: str
    station_id: str
    onset_at: datetime
    peak_at: datetime
    decay_at: datetime | None = None
    ended_at: datetime | None = None
    peak_aqi: int
    peak_category: AqiCategory
    severity: str
    duration_hours: float
    mean_aqi: float
    data_completeness: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(
        ge=0.0,
        le=1.0,
        description="Higher when gaps are large or window still open.",
    )
    is_open: bool = False
    category_at_peak: AqiCategory | None = None
    notes: list[str] = Field(default_factory=list)
