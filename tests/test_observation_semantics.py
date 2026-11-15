"""Guards: CPCB sub-index vs concentration must not mix silently."""

from __future__ import annotations

from datetime import datetime, timezone

from aether_agents.agents.base.types import Observation, pm25_to_cpcb_aqi
from aether_agents.agents.episode import EpisodeAgent, resolve_episode_aqi


def test_concentration_maps_via_breakpoints():
    obs = Observation(
        station_id="s1",
        observed_at=datetime(2024, 11, 1, tzinfo=timezone.utc),
        pollutant="pm25",
        value=200.0,
        value_semantics="concentration",
        unit="ug/m3",
    )
    aqi = obs.resolved_aqi()
    assert aqi == pm25_to_cpcb_aqi(200.0)
    assert aqi >= 301
    assert "mapped_pm25" in ",".join(obs.resolution_notes)


def test_sub_index_not_passed_through_concentration_mapping():
    # A sub-index of 200 is Poor-band AQI; if wrongly treated as µg/m³ it would
    # map into Very Poor. Guard must keep 200.
    obs = Observation(
        station_id="s1",
        observed_at=datetime(2024, 11, 1, tzinfo=timezone.utc),
        pollutant="pm25",
        value=200.0,
        value_semantics="sub_index",
        unit="aqi_sub_index",
    )
    assert obs.resolved_aqi() == 200
    assert "sub_index" in ",".join(obs.resolution_notes)


def test_unknown_semantics_refuses_conversion():
    obs = Observation(
        station_id="s1",
        observed_at=datetime(2024, 11, 1, tzinfo=timezone.utc),
        pollutant="pm25",
        value=200.0,
        value_semantics="unknown",
        unit="mystery",
    )
    assert obs.resolved_aqi() is None
    assert any("refused" in n for n in obs.resolution_notes)


def test_prefer_concentration_over_station_aqi():
    obs = Observation(
        station_id="s1",
        observed_at=datetime(2024, 11, 1, tzinfo=timezone.utc),
        pollutant="pm25",
        value=250.0,  # → Severe-ish via breakpoints
        value_semantics="concentration",
        unit="ug/m3",
        aqi=220,  # Poor; should be ignored when prefer_concentration=True
    )
    preferred = resolve_episode_aqi(obs, prefer_concentration=True)
    explicit = resolve_episode_aqi(obs, prefer_concentration=False)
    assert preferred == pm25_to_cpcb_aqi(250.0)
    assert explicit == 220
    assert preferred != explicit


def test_episode_notes_include_calibration():
    start = datetime(2024, 12, 1, tzinfo=timezone.utc)
    from datetime import timedelta

    obs = [
        Observation(
            station_id="DL001",
            observed_at=start + timedelta(hours=i),
            pollutant="pm25",
            value=200.0,
            value_semantics="concentration",
            unit="ug/m3",
        )
        for i in range(8)
    ]
    episodes = EpisodeAgent(min_duration_hours=6.0).detect(obs)
    assert len(episodes) == 1
    assert any("calibration" in n for n in episodes[0].notes)
