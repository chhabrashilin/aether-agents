"""Shared evidence objects and Episode/Context inputs for the agent pipeline.

Episode and Context agents may land separately; Attribution/Critic/Advisory accept
these Pydantic shapes so the supervisor can wire outputs as soon as siblings exist.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SourceClass(str, Enum):
    """Source-class hypotheses for Delhi–NCT winter smog episodes."""

    TRANSPORT_STUBBLE = "transport_stubble"
    LOCAL_COMBUSTION = "local_combustion"
    DUST = "dust"
    INDUSTRIAL = "industrial"
    MIXED = "mixed"


SOURCE_CLASS_LABELS: dict[SourceClass, str] = {
    SourceClass.TRANSPORT_STUBBLE: "Regional transport / stubble burning",
    SourceClass.LOCAL_COMBUSTION: "Local combustion",
    SourceClass.DUST: "Dust / resuspended particulate",
    SourceClass.INDUSTRIAL: "Industrial",
    SourceClass.MIXED: "Mixed / ambiguous",
}


class EvidenceFeature(BaseModel):
    """A single cited evidence feature used by Attribution / Critic / Advisory."""

    name: str
    value: float | str | bool | None = None
    unit: str | None = None
    source: str = Field(description="Upstream provider or agent, e.g. firms, openmeteo, episode")
    citation: str = Field(description="Human-readable citation or provenance note")
    weight: float = Field(default=1.0, ge=0.0, le=5.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    missing: bool = False

    @field_validator("name")
    @classmethod
    def _nonempty_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("evidence feature name must be non-empty")
        return cleaned


class EpisodePhase(str, Enum):
    ONSET = "onset"
    PEAK = "peak"
    DECAY = "decay"
    NONE = "none"


class EpisodeSeverity(str, Enum):
    """CPCB-aligned AQI category labels used for episode severity."""

    GOOD = "Good"
    SATISFACTORY = "Satisfactory"
    MODERATE = "Moderate"
    POOR = "Poor"
    VERY_POOR = "Very Poor"
    SEVERE = "Severe"


class EpisodeTimelinePoint(BaseModel):
    """One point on an episode timeline for dashboard / advisory context."""

    timestamp: datetime
    aqi: float | None = None
    phase: EpisodePhase = EpisodePhase.NONE
    label: str | None = None


class EpisodeOutput(BaseModel):
    """Expected EpisodeAgent output (accepted even if Episode agent is still landing)."""

    episode_id: str
    region: str = "delhi-nct"
    severity: EpisodeSeverity = EpisodeSeverity.MODERATE
    aqi_peak: float | None = None
    aqi_mean: float | None = None
    onset: datetime | None = None
    peak: datetime | None = None
    decay: datetime | None = None
    duration_hours: float | None = None
    phase: EpisodePhase = EpisodePhase.NONE
    uncertainty: float = Field(default=0.3, ge=0.0, le=1.0)
    station_coverage: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of expected stations reporting usable AQI",
    )
    timeline: list[EpisodeTimelinePoint] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ContextOutput(BaseModel):
    """Expected ContextAgent output (fire / met / calendar feature vector)."""

    region: str = "delhi-nct"
    observed_at: datetime | None = None
    fire_count_upwind: int | None = None
    fire_frp_sum: float | None = None
    wind_speed_ms: float | None = None
    wind_direction_deg: float | None = None
    blh_m: float | None = None
    relative_humidity: float | None = None
    temperature_c: float | None = None
    is_festival_window: bool = False
    is_stubble_season: bool = False
    is_weekday: bool | None = None
    missing_fields: list[str] = Field(default_factory=list)
    features: list[EvidenceFeature] = Field(default_factory=list)
    uncertainty: float = Field(default=0.2, ge=0.0, le=1.0)
    extra: dict[str, Any] = Field(default_factory=dict)


class ScoreContribution(BaseModel):
    """Transparent scorecard row: feature → weight → signed contribution.

    Exportable for reproducibility. These are heuristic score increments, not
    causal effect sizes or CTM tagged contributions.
    """

    source_class: SourceClass
    feature: str
    feature_value: float | str | bool | None = None
    weight: float = Field(description="Rule weight applied for this feature")
    contribution: float = Field(
        description="Signed increment added to the class raw score"
    )
    rule: str = Field(description="Human-readable rule that fired")


class AttributionPosterior(BaseModel):
    """Softmax mass for one source class with cited supporting features.

    Probabilities are softmax of heuristic raw scores, not calibrated
    Bayesian posteriors unless a later study demonstrates calibration.
    """

    source_class: SourceClass
    label: str
    probability: float = Field(ge=0.0, le=1.0)
    raw_score: float = 0.0
    supporting_evidence: list[EvidenceFeature] = Field(default_factory=list)
    rationale: str = ""


class AttributionResult(BaseModel):
    """AttributionAgent output: evidence-weighted source-class scores."""

    episode_id: str
    region: str = "delhi-nct"
    posteriors: list[AttributionPosterior]
    dominant_class: SourceClass | None = Field(
        default=None,
        description="Highest-probability class, or null when critic refuses.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[EvidenceFeature] = Field(default_factory=list)
    scorecard: list[ScoreContribution] = Field(
        default_factory=list,
        description="Feature→weight→contribution rows for reproducibility",
    )
    method: str = "rule_score"
    notes: list[str] = Field(default_factory=list)


class CriticFinding(BaseModel):
    code: str
    severity: str = Field(description="info | warn | error")
    message: str
    penalty: float = Field(default=0.0, ge=0.0, le=1.0)


class CriticResult(BaseModel):
    """CriticAgent output: consistency checks and dampened uncertainty.

    Fail-closed: when data are too sparse, ``dominant_refused`` is True and
    ``revised_dominant_class`` is None (or MIXED with explicit refusal note).
    """

    episode_id: str
    revised_posteriors: list[AttributionPosterior]
    revised_dominant_class: SourceClass | None = None
    revised_confidence: float = Field(ge=0.0, le=1.0)
    dominant_refused: bool = Field(
        default=False,
        description="True when critic refuses an overconfident dominant_source",
    )
    findings: list[CriticFinding] = Field(default_factory=list)
    missing_data_penalty: float = Field(default=0.0, ge=0.0, le=1.0)
    overconfidence_dampening: float = Field(default=0.0, ge=0.0, le=1.0)
    method: str = "rule_score"
    notes: list[str] = Field(default_factory=list)


class GrapStage(str, Enum):
    """CAQM GRAP stage labels (advisory alignment only, not legal orders)."""

    NONE = "none"
    STAGE_I = "I"
    STAGE_II = "II"
    STAGE_III = "III"
    STAGE_IV = "IV"


class ExposureGuidance(BaseModel):
    audience: str
    guidance: str
    citations: list[str] = Field(default_factory=list)


# Official CAQM / GRAP references (public pages, not scraped content).
CAQM_GRAP_URL = (
    "https://caqm.nic.in/"  # Commission for Air Quality Management, official portal
)
CAQM_GRAP_DOC_NOTE = (
    "GRAP stage labels in this API are research *alignment bands* mapped from "
    "CPCB AQI categories. Official stage activation is issued only by CAQM / "
    "competent authorities: https://caqm.nic.in/"
)


class AdvisoryResult(BaseModel):
    """AdvisoryAgent output: GRAP *alignment-band* advisory JSON with citations.

    Non-authoritative: never invents legal orders or CAQM directives.
    """

    episode_id: str
    region: str = "delhi-nct"
    grap_stage: GrapStage
    grap_stage_label: str
    grap_alignment_only: bool = True
    aqi_basis: float | None = None
    severity: EpisodeSeverity | None = None
    dominant_source: SourceClass | None = None
    summary: str
    exposure_guidance: list[ExposureGuidance] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    official_sources: list[str] = Field(
        default_factory=lambda: [CAQM_GRAP_URL, CAQM_GRAP_DOC_NOTE]
    )
    disclaimer: str = (
        "NON-AUTHORITATIVE research advisory. GRAP stage fields are AQI "
        "*alignment bands* only, not CAQM orders, legal restrictions, or "
        "enforceable actions. Consult https://caqm.nic.in/ and state notifications "
        "for official measures. Source-class hypotheses are heuristic and may be "
        "refused under sparse data."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = "rule_score"
    critic_findings: list[CriticFinding] = Field(default_factory=list)
    timeline: list[EpisodeTimelinePoint] = Field(default_factory=list)


def episode_from_object(obj: Any) -> EpisodeOutput:
    """Adapt EpisodeObject (or compatible mapping) into Attribution EpisodeOutput."""

    if isinstance(obj, EpisodeOutput):
        return obj
    if isinstance(obj, dict):
        if "aqi_peak" in obj or ("severity" in obj and "onset" in obj):
            try:
                return EpisodeOutput.model_validate(obj)
            except Exception:  # noqa: BLE001  # fall through to sibling shape
                pass
        # Sibling EpisodeObject field names
        peak_cat = obj.get("peak_category") or obj.get("category_at_peak") or obj.get("severity")
        severity = _coerce_severity(peak_cat or obj.get("severity"))
        onset = obj.get("onset_at") or obj.get("onset")
        peak = obj.get("peak_at") or obj.get("peak")
        decay = obj.get("decay_at") or obj.get("decay") or obj.get("ended_at")
        return EpisodeOutput(
            episode_id=str(obj.get("episode_id", "unknown")),
            region="delhi-nct",
            severity=severity,
            aqi_peak=_as_float(obj.get("peak_aqi", obj.get("aqi_peak"))),
            aqi_mean=_as_float(obj.get("mean_aqi", obj.get("aqi_mean"))),
            onset=onset,
            peak=peak,
            decay=decay,
            duration_hours=_as_float(obj.get("duration_hours")),
            phase=EpisodePhase.PEAK if obj.get("is_open") else EpisodePhase.DECAY,
            uncertainty=float(obj.get("uncertainty", 0.3)),
            station_coverage=float(
                obj.get("data_completeness", obj.get("station_coverage", 1.0))
            ),
            notes=list(obj.get("notes") or []),
            extra={"station_id": obj.get("station_id")},
        )

    # Duck-type EpisodeObject
    peak_cat = getattr(obj, "peak_category", None) or getattr(obj, "category_at_peak", None)
    severity = _coerce_severity(getattr(peak_cat, "value", peak_cat) or getattr(obj, "severity", None))
    return EpisodeOutput(
        episode_id=str(getattr(obj, "episode_id")),
        region="delhi-nct",
        severity=severity,
        aqi_peak=_as_float(getattr(obj, "peak_aqi", None)),
        aqi_mean=_as_float(getattr(obj, "mean_aqi", None)),
        onset=getattr(obj, "onset_at", None),
        peak=getattr(obj, "peak_at", None),
        decay=getattr(obj, "decay_at", None) or getattr(obj, "ended_at", None),
        duration_hours=_as_float(getattr(obj, "duration_hours", None)),
        phase=EpisodePhase.PEAK if getattr(obj, "is_open", False) else EpisodePhase.DECAY,
        uncertainty=float(getattr(obj, "uncertainty", 0.3)),
        station_coverage=float(getattr(obj, "data_completeness", 1.0)),
        notes=list(getattr(obj, "notes", []) or []),
        extra={"station_id": getattr(obj, "station_id", None)},
    )


def context_from_vector(obj: Any) -> ContextOutput:
    """Adapt ContextFeatureVector (or compatible mapping) into ContextOutput."""

    if isinstance(obj, ContextOutput):
        return obj
    if isinstance(obj, dict):
        if "fire_count_upwind" in obj or "is_stubble_season" in obj:
            try:
                return ContextOutput.model_validate(obj)
            except Exception:  # noqa: BLE001
                pass
        missing: list[str] = []
        wind = obj.get("wind_speed_ms")
        blh = obj.get("boundary_layer_height_m", obj.get("blh_m"))
        rh = obj.get("relative_humidity_pct", obj.get("relative_humidity"))
        wdir = obj.get("wind_direction_deg")
        if wind is None:
            missing.append("wind_speed_ms")
        if blh is None:
            missing.append("blh_m")
        if rh is None:
            missing.append("relative_humidity")
        if wdir is None:
            missing.append("wind_direction_deg")
        completeness = float(obj.get("feature_completeness", 1.0))
        return ContextOutput(
            region="delhi-nct",
            observed_at=obj.get("valid_at") or obj.get("observed_at"),
            fire_count_upwind=obj.get(
                "upwind_fire_count_24h", obj.get("fire_count_upwind", 0)
            ),
            wind_speed_ms=wind,
            wind_direction_deg=wdir,
            blh_m=blh,
            relative_humidity=rh,
            is_festival_window=bool(obj.get("is_festival", obj.get("is_festival_window", False))),
            is_stubble_season=bool(
                obj.get("is_delhi_winter_season", obj.get("is_stubble_season", False))
            ),
            missing_fields=missing,
            uncertainty=round(1.0 - completeness, 4),
            extra={
                "location_id": obj.get("location_id"),
                "upwind_fire_count_72h": obj.get("upwind_fire_count_72h"),
                "festival_name": obj.get("festival_name"),
            },
        )

    missing = []
    wind = getattr(obj, "wind_speed_ms", None)
    blh = getattr(obj, "boundary_layer_height_m", None)
    rh = getattr(obj, "relative_humidity_pct", None)
    wdir = getattr(obj, "wind_direction_deg", None)
    if wind is None:
        missing.append("wind_speed_ms")
    if blh is None:
        missing.append("blh_m")
    if rh is None:
        missing.append("relative_humidity")
    if wdir is None:
        missing.append("wind_direction_deg")
    completeness = float(getattr(obj, "feature_completeness", 1.0))
    return ContextOutput(
        region="delhi-nct",
        observed_at=getattr(obj, "valid_at", None),
        fire_count_upwind=int(getattr(obj, "upwind_fire_count_24h", 0) or 0),
        wind_speed_ms=wind,
        wind_direction_deg=wdir,
        blh_m=blh,
        relative_humidity=rh,
        is_festival_window=bool(getattr(obj, "is_festival", False)),
        is_stubble_season=bool(getattr(obj, "is_delhi_winter_season", False)),
        missing_fields=missing,
        uncertainty=round(1.0 - completeness, 4),
        extra={
            "location_id": getattr(obj, "location_id", None),
            "upwind_fire_count_72h": getattr(obj, "upwind_fire_count_72h", None),
            "festival_name": getattr(obj, "festival_name", None),
        },
    )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _coerce_severity(value: Any) -> EpisodeSeverity:
    if isinstance(value, EpisodeSeverity):
        return value
    if value is None:
        return EpisodeSeverity.MODERATE
    text = getattr(value, "value", value)
    text = str(text)
    for sev in EpisodeSeverity:
        if sev.value.lower() == text.lower() or sev.name.lower() == text.lower():
            return sev
    # Sibling uses severity strings like "Very Poor"
    mapping = {
        "very poor": EpisodeSeverity.VERY_POOR,
        "severe": EpisodeSeverity.SEVERE,
        "poor": EpisodeSeverity.POOR,
        "moderate": EpisodeSeverity.MODERATE,
    }
    return mapping.get(text.lower(), EpisodeSeverity.MODERATE)


def severity_to_aqi_proxy(severity: EpisodeSeverity) -> float | None:
    """Map CPCB category midpoints when a numeric AQI peak is unavailable."""

    return {
        EpisodeSeverity.GOOD: 25.0,
        EpisodeSeverity.SATISFACTORY: 75.0,
        EpisodeSeverity.MODERATE: 150.0,
        EpisodeSeverity.POOR: 250.0,
        EpisodeSeverity.VERY_POOR: 350.0,
        EpisodeSeverity.SEVERE: 425.0,
    }.get(severity)


def aqi_to_grap_stage(aqi: float | None, severity: EpisodeSeverity | None = None) -> GrapStage:
    """Map AQI (or severity fallback) to GRAP stage for advisory language only."""

    value = aqi
    if value is None and severity is not None:
        value = severity_to_aqi_proxy(severity)
    if value is None:
        return GrapStage.NONE
    if value > 450:
        return GrapStage.STAGE_IV
    if value >= 401:
        return GrapStage.STAGE_III
    if value >= 301:
        return GrapStage.STAGE_II
    if value >= 201:
        return GrapStage.STAGE_I
    return GrapStage.NONE
