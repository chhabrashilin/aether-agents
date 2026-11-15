"""Unit tests for CPCB OGD client parsing (fixture-only, no live API)."""

from datetime import datetime, timezone

from aether_agents.ingest.cpcb import (
    CPCB_RESOURCE_ID,
    is_delhi_ncr,
    parse_cpcb_records,
    parse_cpcb_timestamp,
)


def test_resource_id_is_documented_constant():
    assert CPCB_RESOURCE_ID == "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"


def test_delhi_ncr_filter():
    assert is_delhi_ncr("Delhi", "Delhi")
    assert is_delhi_ncr("Noida", "Uttar Pradesh")
    assert is_delhi_ncr("Gurugram", "Haryana")
    assert not is_delhi_ncr("Mumbai", "Maharashtra")


def test_parse_timestamp():
    dt = parse_cpcb_timestamp("15-11-2024 10:00:00")
    assert dt == datetime(2024, 11, 15, 10, 0, 0, tzinfo=timezone.utc)
    assert parse_cpcb_timestamp("") is None


def test_parse_cpcb_filters_delhi_and_marks_sub_index(cpcb_payload):
    records = parse_cpcb_records(
        cpcb_payload,
        delhi_ncr_only=True,
        now=datetime(2024, 11, 15, 10, 30, tzinfo=timezone.utc),
    )
    cities = {r.city for r in records}
    assert "Mumbai" not in cities
    assert "Delhi" in cities
    assert "Noida" in cities

    anand = next(r for r in records if r.station.startswith("Anand") and r.pollutant_id == "PM2.5")
    assert anand.value_semantics == "sub_index"
    assert anand.pollutant_avg == 312.0
    assert "cpcb_sub_index" in anand.qa_flags

    bad = next(r for r in records if r.station.startswith("Bad Value"))
    assert bad.pollutant_avg is None
    assert "non_numeric" in bad.qa_flags or "missing_value" in bad.qa_flags


def test_parse_without_filter_includes_mumbai(cpcb_payload):
    records = parse_cpcb_records(cpcb_payload, delhi_ncr_only=False)
    assert any(r.city == "Mumbai" for r in records)
