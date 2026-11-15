"""Evidence-weighted AttributionAgent for Delhi–NCT winter source classes.

Default path is deterministic rule/score-based. Optional LLM enrichment is gated
by AETHER_LLM_ENABLED and never required for a valid result.

Outputs include a transparent **scorecard** (feature → weight → contribution)
so heuristic increments are reproducible. Softmax probabilities are **not**
calibrated Bayesian posteriors.
"""

from __future__ import annotations

import math
from typing import Iterable

from aether_agents.agents.evidence import (
    SOURCE_CLASS_LABELS,
    AttributionPosterior,
    AttributionResult,
    ContextOutput,
    EpisodeOutput,
    EpisodeSeverity,
    EvidenceFeature,
    ScoreContribution,
    SourceClass,
)
from aether_agents.config import Settings, get_settings

# NW–N transport corridor typical for Punjab/Haryana stubble plumes into Delhi.
_STUBBLE_WIND_DIRS = frozenset(range(280, 361)) | frozenset(range(0, 46))


def _softmax(scores: dict[SourceClass, float], temperature: float = 1.0) -> dict[SourceClass, float]:
    temp = max(temperature, 1e-6)
    shifted = {k: v / temp for k, v in scores.items()}
    peak = max(shifted.values()) if shifted else 0.0
    exps = {k: math.exp(v - peak) for k, v in shifted.items()}
    total = sum(exps.values()) or 1.0
    return {k: exps[k] / total for k in scores}


def _is_missing(value: object | None) -> bool:
    return value is None


def _feature(
    name: str,
    value: float | str | bool | None,
    *,
    source: str,
    citation: str,
    unit: str | None = None,
    weight: float = 1.0,
    confidence: float = 1.0,
    missing: bool = False,
) -> EvidenceFeature:
    return EvidenceFeature(
        name=name,
        value=value,
        unit=unit,
        source=source,
        citation=citation,
        weight=weight,
        confidence=confidence if not missing else 0.0,
        missing=missing,
    )


def _collect_evidence(episode: EpisodeOutput, context: ContextOutput) -> list[EvidenceFeature]:
    features: list[EvidenceFeature] = list(context.features)

    features.append(
        _feature(
            "aqi_peak",
            episode.aqi_peak,
            source="episode",
            citation="EpisodeAgent peak AQI (CPCB category rules)",
            unit="AQI",
            weight=1.2,
            missing=_is_missing(episode.aqi_peak),
        )
    )
    features.append(
        _feature(
            "severity",
            episode.severity.value,
            source="episode",
            citation="EpisodeAgent CPCB-aligned severity label",
            weight=1.0,
        )
    )
    features.append(
        _feature(
            "station_coverage",
            episode.station_coverage,
            source="episode",
            citation="Fraction of expected Delhi–NCT stations with usable AQI",
            weight=0.8,
            missing=episode.station_coverage < 0.4,
        )
    )
    features.append(
        _feature(
            "fire_count_upwind",
            context.fire_count_upwind,
            source="firms",
            citation="NASA FIRMS upwind fire count (ContextAgent)",
            weight=1.4,
            missing=_is_missing(context.fire_count_upwind),
        )
    )
    features.append(
        _feature(
            "wind_speed_ms",
            context.wind_speed_ms,
            source="openmeteo",
            citation="Near-surface wind speed (ContextAgent / Open-Meteo)",
            unit="m/s",
            weight=1.0,
            missing=_is_missing(context.wind_speed_ms),
        )
    )
    features.append(
        _feature(
            "wind_direction_deg",
            context.wind_direction_deg,
            source="openmeteo",
            citation="Wind direction from which air arrives (ContextAgent)",
            unit="deg",
            weight=1.0,
            missing=_is_missing(context.wind_direction_deg),
        )
    )
    features.append(
        _feature(
            "blh_m",
            context.blh_m,
            source="openmeteo",
            citation="Boundary-layer height (ContextAgent)",
            unit="m",
            weight=1.1,
            missing=_is_missing(context.blh_m),
        )
    )
    features.append(
        _feature(
            "relative_humidity",
            context.relative_humidity,
            source="openmeteo",
            citation="Relative humidity (ContextAgent)",
            unit="%",
            weight=0.7,
            missing=_is_missing(context.relative_humidity),
        )
    )
    features.append(
        _feature(
            "is_stubble_season",
            context.is_stubble_season,
            source="calendar",
            citation="Post-monsoon stubble season window (approx. Oct–Nov)",
            weight=1.0,
        )
    )
    features.append(
        _feature(
            "is_festival_window",
            context.is_festival_window,
            source="calendar",
            citation="Festival / fireworks calendar hook (e.g. Diwali window)",
            weight=1.0,
        )
    )
    if context.is_weekday is not None:
        features.append(
            _feature(
                "is_weekday",
                context.is_weekday,
                source="calendar",
                citation="Weekday industrial activity prior",
                weight=0.5,
            )
        )

    seen: set[str] = set()
    unique: list[EvidenceFeature] = []
    for feat in features:
        if feat.name in seen:
            continue
        seen.add(feat.name)
        unique.append(feat)
    return unique


