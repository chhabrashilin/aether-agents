"""Integration-style tests for DB schema + ingest pipeline (SQLite)."""

from sqlalchemy import select

from aether_agents.db.models import Observation, RawPayload, Station
from aether_agents.db.session import get_session_factory
from aether_agents.ingest.pipeline import run_ingest_from_payloads


def test_schema_and_pipeline_persist_fixtures(
    sqlite_url,
    cpcb_payload,
    openaq_locations_payload,
    openaq_measurements_payload,
):
    factory = get_session_factory(sqlite_url)
    with factory() as session:
        result = run_ingest_from_payloads(
            session,
            cpcb_payload=cpcb_payload,
            openaq_locations_payload=openaq_locations_payload,
            openaq_hours_payload=openaq_measurements_payload,
            openaq_location_id="1001",
        )
        session.commit()

    assert result.cpcb_records >= 4
    assert result.openaq_locations == 3
    assert result.openaq_measurements == 4
    assert len(result.matches) >= 2
    assert result.observations_upserted >= 1

    with factory() as session:
        stations = list(session.scalars(select(Station)))
        observations = list(session.scalars(select(Observation)))
        payloads = list(session.scalars(select(RawPayload)))

        assert len(stations) >= 2
        assert len(payloads) >= 1

        cpcb_obs = [o for o in observations if o.source == "cpcb"]
        openaq_obs = [o for o in observations if o.source == "openaq"]
        assert cpcb_obs
        assert all(o.value_semantics == "sub_index" for o in cpcb_obs)
        assert openaq_obs
        assert all(o.value_semantics == "concentration" for o in openaq_obs)

        gap_rows = [o for o in openaq_obs if o.value is None]
        assert gap_rows
        assert any("gap" in (o.qa_flags or []) for o in gap_rows)

        matched = [s for s in stations if s.cpcb_station_id and s.openaq_location_id]
        assert matched
