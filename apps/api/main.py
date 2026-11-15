"""FastAPI gateway for AetherAgents."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aether_agents import __version__
from apps.api.routes import attribution, context, episodes, metrics, pipeline, stations


class StripApiPrefixMiddleware(BaseHTTPMiddleware):
    """Allow CIRRUS ingress path ``/api/*`` without rewriting every route."""

    def __init__(self, app: ASGIApp, prefix: str = "/api") -> None:
        super().__init__(app)
        self.prefix = prefix.rstrip("/")

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "")
        if path == self.prefix:
            request.scope["path"] = "/"
        elif path.startswith(self.prefix + "/"):
            request.scope["path"] = path[len(self.prefix) :] or "/"
        return await call_next(request)


app = FastAPI(
    title="AetherAgents API",
    description=(
        "Delhi–NCT winter smog episode intelligence gateway.\n\n"
        "Provides station/episode reads, context features, evidence-weighted "
        "source hypotheses, and GRAP *alignment-band* advisories. "
        "Advisories are non-authoritative research outputs, not CAQM orders. "
        "Official CAQM portal: https://caqm.nic.in/"
    ),
    version=__version__,
    openapi_tags=[
        {
            "name": "health",
            "description": "Liveness / readiness probes for Kubernetes",
        },
        {
            "name": "stations",
            "description": "Monitoring station metadata (CPCB / OpenAQ matched)",
        },
        {
            "name": "episodes",
            "description": "Detected Very Poor / Severe AQI episode windows",
        },
        {
            "name": "context",
            "description": "Fire / meteorology / calendar feature vectors",
        },
        {
            "name": "attribution-advisory",
            "description": (
                "Attribution → Critic → Advisory chain. "
                "Source classes are heuristic scores, not calibrated posteriors."
            ),
        },
        {
            "name": "pipeline",
            "description": (
                "Full offline/live pipeline (ingest→episode→context→attribution→advisory) "
                "with exportable provenance"
            ),
        },
        {
            "name": "observability",
            "description": "Prometheus text metrics",
        },
    ],
)

app.add_middleware(StripApiPrefixMiddleware, prefix="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(stations.router)
app.include_router(episodes.router)
app.include_router(context.router)
app.include_router(attribution.router)
app.include_router(pipeline.router)
app.include_router(metrics.router)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: datetime


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="aether-agents-api",
        version=__version__,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    return {
        "service": "aether-agents-api",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "stations": "/stations",
        "episodes": "/episodes",
        "context_latest": "/context/latest",
        "attribution_demo": "/v1/attribution/demo",
        "pipeline_run": "/v1/pipeline/run?mode=fixture",
        "advisory_note": "GRAP fields are alignment bands only; see https://caqm.nic.in/",
    }
