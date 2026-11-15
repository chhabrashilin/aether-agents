"""EpisodeAgent tests with synthetic AQI series (no live data)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aether_agents.agents.base.types import AqiCategory, Observation, aqi_category
from aether_agents.agents.episode import EpisodeAgent


def _series(
    station_id: str,
    aqi_values: list[int | None],
    *,
    start: datetime | None = None,
) -> list[Observation]:
    start = start or datetime(2024, 11, 1, 0, 0, tzinfo=timezone.utc)
    return [
        Observation(
            station_id=station_id,
            observed_at=start + timedelta(hours=i),
            pollutant="pm25",
            aqi=aqi,
        )
        for i, aqi in enumerate(aqi_values)
    ]


def test_aqi_category_rules():
    assert aqi_category(40) == AqiCategory.GOOD
    assert aqi_category(80) == AqiCategory.SATISFACTORY
    assert aqi_category(150) == AqiCategory.MODERATE
    assert aqi_category(250) == AqiCategory.POOR
    assert aqi_category(350) == AqiCategory.VERY_POOR
    assert aqi_category(450) == AqiCategory.SEVERE
    assert aqi_category(None) == AqiCategory.UNKNOWN


def test_detects_very_poor_severe_window():
    # 4h below floor, then 10h Very Poor/Severe, then decay
    values: list[int | None] = [200] * 4 + [320, 340, 360, 410, 430, 420, 400, 380, 350, 330] + [
        250,
        200,
    ]
    agent = EpisodeAgent(min_duration_hours=6.0)
    episodes = agent.detect(_series("DL001", values))
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.station_id == "DL001"
    assert ep.peak_category == AqiCategory.SEVERE
    assert ep.peak_aqi == 430
    assert ep.onset_at < ep.peak_at
    assert ep.decay_at is not None
    assert ep.ended_at is not None
    assert ep.severity in {"severe", "extreme", "high", "elevated"}
    assert 0.0 <= ep.uncertainty <= 1.0
    assert ep.data_completeness == 1.0


def test_short_spike_not_episode():
    values: list[int | None] = [180, 320, 330, 200, 180]
    agent = EpisodeAgent(min_duration_hours=6.0)
    assert agent.detect(_series("DL001", values)) == []


def test_uncertainty_rises_with_gaps():
    # Elevated window with internal nulls → lower completeness / higher uncertainty
    values: list[int | None] = [320, None, 340, None, 360, 380, 400, 390]
    agent = EpisodeAgent(min_duration_hours=6.0, max_gap_hours=3.0)
    episodes = agent.detect(_series("DL002", values))
    assert len(episodes) == 1
    assert episodes[0].data_completeness < 1.0
    assert episodes[0].uncertainty > 0.05


def test_open_episode_when_still_elevated():
    values: list[int | None] = [310, 320, 330, 340, 350, 360, 370]
    agent = EpisodeAgent(min_duration_hours=6.0)
    episodes = agent.detect(_series("DL003", values))
    assert len(episodes) == 1
    assert episodes[0].is_open is True
    assert episodes[0].ended_at is None
    assert episodes[0].uncertainty >= 0.15


def test_pm25_concentration_derives_aqi():
    start = datetime(2024, 12, 1, tzinfo=timezone.utc)
    obs = [
        Observation(
            station_id="DL001",
            observed_at=start + timedelta(hours=i),
            pollutant="pm25",
            value=200.0,  # maps into Very Poor CPCB sub-index
            value_semantics="concentration",
            unit="ug/m3",
            aqi=None,
        )
        for i in range(8)
    ]
    episodes = EpisodeAgent(min_duration_hours=6.0).detect(obs)
    assert len(episodes) == 1
    assert episodes[0].peak_aqi >= 301
