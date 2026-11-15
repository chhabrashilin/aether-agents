"""Full pipeline: ingest → episode → context → attribution → critic → advisory.

Offline mode uses fixtures / synthetic series (no API keys).
Live mode optionally fetches CPCB/OpenAQ/FIRMS/meteo when keys are present.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from aether_agents.agents.base.types import Observation
from aether_agents.agents.context import ContextAgent
from aether_agents.agents.episode import EpisodeAgent
from aether_agents.agents.evidence import (
    ContextOutput,
    EpisodeOutput,
    EpisodePhase,
    EpisodeSeverity,
    EpisodeTimelinePoint,
    context_from_vector,
    episode_from_object,
)
from aether_agents.agents.supervisor import PipelineResult, Supervisor
from aether_agents.config import Settings, get_settings
from aether_agents.context.firms import FirmsClient, FirmsFireEvent
from aether_agents.context.meteo import MeteoClient, MeteoSnapshot
from aether_agents.logging_util import bind_fields
from aether_agents.ingest.cpcb import parse_cpcb_records

logger = logging.getLogger(__name__)

_REPO_FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"
_DEFAULT_OFFLINE_SERIES = _REPO_FIXTURES / "pipeline_episode_series.json"

# Delhi centre (Connaught Place area) for context defaults.
_DELHI_LAT = 28.6139
_DELHI_LON = 77.2090


class PipelineMode(str, Enum):
    FIXTURE = "fixture"
    LIVE = "live"


class FullPipelineResult(BaseModel):
    """End-to-end run with provenance for research reproducibility."""

    run_id: str
    mode: PipelineMode
    started_at: datetime
    finished_at: datetime
    station_id: str
    observations_used: int
    episodes_detected: int
    episode: EpisodeOutput | None = None
    context: ContextOutput | None = None
    science: PipelineResult | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


def _load_offline_observations(
    path: Path | None = None,
) -> tuple[list[Observation], dict[str, Any]]:
    series_path = path or _DEFAULT_OFFLINE_SERIES
    payload = json.loads(series_path.read_text(encoding="utf-8"))
    rows = payload.get("observations") or []
    observations: list[Observation] = []
    for row in rows:
        observations.append(Observation.model_validate(row))
    meta = {
        "fixture_path": str(series_path),
        "fixture_label": payload.get("label", "pipeline_episode_series"),
        "fixture_disclaimer": payload.get(
            "disclaimer",
            "Synthetic series for offline pipeline tests, not observational archive.",
        ),
    }
    return observations, meta


def _stub_meteo(as_of: datetime) -> MeteoSnapshot:
    return MeteoSnapshot(
        valid_at=as_of,
        wind_speed_ms=2.8,
        wind_direction_deg=310.0,
        boundary_layer_height_m=380.0,
        relative_humidity_pct=72.0,
    )


def _stub_firms(as_of: datetime) -> list[FirmsFireEvent]:
    # Synthetic upwind NW fires for offline reproducibility.
    events: list[FirmsFireEvent] = []
    for i in range(40):
        events.append(
            FirmsFireEvent(
                latitude=29.5 + (i % 5) * 0.1,
                longitude=76.0 + (i % 7) * 0.1,
                brightness=320.0,
                acq_datetime=as_of - timedelta(hours=i % 20),
                confidence="nominal",
            )
        )
    return events


class _FixtureMeteo:
    def fetch_snapshot(
        self,
        *,
        latitude: float,
        longitude: float,
        as_of: datetime | None = None,
    ) -> MeteoSnapshot:
        return _stub_meteo(as_of or datetime.now(timezone.utc))


class _FixtureFirms:
    def fetch_fires(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float = 250.0,
        days: int = 3,
        as_of: datetime | None = None,
    ) -> list[FirmsFireEvent]:
        return _stub_firms(as_of or datetime.now(timezone.utc))


def _episode_to_output(ep: Any, observations: list[Observation]) -> EpisodeOutput:
    base = episode_from_object(ep)
    # Build timeline from observations in the episode window.
    start = ep.onset_at
    end = ep.ended_at or ep.peak_at
    timeline: list[EpisodeTimelinePoint] = []
    for obs in sorted(observations, key=lambda o: o.observed_at):
        ts = obs.observed_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < start or ts > end + timedelta(hours=1):
            continue
        aqi = obs.resolved_aqi()
        if ts == ep.peak_at:
            phase = EpisodePhase.PEAK
        elif ts <= ep.peak_at:
            phase = EpisodePhase.ONSET
        else:
            phase = EpisodePhase.DECAY
        timeline.append(
            EpisodeTimelinePoint(
                timestamp=ts,
                aqi=float(aqi) if aqi is not None else None,
                phase=phase,
            )
        )
    severity = EpisodeSeverity.SEVERE
    try:
        severity = EpisodeSeverity(ep.peak_category.value)
    except Exception:  # noqa: BLE001
        severity = EpisodeSeverity.VERY_POOR
    return base.model_copy(
        update={
            "severity": severity,
            "timeline": timeline,
            "notes": list(ep.notes or []) + list(base.notes or []),
        }
    )


def run_full_pipeline(
    *,
    mode: PipelineMode | Literal["fixture", "live"] = PipelineMode.FIXTURE,
    settings: Settings | None = None,
    fixture_path: Path | None = None,
    station_id: str | None = None,
    latitude: float = _DELHI_LAT,
    longitude: float = _DELHI_LON,
    run_id: str | None = None,
) -> FullPipelineResult:
    """Execute ingest→episode→context→attribution→advisory with provenance."""

    settings = settings or get_settings()
    mode_enum = PipelineMode(mode) if not isinstance(mode, PipelineMode) else mode
    rid = run_id or f"run-{uuid4().hex[:12]}"
    started = datetime.now(timezone.utc)
    log = bind_fields(logger, run_id=rid)
    notes: list[str] = []
    errors: list[str] = []
    provenance: dict[str, Any] = {
        "run_id": rid,
        "mode": mode_enum.value,
        "region": settings.region,
        "steps": [],
    }

    observations: list[Observation] = []
    if mode_enum == PipelineMode.FIXTURE:
        observations, meta = _load_offline_observations(fixture_path)
        provenance["ingest"] = meta
        provenance["steps"].append("ingest_fixture")
        notes.append(meta["fixture_disclaimer"])
    else:
        # Live: best-effort CPCB snapshot expanded is not enough for episodes;
        # still attempt OpenAQ hours when key present; otherwise fall back note.
        provenance["steps"].append("ingest_live_attempt")
        if settings.data_gov_in_api_key:
            try:
                from aether_agents.ingest.cpcb import CpcbClient

                with CpcbClient(settings.data_gov_in_api_key) as client:
                    raw, records = client.fetch_delhi_ncr(limit=200, max_pages=2)
                provenance["cpcb_records"] = len(records)
                provenance["cpcb_resource"] = raw.get("resource_id")
                # Convert latest CPCB PM2.5 sub-indices into single-hour observations;
                # without history, episode detection may yield zero episodes.
                for rec in records:
                    if not rec.last_update or not rec.pollutant_id:
                        continue
                    if "pm2.5" not in rec.pollutant_id.lower().replace(" ", ""):
                        continue
                    observations.append(
                        Observation(
                            station_id=f"{rec.city}|{rec.station}",
                            observed_at=rec.last_update,
                            pollutant="pm25",
                            value=rec.pollutant_avg,
                            value_semantics="sub_index",
                            unit="aqi_sub_index",
                            qa_flag=",".join(rec.qa_flags) if rec.qa_flags else None,
                        )
                    )
                notes.append(
                    "Live CPCB snapshot ingested; multi-hour history may be insufficient "
                    "for episode min_duration without OpenAQ hours."
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"cpcb_live: {exc}")
                log.exception("live CPCB ingest failed")
        else:
            notes.append("LIVE mode without DATA_GOV_IN_API_KEY; no CPCB fetch.")

        if settings.openaq_api_key:
            try:
                from aether_agents.ingest.openaq import OpenAqClient, parse_openaq_measurements

                with OpenAqClient(settings.openaq_api_key) as client:
                    _, locations = client.list_delhi_ncr_locations()
                    for loc in locations[:5]:
                        page = client.fetch_location_hours(loc.id, limit=48)
                        for meas in parse_openaq_measurements(page, location_id=loc.id):
                            if meas.observed_at is None:
                                continue
                            observations.append(
                                Observation(
                                    station_id=loc.id,
                                    observed_at=meas.observed_at,
                                    pollutant=meas.pollutant or "pm25",
                                    value=meas.value,
                                    value_semantics="concentration",
                                    unit=meas.unit or "ug/m3",
                                )
                            )
                provenance["openaq_observations"] = len(observations)
                provenance["steps"].append("openaq_hours")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"openaq_live: {exc}")
        else:
            notes.append("LIVE mode without OPENAQ_API_KEY; no OpenAQ hours.")

        if not observations:
            # Honest fallback: run fixture path so the pipeline remains demoable,
            # but mark provenance clearly.
            observations, meta = _load_offline_observations(fixture_path)
            provenance["ingest_fallback"] = meta
            notes.append(
                "Live keys/data insufficient; fell back to offline fixture series."
            )
            provenance["steps"].append("ingest_fixture_fallback")

    if station_id:
        observations = [o for o in observations if o.station_id == station_id]
    if not observations:
        finished = datetime.now(timezone.utc)
        return FullPipelineResult(
            run_id=rid,
            mode=mode_enum,
            started_at=started,
            finished_at=finished,
            station_id=station_id or "",
            observations_used=0,
            episodes_detected=0,
            provenance=provenance,
            notes=notes + ["No observations available"],
            errors=errors,
        )

    # Pick the station with the most points if not specified.
    from collections import Counter

    counts = Counter(o.station_id for o in observations)
    primary_station = station_id or counts.most_common(1)[0][0]
    station_obs = [o for o in observations if o.station_id == primary_station]
    log = bind_fields(logger, run_id=rid, station_id=primary_station)
    log.info("pipeline episode detection observations=%s", len(station_obs))

    episode_agent = EpisodeAgent()
    episodes = episode_agent.detect(station_obs)
    provenance["steps"].append("episode")
    provenance["episodes_detected"] = len(episodes)

    if not episodes:
        finished = datetime.now(timezone.utc)
        return FullPipelineResult(
            run_id=rid,
            mode=mode_enum,
            started_at=started,
            finished_at=finished,
            station_id=primary_station,
            observations_used=len(station_obs),
            episodes_detected=0,
            provenance=provenance,
            notes=notes + ["No Very Poor/Severe episode meeting min_duration"],
            errors=errors,
        )

    # Use the highest-peak episode.
    chosen = max(episodes, key=lambda e: e.peak_aqi)
    episode_out = _episode_to_output(chosen, station_obs)
    log = bind_fields(
        logger, run_id=rid, station_id=primary_station, episode_id=chosen.episode_id
    )
    log.info("pipeline selected episode peak_aqi=%s", chosen.peak_aqi)

    as_of = chosen.peak_at
    if mode_enum == PipelineMode.FIXTURE:
        context_agent = ContextAgent(firms=_FixtureFirms(), meteo=_FixtureMeteo())
        provenance["context_sources"] = {"firms": "fixture_stub", "meteo": "fixture_stub"}
    else:
        firms = FirmsClient(map_key=settings.firms_map_key or None)
        meteo = MeteoClient()
        context_agent = ContextAgent(firms=firms, meteo=meteo)
        provenance["context_sources"] = {
            "firms": "nasa_firms" if settings.firms_map_key else "firms_no_key",
            "meteo": "open_meteo",
        }

    vector = context_agent.build(
        location_id=primary_station,
        latitude=latitude,
        longitude=longitude,
        as_of=as_of,
    )
    # Calendar: mark stubble season for Nov fixture peaks.
    context_out = context_from_vector(vector)
    if as_of.month in (10, 11):
        context_out = context_out.model_copy(
            update={"is_stubble_season": True}
        )
    provenance["steps"].append("context")

    science = Supervisor(settings=settings).run(episode_out, context_out)
    provenance["steps"].extend(["attribution", "critic", "advisory"])
    provenance["scorecard_rows"] = len(science.attribution.scorecard)
    provenance["dominant_refused"] = science.critic.dominant_refused

    finished = datetime.now(timezone.utc)
    log.info(
        "pipeline complete dominant_refused=%s grap=%s",
        science.critic.dominant_refused,
        science.advisory.grap_stage.value,
    )
    return FullPipelineResult(
        run_id=rid,
        mode=mode_enum,
        started_at=started,
        finished_at=finished,
        station_id=primary_station,
        observations_used=len(station_obs),
        episodes_detected=len(episodes),
        episode=episode_out,
        context=context_out,
        science=science,
        provenance=provenance,
        notes=notes,
        errors=errors,
    )


def build_observations_from_cpcb_payload(payload: dict[str, Any]) -> list[Observation]:
    """Helper for tests: map CPCB fixture rows to typed Observations."""

    records = parse_cpcb_records(payload, delhi_ncr_only=True)
    out: list[Observation] = []
    for rec in records:
        if rec.last_update is None:
            continue
        out.append(
            Observation(
                station_id=f"{rec.city}|{rec.station}",
                observed_at=rec.last_update,
                pollutant=rec.pollutant_id.lower().replace(".", "").replace(" ", ""),
                value=rec.pollutant_avg,
                value_semantics="sub_index",
                unit="aqi_sub_index",
            )
        )
    return out
