"""ContextAgent tests with mocked FIRMS / Open-Meteo (no live keys)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from aether_agents.agents.context import ContextAgent
from aether_agents.context.calendar_delhi import DelhiCalendar
from aether_agents.context.firms import (
    FirmsFireEvent,
    MockFirmsClient,
    angle_difference_deg,
    is_upwind,
)
from aether_agents.context.meteo import MockMeteoClient, MeteoSnapshot


DELHI_LAT = 28.6139
DELHI_LON = 77.2090


def test_angle_difference():
    assert angle_difference_deg(10, 350) == 20
    assert angle_difference_deg(0, 180) == 180


def test_upwind_sector_with_nw_wind():
    # Fire north of Delhi; wind from NW (~315) → fire roughly upwind
    assert is_upwind(
        station_lat=DELHI_LAT,
        station_lon=DELHI_LON,
        fire_lat=DELHI_LAT + 1.0,
        fire_lon=DELHI_LON - 0.5,
        wind_direction_deg=320.0,
        sector_half_width_deg=60.0,
    )
    # Fire south; not upwind for NW wind
    assert not is_upwind(
        station_lat=DELHI_LAT,
        station_lon=DELHI_LON,
        fire_lat=DELHI_LAT - 1.5,
        fire_lon=DELHI_LON,
        wind_direction_deg=320.0,
        sector_half_width_deg=45.0,
    )


def test_context_feature_vector_deterministic():
    as_of = datetime(2024, 11, 3, 12, 0, tzinfo=timezone.utc)  # Diwali window + winter
    fires = [
        FirmsFireEvent(
            latitude=DELHI_LAT + 1.2,
            longitude=DELHI_LON - 0.4,
            acq_datetime=as_of - timedelta(hours=5),
        ),
        FirmsFireEvent(
            latitude=DELHI_LAT - 2.0,
            longitude=DELHI_LON + 0.5,
            acq_datetime=as_of - timedelta(hours=8),
        ),
        FirmsFireEvent(
            latitude=DELHI_LAT + 0.8,
            longitude=DELHI_LON - 0.3,
            acq_datetime=as_of - timedelta(hours=40),
        ),
    ]
    met = MeteoSnapshot(
        valid_at=as_of,
        wind_speed_ms=1.8,
        wind_direction_deg=315.0,
        boundary_layer_height_m=220.0,
        relative_humidity_pct=68.0,
    )
    agent = ContextAgent(
        firms=MockFirmsClient(fires),
        meteo=MockMeteoClient(met),
    )
    vec = agent.build(
        location_id="DL001",
        latitude=DELHI_LAT,
        longitude=DELHI_LON,
        as_of=as_of,
    )
    assert vec.location_id == "DL001"
    assert vec.wind_speed_ms == 1.8
    assert vec.boundary_layer_height_m == 220.0
    assert vec.relative_humidity_pct == 68.0
    assert vec.is_delhi_winter_season is True
    assert vec.is_festival is True
    assert vec.festival_name is not None
    assert vec.upwind_fire_count_24h >= 1
    assert vec.upwind_fire_count_72h >= vec.upwind_fire_count_24h
    assert vec.feature_completeness == 1.0


def test_calendar_republic_day_holiday():
    cal = DelhiCalendar()
    feats = cal.features(date(2025, 1, 26))
    assert feats["is_holiday"] is True
    assert feats["holiday_name"] == "Republic Day"
    assert feats["is_delhi_winter_season"] is True


def test_empty_firms_without_key_returns_zeros():
    """Live FirmsClient with empty MAP_KEY yields no fires (safe offline default)."""
    from aether_agents.context.firms import FirmsClient

    client = FirmsClient(map_key="")
    assert client.fetch_fires(latitude=DELHI_LAT, longitude=DELHI_LON) == []
