"""Full pipeline run endpoint (fixture or live) with provenance."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aether_agents.config import get_settings
from aether_agents.pipeline.full import FullPipelineResult, PipelineMode, run_full_pipeline
from apps.api.routes.metrics import inc_pipeline_run

router = APIRouter(tags=["pipeline"])


class PipelineRunRequest(BaseModel):
    """Run ingest→episode→context→attribution→advisory."""

    mode: Literal["fixture", "live"] = Field(
        default="fixture",
        description="fixture = offline synthetic series; live = APIs when keys present",
    )
    station_id: str | None = Field(
        default=None, description="Optional station filter / primary station"
    )


@router.post("/v1/pipeline/run", response_model=FullPipelineResult)
def pipeline_run(body: PipelineRunRequest | None = None) -> FullPipelineResult:
    """Execute the full science chain; returns provenance for reproducibility."""

    body = body or PipelineRunRequest()
    try:
        result = run_full_pipeline(
            mode=PipelineMode(body.mode),
            settings=get_settings(),
            station_id=body.station_id,
        )
        inc_pipeline_run(error=bool(result.errors))
        return result
    except Exception as exc:  # noqa: BLE001
        inc_pipeline_run(error=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/pipeline/run", response_model=FullPipelineResult)
def pipeline_run_get(
    mode: Literal["fixture", "live"] = Query(default="fixture"),
    station_id: str | None = Query(default=None),
) -> FullPipelineResult:
    """GET convenience for dashboard / curl smoke tests."""

    try:
        result = run_full_pipeline(
            mode=PipelineMode(mode),
            settings=get_settings(),
            station_id=station_id,
        )
        inc_pipeline_run(error=bool(result.errors))
        return result
    except Exception as exc:  # noqa: BLE001
        inc_pipeline_run(error=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
