"""CriticAgent: consistency checks, missing-data penalties, fail-closed dominant.

Fail-closed policy (v1):
- If evidence is sparse (many missing fields and/or very low station coverage),
  refuse a dominant source hypothesis: set ``dominant_refused=True``,
  ``revised_dominant_class=None``, shrink toward uniform, and force high uncertainty.
- Consistency warnings still dampen confidence even when not refusing.
"""

from __future__ import annotations

from aether_agents.agents.evidence import (
    SOURCE_CLASS_LABELS,
    AttributionPosterior,
    AttributionResult,
    ContextOutput,
    CriticFinding,
    CriticResult,
    EpisodeOutput,
    SourceClass,
)
from aether_agents.config import Settings, get_settings

# Fail-closed thresholds (documented, tunable).
_SPARSE_MISSING_FEATURES = 4
_SPARSE_COVERAGE = 0.35
_SPARSE_NON_MISSING_EVIDENCE = 3


def _feat_map(attribution: AttributionResult) -> dict[str, object]:
    out: dict[str, object] = {}
    for feat in attribution.evidence:
        if feat.missing:
            out[feat.name] = None
        else:
            out[feat.name] = feat.value
    return out


def _renormalize(posteriors: list[AttributionPosterior]) -> list[AttributionPosterior]:
    total = sum(p.probability for p in posteriors) or 1.0
    revised: list[AttributionPosterior] = []
    for p in posteriors:
        revised.append(
            p.model_copy(update={"probability": round(p.probability / total, 4)})
        )
    revised.sort(key=lambda p: p.probability, reverse=True)
    return revised


def _shrink_toward_uniform(
    posteriors: list[AttributionPosterior], dampening: float
) -> list[AttributionPosterior]:
    """Mix posterior with uniform prior; dampening in [0, 1]."""

    n = len(posteriors) or 1
    uniform = 1.0 / n
    alpha = max(0.0, min(1.0, dampening))
    mixed: list[AttributionPosterior] = []
    for p in posteriors:
        new_p = (1.0 - alpha) * p.probability + alpha * uniform
        mixed.append(p.model_copy(update={"probability": new_p}))
    return _renormalize(mixed)


def _is_sparse(
    attribution: AttributionResult,
    episode: EpisodeOutput,
    context: ContextOutput,
) -> tuple[bool, str]:
    missing_names = [
        e.name for e in attribution.evidence if e.missing
    ] + list(context.missing_fields)
    missing_unique = sorted(set(missing_names))
    evidence_count = sum(1 for e in attribution.evidence if not e.missing)

    reasons: list[str] = []
    if len(missing_unique) >= _SPARSE_MISSING_FEATURES:
        reasons.append(f"missing_features>={_SPARSE_MISSING_FEATURES}")
    if episode.station_coverage < _SPARSE_COVERAGE:
        reasons.append(f"station_coverage<{_SPARSE_COVERAGE}")
    if evidence_count < _SPARSE_NON_MISSING_EVIDENCE:
        reasons.append(f"non_missing_evidence<{_SPARSE_NON_MISSING_EVIDENCE}")

    # Require at least two sparse signals, or coverage alone extremely low.
    if episode.station_coverage < 0.2:
        return True, "station_coverage<0.2"
    if len(reasons) >= 2:
        return True, ";".join(reasons)
    if len(missing_unique) >= 5 and evidence_count < 5:
        return True, "heavy_missing_and_thin_evidence"
    return False, ""


