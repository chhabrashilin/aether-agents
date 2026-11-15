"""AdvisoryAgent: GRAP *alignment-band* advisory JSON with exposure guidance.

Never invents legal orders or CAQM directives. Stage language is research
alignment with publicly described AQI bands only. Official sources:
https://caqm.nic.in/
"""

from __future__ import annotations

from aether_agents.agents.evidence import (
    SOURCE_CLASS_LABELS,
    CAQM_GRAP_DOC_NOTE,
    CAQM_GRAP_URL,
    AdvisoryResult,
    CriticResult,
    EpisodeOutput,
    EpisodeSeverity,
    ExposureGuidance,
    GrapStage,
    aqi_to_grap_stage,
)
from aether_agents.config import Settings, get_settings

_GRAP_LABELS: dict[GrapStage, str] = {
    GrapStage.NONE: "Below GRAP Stage I alignment band (AQI < Poor)",
    GrapStage.STAGE_I: "GRAP Stage I alignment band (Poor AQI ≈ 201–300)",
    GrapStage.STAGE_II: "GRAP Stage II alignment band (Very Poor AQI ≈ 301–400)",
    GrapStage.STAGE_III: "GRAP Stage III alignment band (Severe AQI ≈ 401–450)",
    GrapStage.STAGE_IV: "GRAP Stage IV alignment band (Severe+ / extreme AQI > 450)",
}

_CITATION_BASE = [
    CAQM_GRAP_DOC_NOTE,
    "CPCB National Air Quality Index categories",
    CAQM_GRAP_URL,
]


def _exposure_for_stage(
    stage: GrapStage, severity: EpisodeSeverity | None, citations: list[str]
) -> list[ExposureGuidance]:
    common = list(citations)
    if stage == GrapStage.NONE:
        return [
            ExposureGuidance(
                audience="general_public",
                guidance=(
                    "AQI is below the Poor band used for GRAP Stage I *alignment*. "
                    "Routine outdoor activity is generally acceptable for most people; "
                    "sensitive individuals should still track local AQI. "
                    "This is not an official clearance."
                ),
                citations=common,
            )
        ]

    items: list[ExposureGuidance] = [
        ExposureGuidance(
            audience="general_public",
            guidance=(
                "Limit prolonged outdoor exertion. Prefer indoor activity when AQI "
                f"is in the {severity.value if severity else 'elevated'} range. "
                "This is exposure guidance only, not a legal restriction or CAQM order."
            ),
            citations=common,
        ),
        ExposureGuidance(
            audience="sensitive_groups",
            guidance=(
                "Children, older adults, and people with respiratory or cardiac "
                "conditions should minimize outdoor exposure and consider N95/equivalent "
                "filtration if outdoors is unavoidable. Follow official notifications."
            ),
            citations=common,
        ),
    ]

    if stage in {GrapStage.STAGE_III, GrapStage.STAGE_IV}:
        items.append(
            ExposureGuidance(
                audience="schools_and_outdoor_workers",
                guidance=(
                    "Research alignment notes that GRAP Stage III/IV public plans "
                    "historically emphasize curtailing intense outdoor activity. "
                    "Only CAQM / state notifications create enforceable measures; "
                    f"see {CAQM_GRAP_URL}."
                ),
                citations=common,
            )
        )
    return items


def _summary(
    stage: GrapStage,
    episode: EpisodeOutput,
    critic: CriticResult,
) -> str:
    aqi_txt = f"{episode.aqi_peak:.0f}" if episode.aqi_peak is not None else "unspecified"
    stage_txt = _GRAP_LABELS[stage]
    if critic.dominant_refused or critic.revised_dominant_class is None:
        source_txt = (
            "no dominant source asserted (critic fail-closed under sparse/uncertain data)"
        )
    else:
        label = SOURCE_CLASS_LABELS[critic.revised_dominant_class]
        source_txt = (
            f"heuristic source hypothesis: {label} "
            f"(confidence {critic.revised_confidence:.2f}; not calibrated)"
        )
    return (
        f"Episode {episode.episode_id} ({episode.severity.value}, peak AQI {aqi_txt}) "
        f"maps to {stage_txt}. Critic: {source_txt}. "
        "GRAP fields are alignment bands only, not legal orders. "
        f"Official CAQM portal: {CAQM_GRAP_URL}."
    )


def _citations(episode: EpisodeOutput, critic: CriticResult) -> list[str]:
    cites = list(_CITATION_BASE)
    cites.append(f"EpisodeAgent severity={episode.severity.value} id={episode.episode_id}")
    if episode.aqi_peak is not None:
        cites.append(f"Episode peak AQI={episode.aqi_peak}")
    if critic.dominant_refused:
        cites.append("Critic:dominant_refused=true")
    else:
        cites.append(
            f"Critic revised dominant={critic.revised_dominant_class} "
            f"confidence={critic.revised_confidence:.2f}"
        )
    for finding in critic.findings:
        if finding.severity in {"warn", "error"}:
            cites.append(f"Critic:{finding.code}")
    seen: set[str] = set()
    out: list[str] = []
    for c in cites:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


class AdvisoryAgent:
    """Map critic-revised attribution to GRAP alignment-band advisory JSON."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, episode: EpisodeOutput, critic: CriticResult) -> AdvisoryResult:
        stage = aqi_to_grap_stage(episode.aqi_peak, episode.severity)
        citations = _citations(episode, critic)

        return AdvisoryResult(
            episode_id=episode.episode_id,
            region=episode.region,
            grap_stage=stage,
            grap_stage_label=_GRAP_LABELS[stage],
            grap_alignment_only=True,
            aqi_basis=episode.aqi_peak,
            severity=episode.severity,
            dominant_source=critic.revised_dominant_class,
            summary=_summary(stage, episode, critic),
            exposure_guidance=_exposure_for_stage(stage, episode.severity, citations),
            citations=citations,
            confidence=critic.revised_confidence,
            method="rule_score",
            critic_findings=critic.findings,
            timeline=list(episode.timeline),
        )


def build_advisory(
    episode: EpisodeOutput,
    critic: CriticResult,
    settings: Settings | None = None,
) -> AdvisoryResult:
    return AdvisoryAgent(settings=settings).run(episode, critic)