def _supporting(
    evidence: Iterable[EvidenceFeature], names: Iterable[str]
) -> list[EvidenceFeature]:
    wanted = set(names)
    return [e for e in evidence if e.name in wanted and not e.missing]


def _add(
    scorecard: list[ScoreContribution],
    scores: dict[SourceClass, float],
    *,
    source_class: SourceClass,
    feature: str,
    feature_value: float | str | bool | None,
    weight: float,
    contribution: float,
    rule: str,
) -> None:
    if contribution == 0.0:
        return
    scores[source_class] += contribution
    scorecard.append(
        ScoreContribution(
            source_class=source_class,
            feature=feature,
            feature_value=feature_value,
            weight=weight,
            contribution=round(contribution, 4),
            rule=rule,
        )
    )


def _score_classes(
    episode: EpisodeOutput, context: ContextOutput, evidence: list[EvidenceFeature]
) -> tuple[dict[SourceClass, float], list[ScoreContribution]]:
    scores: dict[SourceClass, float] = {cls: 0.15 for cls in SourceClass}
    scores[SourceClass.MIXED] = 0.05
    scorecard: list[ScoreContribution] = []

    # Baseline prior rows (transparent).
    for cls, base in scores.items():
        scorecard.append(
            ScoreContribution(
                source_class=cls,
                feature="prior_base",
                feature_value=base,
                weight=1.0,
                contribution=round(base, 4),
                rule="uniform-ish class prior before evidence rules",
            )
        )

    fires = context.fire_count_upwind
    wind_dir = context.wind_direction_deg
    wind_spd = context.wind_speed_ms
    blh = context.blh_m
    rh = context.relative_humidity
    aqi = episode.aqi_peak

    # Transport / stubble
    if fires is not None and fires >= 20:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.TRANSPORT_STUBBLE,
            feature="fire_count_upwind",
            feature_value=fires,
            weight=1.4,
            contribution=1.6,
            rule="fires>=20 → strong transport/stubble prior",
        )
    elif fires is not None and fires >= 5:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.TRANSPORT_STUBBLE,
            feature="fire_count_upwind",
            feature_value=fires,
            weight=1.4,
            contribution=0.8,
            rule="fires>=5 → moderate transport/stubble prior",
        )
    if context.is_stubble_season:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.TRANSPORT_STUBBLE,
            feature="is_stubble_season",
            feature_value=True,
            weight=1.0,
            contribution=0.9,
            rule="Oct–Nov stubble season calendar window",
        )
    if wind_dir is not None and int(wind_dir) % 360 in _STUBBLE_WIND_DIRS:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.TRANSPORT_STUBBLE,
            feature="wind_direction_deg",
            feature_value=wind_dir,
            weight=1.0,
            contribution=0.7,
            rule="NW–N wind sector favorable for Punjab/Haryana transport",
        )
    if wind_spd is not None and 1.5 <= wind_spd <= 6.0 and (fires or 0) >= 5:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.TRANSPORT_STUBBLE,
            feature="wind_speed_ms",
            feature_value=wind_spd,
            weight=1.0,
            contribution=0.4,
            rule="moderate winds + fires support plume transport",
        )

    # Local combustion
    if blh is not None and blh < 400:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="blh_m",
            feature_value=blh,
            weight=1.1,
            contribution=1.2,
            rule="BLH<400m favors local accumulation",
        )
    elif blh is not None and blh < 700:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="blh_m",
            feature_value=blh,
            weight=1.1,
            contribution=0.6,
            rule="BLH<700m mild local accumulation prior",
        )
    if wind_spd is not None and wind_spd < 1.5:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="wind_speed_ms",
            feature_value=wind_spd,
            weight=1.0,
            contribution=1.0,
            rule="calm winds (<1.5 m/s) favor local combustion",
        )
    elif wind_spd is not None and wind_spd < 2.5:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="wind_speed_ms",
            feature_value=wind_spd,
            weight=1.0,
            contribution=0.4,
            rule="light winds (<2.5 m/s) mild local prior",
        )
    if rh is not None and rh >= 70:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="relative_humidity",
            feature_value=rh,
            weight=0.7,
            contribution=0.5,
            rule="RH>=70% winter chemistry / stagnation proxy",
        )
    if context.is_festival_window:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="is_festival_window",
            feature_value=True,
            weight=1.0,
            contribution=1.1,
            rule="festival/fireworks calendar window",
        )
    if fires is not None and fires < 3:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="fire_count_upwind",
            feature_value=fires,
            weight=1.4,
            contribution=0.3,
            rule="weak fire signal reduces transport preference",
        )

    # Dust
    if wind_spd is not None and wind_spd >= 6.0:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.DUST,
            feature="wind_speed_ms",
            feature_value=wind_spd,
            weight=1.0,
            contribution=1.3,
            rule="strong winds (>=6 m/s) favor dust / resuspension",
        )
    if rh is not None and rh <= 35:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.DUST,
            feature="relative_humidity",
            feature_value=rh,
            weight=0.7,
            contribution=0.8,
            rule="dry air (RH<=35%) favors dust",
        )
    if blh is not None and blh >= 1200:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.DUST,
            feature="blh_m",
            feature_value=blh,
            weight=1.1,
            contribution=0.4,
            rule="deep BLH consistent with dust mixing",
        )
    if episode.severity in {EpisodeSeverity.MODERATE, EpisodeSeverity.POOR} and (
        wind_spd is not None and wind_spd >= 5.0
    ):
        _add(
            scorecard,
            scores,
            source_class=SourceClass.DUST,
            feature="severity",
            feature_value=episode.severity.value,
            weight=1.0,
            contribution=0.3,
            rule="moderate/poor + strong wind mild dust prior",
        )

    # Industrial
    if context.is_weekday is True:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.INDUSTRIAL,
            feature="is_weekday",
            feature_value=True,
            weight=0.5,
            contribution=0.6,
            rule="weekday industrial activity prior",
        )
    if aqi is not None and 200 <= aqi < 350 and (fires is None or fires < 5):
        _add(
            scorecard,
            scores,
            source_class=SourceClass.INDUSTRIAL,
            feature="aqi_peak",
            feature_value=aqi,
            weight=1.2,
            contribution=0.5,
            rule="moderate-severe AQI with limited fires",
        )
    if wind_spd is not None and 2.0 <= wind_spd <= 5.0 and not context.is_stubble_season:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.INDUSTRIAL,
            feature="wind_speed_ms",
            feature_value=wind_spd,
            weight=1.0,
            contribution=0.3,
            rule="moderate winds outside stubble season",
        )

    # Mixed
    non_mixed = {k: v for k, v in scores.items() if k != SourceClass.MIXED}
    ranked = sorted(non_mixed.values(), reverse=True)
    if len(ranked) >= 2 and ranked[0] >= 1.5 and ranked[1] >= 1.2:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.MIXED,
            feature="multi_class_strength",
            feature_value=f"top={ranked[0]:.2f},second={ranked[1]:.2f}",
            weight=1.0,
            contribution=1.4,
            rule="two non-mixed classes both strong → mixed",
        )
    if context.is_stubble_season and context.is_festival_window:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.MIXED,
            feature="is_stubble_season+is_festival_window",
            feature_value=True,
            weight=1.0,
            contribution=0.8,
            rule="overlapping stubble + festival windows",
        )

    if episode.severity == EpisodeSeverity.SEVERE:
        _add(
            scorecard,
            scores,
            source_class=SourceClass.MIXED,
            feature="severity",
            feature_value=episode.severity.value,
            weight=1.0,
            contribution=0.35,
            rule="severe episodes often multi-source",
        )
        _add(
            scorecard,
            scores,
            source_class=SourceClass.LOCAL_COMBUSTION,
            feature="severity",
            feature_value=episode.severity.value,
            weight=1.0,
            contribution=0.2,
            rule="severe episode mild local bump",
        )
        _add(
            scorecard,
            scores,
            source_class=SourceClass.TRANSPORT_STUBBLE,
            feature="severity",
            feature_value=episode.severity.value,
            weight=1.0,
            contribution=0.15,
            rule="severe episode mild transport bump",
        )

    _ = evidence
    return scores, scorecard


