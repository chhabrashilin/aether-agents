"""Prometheus-style text metrics (lightweight, no prometheus_client dep)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from apps.api.store import store

router = APIRouter(tags=["observability"])

# Process-local counters (reset on restart; honest about v1 limits).
_pipeline_runs = 0
_pipeline_errors = 0


def inc_pipeline_run(*, error: bool = False) -> None:
    global _pipeline_runs, _pipeline_errors
    _pipeline_runs += 1
    if error:
        _pipeline_errors += 1


@router.get("/metrics", response_class=Response)
def metrics() -> Response:
    """Expose Prometheus text exposition format for CIRRUS scraping."""

    episodes = len(store.episodes)
    stations = len(store.stations)
    lines = [
        "# HELP aether_agents_info Static build info",
        "# TYPE aether_agents_info gauge",
        'aether_agents_info{service="aether-agents-api"} 1',
        "# HELP aether_agents_store_episodes In-memory episode count (demo store)",
        "# TYPE aether_agents_store_episodes gauge",
        f"aether_agents_store_episodes {episodes}",
        "# HELP aether_agents_store_stations In-memory station count (demo store)",
        "# TYPE aether_agents_store_stations gauge",
        f"aether_agents_store_stations {stations}",
        "# HELP aether_agents_pipeline_runs_total Full pipeline invocations since process start",
        "# TYPE aether_agents_pipeline_runs_total counter",
        f"aether_agents_pipeline_runs_total {_pipeline_runs}",
        "# HELP aether_agents_pipeline_errors_total Full pipeline errors since process start",
        "# TYPE aether_agents_pipeline_errors_total counter",
        f"aether_agents_pipeline_errors_total {_pipeline_errors}",
        "",
    ]
    return Response(content="\n".join(lines), media_type="text/plain; version=0.0.4")
