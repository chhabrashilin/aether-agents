"""Episode read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from aether_agents.agents.base.types import EpisodeObject
from apps.api.store import store

router = APIRouter(prefix="/episodes", tags=["episodes"])


@router.get("", response_model=list[EpisodeObject])
def list_episodes(
    station_id: str | None = Query(default=None, description="Filter by station"),
    open_only: bool = Query(default=False, description="Only open (ongoing) episodes"),
) -> list[EpisodeObject]:
    """Return detected Very Poor / Severe episode windows."""
    rows = store.episodes
    if station_id:
        rows = [e for e in rows if e.station_id == station_id]
    if open_only:
        rows = [e for e in rows if e.is_open]
    return rows