def _build_posteriors(
    probs: dict[SourceClass, float],
    scores: dict[SourceClass, float],
    evidence: list[EvidenceFeature],
) -> list[AttributionPosterior]:
    support_map: dict[SourceClass, list[str]] = {
        SourceClass.TRANSPORT_STUBBLE: [
            "fire_count_upwind",
            "is_stubble_season",
            "wind_direction_deg",
            "wind_speed_ms",
        ],
        SourceClass.LOCAL_COMBUSTION: [
            "blh_m",
            "wind_speed_ms",
            "relative_humidity",
            "is_festival_window",
            "fire_count_upwind",
        ],
        SourceClass.DUST: ["wind_speed_ms", "relative_humidity", "blh_m", "severity"],
        SourceClass.INDUSTRIAL: ["is_weekday", "aqi_peak", "wind_speed_ms", "fire_count_upwind"],
        SourceClass.MIXED: [
            "severity",
            "is_stubble_season",
            "is_festival_window",
            "fire_count_upwind",
            "blh_m",
        ],
    }
    rationale_map: dict[SourceClass, str] = {
        SourceClass.TRANSPORT_STUBBLE: (
            "Elevated upwind fire activity and/or NW–N transport-favorable winds "
            "during the stubble season."
        ),
        SourceClass.LOCAL_COMBUSTION: (
            "Shallow boundary layer and/or calm winds favor local combustion "
            "accumulation (traffic, heating, festival emissions)."
        ),
        SourceClass.DUST: (
            "Strong winds and dry air favor dust / resuspended particulate "
            "contributions over stagnant smoke."
        ),
        SourceClass.INDUSTRIAL: (
            "Weekday / moderate-severe patterns with limited fire signal "
            "support an industrial contribution hypothesis."
        ),
        SourceClass.MIXED: (
            "Multiple source classes score strongly; evidence does not isolate "
            "a single dominant process."
        ),
    }

    posteriors: list[AttributionPosterior] = []
    for cls in SourceClass:
        posteriors.append(
            AttributionPosterior(
                source_class=cls,
                label=SOURCE_CLASS_LABELS[cls],
                probability=round(probs[cls], 4),
                raw_score=round(scores[cls], 4),
                supporting_evidence=_supporting(evidence, support_map[cls]),
                rationale=rationale_map[cls],
            )
        )
    posteriors.sort(key=lambda p: p.probability, reverse=True)
    return posteriors


