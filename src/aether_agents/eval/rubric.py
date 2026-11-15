"""Case-study rubrics for winter episode attribution review.

Scores are structured expert-review criteria aligned with published festival,
stubble-transport, and stagnation case narratives. They are **not** a claim
of pollutant-level ground truth or certified source apportionment labels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from aether_agents.eval.fixtures import CASE_STUDIES, CaseStudyMeta


@dataclass(frozen=True)
class RubricCriterion:
    criterion_id: str
    title: str
    guidance: str
    max_score: int = 2  # 0 absent, 1 partial, 2 well-supported


@dataclass
class CriterionScore:
    criterion_id: str
    score: int
    notes: str = ""

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 2:
            raise ValueError(f"score must be in 0..2, got {self.score}")


@dataclass
class CaseStudyScorecard:
    case_id: str
    scores: list[CriterionScore] = field(default_factory=list)
    reviewer: str = ""
    overall_notes: str = ""

    @property
    def total(self) -> int:
        return sum(s.score for s in self.scores)

    @property
    def max_total(self) -> int:
        return 2 * len(self.scores)

    @property
    def normalized(self) -> float | None:
        if not self.scores:
            return None
        return self.total / self.max_total

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "reviewer": self.reviewer,
            "overall_notes": self.overall_notes,
            "total": self.total,
            "max_total": self.max_total,
            "normalized": self.normalized,
            "scores": [asdict(s) for s in self.scores],
            "disclaimer": (
                "Rubric scores reflect structured literature-aligned review, "
                "not fabricated measurement ground truth."
            ),
        }


# Shared dimensions across case types.
_COMMON: tuple[RubricCriterion, ...] = (
    RubricCriterion(
        "temporal_alignment",
        "Temporal alignment",
        "Detected episode onset/peak/decay overlaps the published case window "
        "without requiring exact hour-level truth.",
    ),
    RubricCriterion(
        "evidence_citation",
        "Evidence citation",
        "Source-class claims cite concrete features (AQI trajectory, fires, "
        "winds, BLH, calendar hooks) rather than unsupported assertions.",
    ),
    RubricCriterion(
        "uncertainty_language",
        "Uncertainty language",
        "Uncertainty widens under missing data or conflicting signals; "
        "no overconfident single-cause claims.",
    ),
    RubricCriterion(
        "grap_appropriateness",
        "GRAP-relevant framing",
        "Advisory language maps to GRAP-stage style guidance without inventing "
        "legal orders or agency directives.",
    ),
)

_CASE_SPECIFIC: dict[str, tuple[RubricCriterion, ...]] = {
    "diwali": (
        RubricCriterion(
            "local_combustion_prior",
            "Local combustion prior",
            "Festival window elevates local combustion / mixed classes; "
            "distant-fire-only explanations are down-weighted.",
        ),
        RubricCriterion(
            "short_duration_handling",
            "Short-duration handling",
            "Multi-day festival spike is distinguished from multi-week "
            "regional transport seasons.",
        ),
    ),
    "stubble": (
        RubricCriterion(
            "transport_fire_consistency",
            "Transport / fire consistency",
            "Upwind fire counts and wind context support a stubble/transport "
            "contribution when claimed.",
        ),
        RubricCriterion(
            "mixture_acknowledgment",
            "Mixture acknowledgment",
            "Attribution allows mixed local + regional contributions rather "
            "than forcing a single exclusive class.",
        ),
    ),
    "stagnation": (
        RubricCriterion(
            "meteorology_emphasis",
            "Meteorology emphasis",
            "Low BLH / weak winds are cited when arguing local accumulation.",
        ),
        RubricCriterion(
            "fire_overattribution_guard",
            "Fire over-attribution guard",
            "Low upwind fire activity is not spun into a transport narrative.",
        ),
    ),
}


def criteria_for_case(case_id: str) -> list[RubricCriterion]:
    if case_id not in _CASE_SPECIFIC:
        known = ", ".join(sorted(_CASE_SPECIFIC))
        raise KeyError(f"Unknown case_id={case_id!r}; expected one of: {known}")
    return list(_COMMON) + list(_CASE_SPECIFIC[case_id])


def case_meta(case_id: str) -> CaseStudyMeta:
    for c in CASE_STUDIES:
        if c.case_id == case_id:
            return c
    raise KeyError(case_id)


def rubric_catalog() -> dict[str, Any]:
    """Export full rubric text for methods notes / notebooks."""
    return {
        "disclaimer": (
            "Case-study rubrics support transparent expert review against "
            "historical winter narratives and CAQM/GRAP timelines. They do "
            "not constitute measurement ground truth or certified source "
            "apportionment labels."
        ),
        "cases": {
            c.case_id: {
                "label": c.label,
                "narrative": c.narrative,
                "expected_source_classes": list(c.expected_source_classes),
                "literature_hooks": list(c.literature_hooks),
                "window_hours": [c.window_start, c.window_end],
                "criteria": [asdict(cr) for cr in criteria_for_case(c.case_id)],
            }
            for c in CASE_STUDIES
        },
    }


def score_case_study(
    case_id: str,
    scores: Mapping[str, int] | Sequence[CriterionScore],
    *,
    reviewer: str = "",
    overall_notes: str = "",
) -> CaseStudyScorecard:
    """Build a scorecard; ``scores`` may be criterion_id→int or CriterionScore list."""
    criteria = criteria_for_case(case_id)
    allowed = {c.criterion_id for c in criteria}

    if isinstance(scores, Mapping):
        unknown = set(scores) - allowed
        if unknown:
            raise KeyError(f"Unknown criterion ids: {sorted(unknown)}")
        missing = allowed - set(scores)
        if missing:
            raise KeyError(f"Missing criterion ids: {sorted(missing)}")
        scored = [CriterionScore(cid, int(scores[cid])) for cid in (c.criterion_id for c in criteria)]
    else:
        scored = list(scores)
        got = {s.criterion_id for s in scored}
        if got != allowed:
            raise KeyError(f"Criterion set mismatch: got={sorted(got)} expected={sorted(allowed)}")

    return CaseStudyScorecard(
        case_id=case_id,
        scores=scored,
        reviewer=reviewer,
        overall_notes=overall_notes,
    )


def demo_scorecards() -> list[CaseStudyScorecard]:
    """Illustrative completed rubrics for the offline notebook (not real audits)."""
    return [
        score_case_study(
            "diwali",
            {
                "temporal_alignment": 2,
                "evidence_citation": 2,
                "uncertainty_language": 1,
                "grap_appropriateness": 2,
                "local_combustion_prior": 2,
                "short_duration_handling": 2,
            },
            reviewer="methods-demo",
            overall_notes="Demo scores for notebook reproducibility only.",
        ),
        score_case_study(
            "stubble",
            {
                "temporal_alignment": 2,
                "evidence_citation": 1,
                "uncertainty_language": 2,
                "grap_appropriateness": 2,
                "transport_fire_consistency": 2,
                "mixture_acknowledgment": 2,
            },
            reviewer="methods-demo",
            overall_notes="Demo scores for notebook reproducibility only.",
        ),
        score_case_study(
            "stagnation",
            {
                "temporal_alignment": 2,
                "evidence_citation": 2,
                "uncertainty_language": 2,
                "grap_appropriateness": 1,
                "meteorology_emphasis": 2,
                "fire_overattribution_guard": 2,
            },
            reviewer="methods-demo",
            overall_notes="Demo scores for notebook reproducibility only.",
        ),
    ]
