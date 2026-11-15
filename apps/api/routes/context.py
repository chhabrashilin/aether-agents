"""Latest context feature vector endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aether_agents.agents.base.types import ContextFeatureVector
from apps.api.store import store

router = APIRouter(prefix="/context", tags=["context"])


@router.get("/latest", response_model=ContextFeatureVector)
def latest_context() -> ContextFeatureVector:
    """Return the most recent context feature vector (stub-seeded if no worker)."""
    if store.latest_context is None:
        raise HTTPException(status_code=404, detail="No context available")
    return store.latest_context