class CriticAgent:
    """Revise attribution uncertainty; refuse dominant source when sparse."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(
        self,
        attribution: AttributionResult,
        episode: EpisodeOutput,
        context: ContextOutput,
    ) -> CriticResult:
        findings: list[CriticFinding] = []
        feats = _feat_map(attribution)
        missing_penalty = 0.0
        dampening = 0.0
        dominant_refused = False

        # --- Missing data ---
        missing_names = [
            e.name for e in attribution.evidence if e.missing
        ] + list(context.missing_fields)
        missing_unique = sorted(set(missing_names))
        if missing_unique:
            missing_penalty = min(0.45, 0.08 * len(missing_unique))
            findings.append(
                CriticFinding(
                    code="missing_data",
                    severity="warn",
                    message="Missing evidence fields: " + ", ".join(missing_unique),
                    penalty=missing_penalty,
                )
            )

        if episode.station_coverage < 0.5:
            cov_pen = 0.15 if episode.station_coverage >= 0.3 else 0.25
            missing_penalty = min(0.6, missing_penalty + cov_pen)
            findings.append(
                CriticFinding(
                    code="low_station_coverage",
                    severity="warn",
                    message=(
                        f"Station coverage {episode.station_coverage:.2f} "
                        "limits spatial representativeness."
                    ),
                    penalty=cov_pen,
                )
            )

        # --- Fail closed on sparse data ---
        sparse, sparse_reason = _is_sparse(attribution, episode, context)
        if sparse:
            dominant_refused = True
            dampening = max(dampening, 0.85)
            missing_penalty = max(missing_penalty, 0.5)
            findings.append(
                CriticFinding(
                    code="refuse_dominant_sparse_data",
                    severity="error",
                    message=(
                        "Fail-closed: evidence too sparse to assert a dominant "
                        f"source ({sparse_reason}). Dominant source refused."
                    ),
                    penalty=0.5,
                )
            )

        # --- Consistency checks ---
        fires = feats.get("fire_count_upwind")
        dominant = attribution.dominant_class

        if dominant == SourceClass.TRANSPORT_STUBBLE and (
            fires is None or (isinstance(fires, (int, float)) and fires < 3)
        ):
            pen = 0.2
            dampening += 0.25
            findings.append(
                CriticFinding(
                    code="stubble_without_fires",
                    severity="warn",
                    message=(
                        "Transport/stubble dominant but upwind fire evidence is "
                        "weak or missing."
                    ),
                    penalty=pen,
                )
            )

        wind_spd = feats.get("wind_speed_ms")
        if dominant == SourceClass.LOCAL_COMBUSTION and isinstance(wind_spd, (int, float)):
            if wind_spd >= 5.0:
                dampening += 0.2
                findings.append(
                    CriticFinding(
                        code="local_with_strong_winds",
                        severity="warn",
                        message=(
                            "Local combustion dominant despite strong winds "
                            f"({wind_spd} m/s); check transport alternatives."
                        ),
                        penalty=0.15,
                    )
                )

        if dominant == SourceClass.DUST and isinstance(wind_spd, (int, float)):
            if wind_spd < 3.0:
                dampening += 0.2
                findings.append(
                    CriticFinding(
                        code="dust_with_calm_winds",
                        severity="warn",
                        message="Dust dominant under calm winds is inconsistent.",
                        penalty=0.15,
                    )
                )

        blh = feats.get("blh_m")
        if dominant == SourceClass.LOCAL_COMBUSTION and blh is None:
            dampening += 0.1
            findings.append(
                CriticFinding(
                    code="local_missing_blh",
                    severity="info",
                    message="Local combustion hypothesis lacks BLH confirmation.",
                    penalty=0.05,
                )
            )

        # --- Overconfidence dampening ---
        top = attribution.posteriors[0].probability if attribution.posteriors else 0.0
        evidence_count = sum(1 for e in attribution.evidence if not e.missing)
        if top >= 0.55 and evidence_count < 5:
            extra = min(0.35, (top - 0.5) * 0.8)
            dampening += extra
            findings.append(
                CriticFinding(
                    code="overconfidence",
                    severity="warn",
                    message=(
                        f"Peak mass {top:.2f} with only {evidence_count} "
                        "non-missing features; shrinking toward uniform."
                    ),
                    penalty=extra,
                )
            )
        elif top >= 0.7:
            extra = 0.12
            dampening += extra
            findings.append(
                CriticFinding(
                    code="high_peak_posterior",
                    severity="info",
                    message=f"Peak mass {top:.2f}; applying mild dampening.",
                    penalty=extra,
                )
            )

        dampening = min(0.95, dampening + 0.5 * missing_penalty)
        revised = _shrink_toward_uniform(attribution.posteriors, dampening)
        revised = [
            p.model_copy(update={"label": SOURCE_CLASS_LABELS[p.source_class]})
            for p in revised
        ]

        if dominant_refused:
            revised_dominant: SourceClass | None = None
            revised_confidence = float(
                max(0.05, min(0.25, attribution.confidence * 0.3))
            )
        else:
            revised_dominant = revised[0].source_class
            revised_confidence = float(
                max(
                    0.05,
                    min(
                        0.95,
                        attribution.confidence
                        * (1.0 - missing_penalty)
                        * (1.0 - 0.5 * dampening),
                    ),
                )
            )

        notes: list[str] = []
        if dominant_refused:
            notes.append(
                "dominant_source refused (fail-closed); treat class masses as "
                "uninformative under sparse evidence."
            )
        if self.settings.llm_enabled and not self.settings.llm_api_key:
            notes.append("LLM enabled but LLM_API_KEY missing; critic used rule_score path.")
        if not findings:
            findings.append(
                CriticFinding(
                    code="consistent",
                    severity="info",
                    message="No material consistency issues detected.",
                    penalty=0.0,
                )
            )

        return CriticResult(
            episode_id=attribution.episode_id,
            revised_posteriors=revised,
            revised_dominant_class=revised_dominant,
            revised_confidence=round(revised_confidence, 4),
            dominant_refused=dominant_refused,
            findings=findings,
            missing_data_penalty=round(missing_penalty, 4),
            overconfidence_dampening=round(dampening, 4),
            method="rule_score",
            notes=notes,
        )


def critique_attribution(
    attribution: AttributionResult,
    episode: EpisodeOutput,
    context: ContextOutput,
    settings: Settings | None = None,
) -> CriticResult:
    return CriticAgent(settings=settings).run(attribution, episode, context)
