"""Integration: full offline pipeline on fixtures."""

from __future__ import annotations

from aether_agents.config import Settings
from aether_agents.pipeline.full import PipelineMode, run_full_pipeline


def test_full_offline_pipeline_detects_episode_and_scorecard():
    result = run_full_pipeline(
        mode=PipelineMode.FIXTURE,
        settings=Settings(llm_enabled=False),
    )
    assert result.mode == PipelineMode.FIXTURE
    assert result.observations_used >= 6
    assert result.episodes_detected >= 1
    assert result.episode is not None
    assert result.context is not None
    assert result.science is not None
    assert result.science.attribution.scorecard
    assert any(c.feature != "prior_base" for c in result.science.attribution.scorecard)
    assert result.science.advisory.grap_alignment_only is True
    assert "caqm.nic.in" in result.science.advisory.disclaimer.lower() or any(
        "caqm" in c.lower() for c in result.science.advisory.official_sources
    )
    assert "ingest_fixture" in result.provenance.get("steps", [])
    assert "advisory" in result.provenance.get("steps", [])
    assert result.run_id.startswith("run-")


def test_full_pipeline_export_json_roundtrip():
    result = run_full_pipeline(mode="fixture", settings=Settings())
    payload = result.model_dump(mode="json")
    assert payload["science"]["attribution"]["scorecard"]
    assert payload["provenance"]["mode"] == "fixture"


def test_critic_fail_closed_on_sparse_in_pipeline_context():
    from datetime import datetime, timezone

    from aether_agents.agents.attribution import AttributionAgent
    from aether_agents.agents.critic import CriticAgent
    from aether_agents.agents.evidence import ContextOutput, EpisodeOutput, EpisodeSeverity

    episode = EpisodeOutput(
        episode_id="sparse-1",
        severity=EpisodeSeverity.SEVERE,
        aqi_peak=420.0,
        station_coverage=0.15,
        uncertainty=0.6,
    )
    context = ContextOutput(
        fire_count_upwind=None,
        wind_speed_ms=None,
        wind_direction_deg=None,
        blh_m=None,
        relative_humidity=None,
        missing_fields=[
            "fire_count_upwind",
            "wind_speed_ms",
            "wind_direction_deg",
            "blh_m",
            "relative_humidity",
        ],
        uncertainty=0.8,
        observed_at=datetime(2024, 11, 1, tzinfo=timezone.utc),
    )
    attribution = AttributionAgent(Settings()).run(episode, context)
    critic = CriticAgent(Settings()).run(attribution, episode, context)
    assert critic.dominant_refused is True
    assert critic.revised_dominant_class is None
    assert critic.revised_confidence <= 0.25
    codes = {f.code for f in critic.findings}
    assert "refuse_dominant_sparse_data" in codes
