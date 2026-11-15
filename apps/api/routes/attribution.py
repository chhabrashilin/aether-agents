"""Attribution / Critic / Advisory API routes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aether_agents.agents.evidence import (
    ContextOutput,
    EpisodeOutput,
    EpisodePhase,
    EpisodeSeverity,
    EpisodeTimelinePoint,
)
from aether_agents.agents.supervisor import PipelineResult, run_attribution_pipeline
from aether_agents.config import get_settings

router = APIRouter(tags=["attribution-advisory"])


class PipelineRequest(BaseModel):
    """Run Attribution → Critic → Advisory from Episode + Context payloads."""

    episode: EpisodeOutput
    context: ContextOutput = Field(default_factory=ContextOutput)


class DemoResponse(BaseModel):
    """Bundled demo payload for the research dashboard."""

    result: PipelineResult
    note: str = (
        "Synthetic winter-episode demo for UI wiring; replace with live Episode/Context agents."
    )


def _demo_episode() -> EpisodeOutput:
    start = datetime(2024, 11, 5, 6, 0, tzinfo=timezone.utc)
    timeline = [
        EpisodeTimelinePoint(
            timestamp=start + timedelta(hours=h),
            aqi=220 + h * 18 if h < 10 else 400 - (h - 10) * 12,
            phase=(
                EpisodePhase.ONSET
                if h < 4
                else EpisodePhase.PEAK
                if h < 12
                else EpisodePhase.DECAY
            ),
        )
        for h in range(0, 24, 2)
    ]
    return EpisodeOutput(
        episode_id="demo-delhi-2024-11-05",
        region="delhi-nct",
        severity=EpisodeSeverity.SEVERE,
        aqi_peak=418.0,
        aqi_mean=312.0,
        onset=start,
        peak=start + timedelta(hours=10),
        decay=start + timedelta(hours=20),
        duration_hours=24.0,
        phase=EpisodePhase.PEAK,
        uncertainty=0.25,
        station_coverage=0.82,
        timeline=timeline,
        notes=["Synthetic demo episode for dashboard"],
    )


def _demo_context() -> ContextOutput:
    return ContextOutput(
        region="delhi-nct",
        observed_at=datetime(2024, 11, 5, 12, 0, tzinfo=timezone.utc),
        fire_count_upwind=47,
        fire_frp_sum=210.0,
        wind_speed_ms=2.8,
        wind_direction_deg=310.0,
        blh_m=380.0,
        relative_humidity=78.0,
        temperature_c=18.0,
        is_festival_window=False,
        is_stubble_season=True,
        is_weekday=True,
        missing_fields=[],
        uncertainty=0.2,
    )


@router.post("/v1/attribution/run", response_model=PipelineResult)
def run_pipeline(body: PipelineRequest) -> PipelineResult:
    """Execute Attribution → Critic → Advisory (rule_score by default)."""

    try:
        return run_attribution_pipeline(
            body.episode, body.context, settings=get_settings()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/attribution/demo", response_model=DemoResponse)
def attribution_demo() -> DemoResponse:
    """Deterministic demo for dashboard timeline + attribution display."""

    result = run_attribution_pipeline(
        _demo_episode(), _demo_context(), settings=get_settings()
    )
    return DemoResponse(result=result)


@router.get("/v1/advisory/demo", response_model=PipelineResult)
def advisory_demo() -> PipelineResult:
    """Same demo chain; advisory is included in PipelineResult.advisory."""

    return run_attribution_pipeline(
        _demo_episode(), _demo_context(), settings=get_settings()
    )
