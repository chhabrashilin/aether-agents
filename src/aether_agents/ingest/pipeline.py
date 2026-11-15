"""Ingest pipeline: CPCB + OpenAQ → station match → Postgres/SQLite."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from aether_agents.db.models import Observation, RawPayload, Station
from aether_agents.db.session import init_db, session_scope
from aether_agents.ingest.cpcb import CpcbClient, CpcbRecord, parse_cpcb_records
from aether_agents.ingest.matching import StationMatch, match_stations, normalize_station_name
from aether_agents.ingest.openaq import (
    OpenAqClient,
    OpenAqLocation,
    OpenAqMeasurement,
    parse_openaq_locations,
    parse_openaq_measurements,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    cpcb_records: int = 0
    openaq_locations: int = 0
    openaq_measurements: int = 0
    stations_upserted: int = 0
    observations_upserted: int = 0
    matches: list[StationMatch] = field(default_factory=list)
    raw_payload_ids: list[int] = field(default_factory=list)


def _upsert_station_from_cpcb(
    session: Session,
    rec: CpcbRecord,
    *,
    openaq_location_id: Optional[str] = None,
    match_score: Optional[float] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Station:
    cpcb_id = f"{rec.city}|{rec.station}"
    existing = session.scalar(select(Station).where(Station.cpcb_station_id == cpcb_id))
    if existing is None and openaq_location_id:
        existing = session.scalar(
            select(Station).where(Station.openaq_location_id == openaq_location_id)
        )
    if existing is None:
        existing = Station(
            name=rec.station,
            normalized_name=normalize_station_name(rec.station),
            city=rec.city,
            state=rec.state,
            country=rec.country or "IN",
            cpcb_station_id=cpcb_id,
            openaq_location_id=openaq_location_id,
            latitude=latitude,
            longitude=longitude,
            source_primary="cpcb",
            match_score=match_score,
        )
        session.add(existing)
        session.flush()
        return existing

    existing.name = rec.station or existing.name
    existing.normalized_name = normalize_station_name(existing.name)
    existing.city = rec.city or existing.city
    existing.state = rec.state or existing.state
    existing.cpcb_station_id = existing.cpcb_station_id or cpcb_id
    if openaq_location_id:
        existing.openaq_location_id = openaq_location_id
    if match_score is not None:
        existing.match_score = match_score
    if latitude is not None:
        existing.latitude = latitude
    if longitude is not None:
        existing.longitude = longitude
    session.flush()
    return existing


def _upsert_station_from_openaq(session: Session, loc: OpenAqLocation) -> Station:
    existing = session.scalar(
        select(Station).where(Station.openaq_location_id == loc.id)
    )
    if existing is None:
        existing = Station(
            name=loc.name,
            normalized_name=normalize_station_name(loc.name),
            city=loc.city or loc.locality,
            country=loc.country or "IN",
            openaq_location_id=loc.id,
            latitude=loc.latitude,
            longitude=loc.longitude,
            source_primary="openaq",
        )
        session.add(existing)
        session.flush()
        return existing
    existing.latitude = loc.latitude if loc.latitude is not None else existing.latitude
    existing.longitude = loc.longitude if loc.longitude is not None else existing.longitude
    existing.city = loc.city or loc.locality or existing.city
    session.flush()
    return existing


def _upsert_observation(
    session: Session,
    *,
    station: Station,
    observed_at: datetime,
    pollutant: str,
    value: Optional[float],
    value_semantics: str,
    unit: Optional[str],
    source: str,
    qa_flags: list[str],
    raw_payload_id: Optional[int],
) -> bool:
    """Insert observation if not present. Returns True when a row was added."""
    existing = session.scalar(
        select(Observation).where(
            Observation.station_id == station.id,
            Observation.observed_at == observed_at,
            Observation.pollutant == pollutant,
            Observation.source == source,
            Observation.value_semantics == value_semantics,
        )
    )
    if existing is not None:
        # Refresh value/QA but do not invent data for gaps.
        existing.value = value
        existing.qa_flags = qa_flags
        existing.unit = unit or existing.unit
        existing.raw_payload_id = raw_payload_id or existing.raw_payload_id
        return False

    session.add(
        Observation(
            station_id=station.id,
            observed_at=observed_at,
            pollutant=pollutant,
            value=value,
            value_semantics=value_semantics,
            unit=unit,
            source=source,
            qa_flags=qa_flags,
            raw_payload_id=raw_payload_id,
        )
    )
    return True


def persist_cpcb(
    session: Session,
    records: list[CpcbRecord],
    *,
    raw_payload: Optional[dict[str, Any]] = None,
    matches: Optional[list[StationMatch]] = None,
    openaq_by_id: Optional[dict[str, OpenAqLocation]] = None,
) -> tuple[int, int, Optional[int]]:
    """Persist CPCB records. Returns (stations, observations, raw_id)."""
    match_index = {
        (m.cpcb_station, m.cpcb_city): m for m in (matches or [])
    }
    openaq_by_id = openaq_by_id or {}
    raw_id: Optional[int] = None
    if raw_payload is not None:
        raw = RawPayload(
            source="cpcb",
            endpoint="resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69",
            payload=raw_payload,
            notes="CPCB OGD Real-time AQI; pollutant_* fields are sub-indices",
        )
        session.add(raw)
        session.flush()
        raw_id = raw.id

    stations = 0
    observations = 0
    seen_stations: set[str] = set()
    for rec in records:
        if not rec.station:
            continue
        m = match_index.get((rec.station, rec.city))
        loc = openaq_by_id.get(m.openaq_location_id) if m else None
        station = _upsert_station_from_cpcb(
            session,
            rec,
            openaq_location_id=m.openaq_location_id if m else None,
            match_score=m.score if m else None,
            latitude=loc.latitude if loc else None,
            longitude=loc.longitude if loc else None,
        )
        sid = station.cpcb_station_id or str(station.id)
        if sid not in seen_stations:
            seen_stations.add(sid)
            stations += 1

        if rec.last_update is None or not rec.pollutant_id:
            continue
        added = _upsert_observation(
            session,
            station=station,
            observed_at=rec.last_update,
            pollutant=rec.pollutant_id,
            value=rec.pollutant_avg,
            value_semantics="sub_index",
            unit="aqi_sub_index",
            source="cpcb",
            qa_flags=list(rec.qa_flags),
            raw_payload_id=raw_id,
        )
        if added:
            observations += 1
    return stations, observations, raw_id


def persist_openaq_measurements(
    session: Session,
    measurements: list[OpenAqMeasurement],
    locations: list[OpenAqLocation],
    *,
    raw_payload: Optional[dict[str, Any]] = None,
    endpoint: str = "locations/hours",
) -> tuple[int, int, Optional[int]]:
    loc_by_id = {loc.id: loc for loc in locations}
    raw_id: Optional[int] = None
    if raw_payload is not None:
        raw = RawPayload(
            source="openaq",
            endpoint=endpoint,
            payload=raw_payload,
            notes="OpenAQ v3 hourly; gaps remain gaps (no interpolation)",
        )
        session.add(raw)
        session.flush()
        raw_id = raw.id

    stations = 0
    observations = 0
    seen: set[str] = set()
    for meas in measurements:
        loc = loc_by_id.get(meas.location_id)
        if loc is None:
            # Minimal station from measurement identity
            loc = OpenAqLocation(
                id=meas.location_id or "unknown",
                name=meas.location_name or meas.location_id or "unknown",
                locality=None,
                city=None,
                country="IN",
                latitude=None,
                longitude=None,
            )
        station = _upsert_station_from_openaq(session, loc)
        if loc.id not in seen:
            seen.add(loc.id)
            stations += 1
        if meas.observed_at is None or not meas.pollutant:
            continue
        added = _upsert_observation(
            session,
            station=station,
            observed_at=meas.observed_at,
            pollutant=meas.pollutant,
            value=meas.value,
            value_semantics="concentration",
            unit=meas.unit,
            source="openaq",
            qa_flags=list(meas.qa_flags),
            raw_payload_id=raw_id,
        )
        if added:
            observations += 1
    return stations, observations, raw_id


def run_ingest_from_payloads(
    session: Session,
    *,
    cpcb_payload: Optional[dict[str, Any]] = None,
    openaq_locations_payload: Optional[dict[str, Any]] = None,
    openaq_hours_payload: Optional[dict[str, Any]] = None,
    openaq_location_id: str = "",
) -> IngestResult:
    """Offline/test path: ingest from fixture payloads (no live HTTP)."""
    result = IngestResult()
    cpcb_records: list[CpcbRecord] = []
    if cpcb_payload is not None:
        cpcb_records = parse_cpcb_records(cpcb_payload, delhi_ncr_only=True)
        result.cpcb_records = len(cpcb_records)

    locations: list[OpenAqLocation] = []
    if openaq_locations_payload is not None:
        locations = parse_openaq_locations(openaq_locations_payload)
        result.openaq_locations = len(locations)

    matches = match_stations(cpcb_records, locations) if cpcb_records and locations else []
    result.matches = matches
    openaq_by_id = {loc.id: loc for loc in locations}

    if cpcb_records:
        st, obs, rid = persist_cpcb(
            session,
            cpcb_records,
            raw_payload=cpcb_payload,
            matches=matches,
            openaq_by_id=openaq_by_id,
        )
        result.stations_upserted += st
        result.observations_upserted += obs
        if rid is not None:
            result.raw_payload_ids.append(rid)

    measurements: list[OpenAqMeasurement] = []
    if openaq_hours_payload is not None:
        measurements = parse_openaq_measurements(
            openaq_hours_payload,
            location_id=openaq_location_id,
        )
        result.openaq_measurements = len(measurements)
        st, obs, rid = persist_openaq_measurements(
            session,
            measurements,
            locations,
            raw_payload=openaq_hours_payload,
        )
        result.stations_upserted += st
        result.observations_upserted += obs
        if rid is not None:
            result.raw_payload_ids.append(rid)

    return result


def run_ingest(
    *,
    database_url: str,
    data_gov_in_api_key: str = "",
    openaq_api_key: str = "",
    fetch_cpcb: bool = True,
    fetch_openaq: bool = True,
    openaq_hours_limit: int = 100,
) -> IngestResult:
    """Live ingest tick: fetch APIs (when keys present) and persist."""
    init_db(database_url)
    result = IngestResult()

    cpcb_payload: Optional[dict[str, Any]] = None
    cpcb_records: list[CpcbRecord] = []
    if fetch_cpcb and data_gov_in_api_key:
        with CpcbClient(data_gov_in_api_key) as client:
            cpcb_payload, cpcb_records = client.fetch_delhi_ncr()
        result.cpcb_records = len(cpcb_records)
        logger.info("CPCB fetch: %s Delhi/NCR records", result.cpcb_records)
    elif fetch_cpcb:
        logger.warning("Skipping CPCB fetch: DATA_GOV_IN_API_KEY not set")

    locations_payload: Optional[dict[str, Any]] = None
    locations: list[OpenAqLocation] = []
    hours_payload: Optional[dict[str, Any]] = None
    measurements: list[OpenAqMeasurement] = []

    if fetch_openaq and openaq_api_key:
        with OpenAqClient(openaq_api_key) as client:
            locations_payload, locations = client.list_delhi_ncr_locations()
            result.openaq_locations = len(locations)
            # Hours for matched (or first few) locations; gaps stay gaps.
            matches_preview = match_stations(cpcb_records, locations) if cpcb_records else []
            target_ids = [m.openaq_location_id for m in matches_preview[:10]]
            if not target_ids:
                target_ids = [loc.id for loc in locations[:5]]
            merged_hours: dict[str, Any] = {"results": []}
            for loc_id in target_ids:
                page = client.fetch_location_hours(loc_id, limit=openaq_hours_limit)
                rows = page.get("results") or []
                if isinstance(rows, list):
                    merged_hours["results"].extend(rows)
                measurements.extend(
                    parse_openaq_measurements(page, location_id=str(loc_id))
                )
            hours_payload = merged_hours
            result.openaq_measurements = len(measurements)
        logger.info(
            "OpenAQ fetch: %s locations, %s hourly rows",
            result.openaq_locations,
            result.openaq_measurements,
        )
    elif fetch_openaq:
        logger.warning("Skipping OpenAQ fetch: OPENAQ_API_KEY not set")

    matches = match_stations(cpcb_records, locations) if cpcb_records and locations else []
    result.matches = matches

    with session_scope(database_url) as session:
        if cpcb_records:
            st, obs, rid = persist_cpcb(
                session,
                cpcb_records,
                raw_payload=cpcb_payload,
                matches=matches,
                openaq_by_id={loc.id: loc for loc in locations},
            )
            result.stations_upserted += st
            result.observations_upserted += obs
            if rid is not None:
                result.raw_payload_ids.append(rid)
        if measurements:
            st, obs, rid = persist_openaq_measurements(
                session,
                measurements,
                locations,
                raw_payload=hours_payload,
            )
            result.stations_upserted += st
            result.observations_upserted += obs
            if rid is not None:
                result.raw_payload_ids.append(rid)

    logger.info(
        "ingest complete stations=%s observations=%s matches=%s at=%s",
        result.stations_upserted,
        result.observations_upserted,
        len(result.matches),
        datetime.now(timezone.utc).isoformat(),
    )
    return result
