"""Station list read endpoint (stub-friendly until ingest persists stations)."""

from __future__ import annotations

from fastapi import APIRouter

from aether_agents.agents.base.types import StationStub
from apps.api.store import store

router = APIRouter(prefix="/stations", tags=["stations"])


@router.get("", response_model=list[StationStub])
def list_stations() -> list[StationStub]:
    """Return Delhi–NCT stations (stub metadata until ingest is wired)."""
    return store.stations
