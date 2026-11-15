"""Unit tests for OpenAQ v3 parsing (fixture-only, no live API)."""

from aether_agents.ingest.openaq import parse_openaq_locations, parse_openaq_measurements


def test_parse_locations(openaq_locations_payload):
    locations = parse_openaq_locations(openaq_locations_payload)
    assert len(locations) == 3
    anand = next(loc for loc in locations if loc.id == "1001")
    assert anand.name == "Anand Vihar"
    assert anand.latitude == 28.6468
    assert anand.longitude == 77.3160


def test_parse_measurements_keeps_gaps(openaq_measurements_payload):
    measurements = parse_openaq_measurements(
        openaq_measurements_payload,
        location_id="1001",
        location_name="Anand Vihar",
    )
    assert len(measurements) == 4
    assert all(m.value_semantics == "concentration" for m in measurements)

    gap = next(m for m in measurements if m.value is None)
    assert "gap" in gap.qa_flags
    assert "missing_value" in gap.qa_flags

    values = [m.value for m in measurements if m.pollutant == "pm25" and m.value is not None]
    assert values == [185.2, 192.0]
