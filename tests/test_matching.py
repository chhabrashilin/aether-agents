"""Unit tests for CPCB ↔ OpenAQ station matching."""

from aether_agents.ingest.cpcb import parse_cpcb_records
from aether_agents.ingest.matching import match_stations, normalize_station_name
from aether_agents.ingest.openaq import parse_openaq_locations


def test_normalize_strips_agency_suffixes():
    assert normalize_station_name("Anand Vihar - DPCC") == "anand vihar"
    assert normalize_station_name("ITO - CPCB") == "ito"


def test_match_stations_from_fixtures(cpcb_payload, openaq_locations_payload):
    cpcb = parse_cpcb_records(cpcb_payload, delhi_ncr_only=True)
    locations = parse_openaq_locations(openaq_locations_payload)
    matches = match_stations(cpcb, locations, min_score=0.6)

    by_cpcb = {m.cpcb_station: m for m in matches}
    assert "Anand Vihar - DPCC" in by_cpcb
    assert by_cpcb["Anand Vihar - DPCC"].openaq_location_id == "1001"
    assert "ITO - CPCB" in by_cpcb
    assert by_cpcb["ITO - CPCB"].openaq_location_id == "1002"