def _confidence_from_probs(
    probs: dict[SourceClass, float],
    episode: EpisodeOutput,
    context: ContextOutput,
) -> float:
    ordered = sorted(probs.values(), reverse=True)
    margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
    coverage = episode.station_coverage
    missing_frac = len(context.missing_fields) / max(len(context.missing_fields) + 6, 1)
    base = 0.35 + 0.45 * margin + 0.2 * coverage
    base *= 1.0 - 0.4 * missing_frac
    base *= 1.0 - 0.25 * episode.uncertainty - 0.15 * context.uncertainty
    return float(max(0.05, min(0.95, base)))


def _optional_llm_note(settings: Settings) -> str | None:
    if not settings.llm_enabled:
        return None
    if not settings.llm_api_key:
        return "LLM enabled but LLM_API_KEY missing; retained rule_score scores."
    return (
        "LLM flag on: structured evidence retained on rule_score path "
        "(live LLM adapter not invoked in deterministic mode)."
    )


class AttributionAgent:
    """Score source-class hypotheses from Episode + Context evidence."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, episode: EpisodeOutput, context: ContextOutput) -> AttributionResult:
        evidence = _collect_evidence(episode, context)
        scores, scorecard = _score_classes(episode, context, evidence)
        probs = _softmax(scores, temperature=0.85)
        posteriors = _build_posteriors(probs, scores, evidence)
        dominant = posteriors[0].source_class
        confidence = _confidence_from_probs(probs, episode, context)

        notes: list[str] = [
            "probabilities=softmax(heuristic_raw_scores); not calibrated posteriors",
            "scorecard lists feature→weight→contribution for each fired rule",
        ]
        llm_note = _optional_llm_note(self.settings)
        if llm_note:
            notes.append(llm_note)
        if episode.station_coverage < 0.5:
            notes.append("Low station coverage; attribution confidence reduced.")
        if context.missing_fields:
            notes.append(
                "Context missing fields: " + ", ".join(sorted(set(context.missing_fields)))
            )

        return AttributionResult(
            episode_id=episode.episode_id,
            region=episode.region or context.region,
            posteriors=posteriors,
            dominant_class=dominant,
            confidence=round(confidence, 4),
            evidence=evidence,
            scorecard=scorecard,
            method="rule_score",
            notes=notes,
        )


def attribute_episode(
    episode: EpisodeOutput,
    context: ContextOutput,
    settings: Settings | None = None,
) -> AttributionResult:
    return AttributionAgent(settings=settings).run(episode, context)
