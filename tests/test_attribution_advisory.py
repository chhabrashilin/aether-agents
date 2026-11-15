"""Unit tests for Attribution, Critic, Advisory, and supervisor wiring."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from aether_agents.agents.advisory import AdvisoryAgent, build_advisory
from aether_agents.agents.attribution import AttributionAgent, attribute_episode
from aether_agents.agents.critic import CriticAgent, critique_attribution
from aether_agents.agents.evidence import (
    ContextOutput,
    EpisodeOutput,
    EpisodePhase,
    EpisodeSeverity,
    EpisodeTimelinePoint,
    GrapStage,
    SourceClass,
    aqi_to_grap_stage,
    context_from_vector,
    episode_from_object,
)
from aether_agents.agents.supervisor import run_attribution_pipeline
from aether_agents.config import Settings


def _stubble_episode() -> EpisodeOutput:
    return EpisodeOutput(
        episode_id="ep-stubble-1",
        region="delhi-nct",
        severity=EpisodeSeverity.SEVERE,
        aqi_peak=420.0,
        aqi_mean=340.0,
        onset=datetime(2024, 11, 5, 4, 0, tzinfo=timezone.utc),
        peak=datetime(2024, 11, 5, 12, 0, tzinfo=timezone.utc),
        duration_hours=18.0,
        phase=EpisodePhase.PEAK,
        uncertainty=0.2,
        station_coverage=0.85,
        timeline=[
            EpisodeTimelinePoint(
                timestamp=datetime(2024, 11, 5, 8, 0, tzinfo=timezone.utc),
                aqi=360.0,
                phase=EpisodePhase.ONSET,
            ),
            EpisodeTimelinePoint(
                timestamp=datetime(2024, 11, 5, 12, 0, tzinfo=timezone.utc),
                aqi=420.0,
                phase=EpisodePhase.PEAK,
            ),
        ],
    )


def _stubble_context() -> ContextOutput:
    return ContextOutput(
        region="delhi-nct",
        observed_at=datetime(2024, 11, 5, 12, 0, tzinfo=timezone.utc),
        fire_count_upwind=55,
        wind_speed_ms=3.0,
        wind_direction_deg=320.0,
        blh_m=450.0,
        relative_humidity=65.0,
        is_stubble_season=True,
        is_festival_window=False,
        is_weekday=True,
        missing_fields=[],
        uncertainty=0.15,
    )


def _local_stagnation_context() -> ContextOutput:
    return ContextOutput(
        fire_count_upwind=0,
        wind_speed_ms=0.8,
        wind_direction_deg=90.0,
        blh_m=250.0,
        relative_humidity=82.0,
        is_stubble_season=False,
        is_festival_window=True,
        missing_fields=[],
        uncertainty=0.1,
    )


def test_attribution_favors_transport_stubble():
    result = attribute_episode(_stubble_episode(), _stubble_context(), Settings())
    assert result.method == "rule_score"
    assert result.dominant_class in {
        SourceClass.TRANSPORT_STUBBLE,
        SourceClass.MIXED,
    }
    probs = {p.source_class: p.probability for p in result.posteriors}
    assert abs(sum(probs.values()) - 1.0) < 1e-3
    assert probs[SourceClass.TRANSPORT_STUBBLE] >= probs[SourceClass.DUST]
    assert any(e.name == "fire_count_upwind" for e in result.evidence)


def test_attribution_favors_local_combustion():
    episode = _stubble_episode().model_copy(
        update={"severity": EpisodeSeverity.VERY_POOR, "aqi_peak": 360.0}
    )
    result = attribute_episode(episode, _local_stagnation_context(), Settings())
    assert result.dominant_class in {
        SourceClass.LOCAL_COMBUSTION,
        SourceClass.MIXED,
    }
    local = next(
        p for p in result.posteriors if p.source_class == SourceClass.LOCAL_COMBUSTION
    )
    assert local.probability >= 0.2
    assert local.supporting_evidence


def test_critic_dampens_overconfidence_with_missing_data():
    episode = _stubble_episode().model_copy(update={"station_coverage": 0.25})
    context = ContextOutput(
        fire_count_upwind=None,
        wind_speed_ms=None,
        blh_m=None,
        missing_fields=["fire_count_upwind", "wind_speed_ms", "blh_m"],
        uncertainty=0.5,
    )
    attribution = AttributionAgent(Settings()).run(episode, context)
    critic = CriticAgent(Settings()).run(attribution, episode, context)
    assert critic.missing_data_penalty > 0
    assert critic.overconfidence_dampening >= 0
    assert critic.revised_confidence <= attribution.confidence + 1e-9
    codes = {f.code for f in critic.findings}
    assert "missing_data" in codes or "low_station_coverage" in codes
    # Sparse enough → fail-closed (no overconfident dominant_source)
    assert critic.dominant_refused is True
    assert critic.revised_dominant_class is None
    total = sum(p.probability for p in critic.revised_posteriors)
    assert abs(total - 1.0) < 1e-3


def test_attribution_scorecard_is_exportable():
    result = attribute_episode(_stubble_episode(), _stubble_context(), Settings())
    assert result.scorecard
    assert any(c.feature == "fire_count_upwind" for c in result.scorecard)
    row = next(c for c in result.scorecard if c.feature == "fire_count_upwind")
    assert row.weight > 0
    assert row.contribution > 0
    assert row.rule
    payload = result.model_dump(mode="json")
    assert payload["scorecard"][0]["feature"]


def test_critic_flags_stubble_without_fires():
    episode = _stubble_episode()
    # Force a stubble-leaning attribution then strip fire signal for critic check
    context = _stubble_context().model_copy(
        update={"fire_count_upwind": 0, "is_stubble_season": True}
    )
    attribution = attribute_episode(episode, context, Settings())
    # Manually set dominant to transport_stubble with high peak for the check
    if attribution.dominant_class != SourceClass.TRANSPORT_STUBBLE:
        posts = list(attribution.posteriors)
        posts[0] = posts[0].model_copy(
            update={"source_class": SourceClass.TRANSPORT_STUBBLE, "probability": 0.6}
        )
        attribution = attribution.model_copy(
            update={
                "dominant_class": SourceClass.TRANSPORT_STUBBLE,
                "posteriors": posts,
                "evidence": [
                    e.model_copy(update={"value": 0, "missing": False})
                    if e.name == "fire_count_upwind"
                    else e
                    for e in attribution.evidence
                ],
            }
        )
    critic = critique_attribution(attribution, episode, context, Settings())
    codes = {f.code for f in critic.findings}
    assert "stubble_without_fires" in codes


def test_advisory_grap_stage_and_disclaimer():
    episode = _stubble_episode()
    context = _stubble_context()
    attribution = attribute_episode(episode, context, Settings())
    critic = critique_attribution(attribution, episode, context, Settings())
    advisory = build_advisory(episode, critic, Settings())
    assert advisory.grap_stage == GrapStage.STAGE_III
    assert advisory.grap_alignment_only is True
    assert "non-authoritative" in advisory.disclaimer.lower() or "legal" in advisory.disclaimer.lower()
    assert any("caqm" in s.lower() for s in advisory.official_sources)
    assert advisory.citations
    assert advisory.exposure_guidance
    assert all(g.citations for g in advisory.exposure_guidance)
    assert "alignment" in advisory.summary.lower() or "legal" in advisory.disclaimer.lower()


def test_aqi_to_grap_stage_boundaries():
    assert aqi_to_grap_stage(150) == GrapStage.NONE
    assert aqi_to_grap_stage(250) == GrapStage.STAGE_I
    assert aqi_to_grap_stage(350) == GrapStage.STAGE_II
    assert aqi_to_grap_stage(420) == GrapStage.STAGE_III
    assert aqi_to_grap_stage(460) == GrapStage.STAGE_IV
    assert aqi_to_grap_stage(None, EpisodeSeverity.VERY_POOR) == GrapStage.STAGE_II


def test_supervisor_pipeline_without_llm_keys():
    settings = Settings(llm_enabled=False, llm_api_key="")
    result = run_attribution_pipeline(
        _stubble_episode(), _stubble_context(), settings=settings
    )
    assert result.attribution.method == "rule_score"
    assert result.critic.method == "rule_score"
    assert result.advisory.method == "rule_score"
    assert result.advisory.episode_id == "ep-stubble-1"
    assert result.graph == ["attribution", "critic", "advisory"]


def test_supervisor_accepts_sibling_episode_context_shapes():
    from aether_agents.agents.base.types import (
        AqiCategory,
        ContextFeatureVector,
        EpisodeObject,
    )

    episode = EpisodeObject(
        episode_id="sib-1",
        station_id="DL001",
        onset_at=datetime(2024, 11, 6, 2, 0, tzinfo=timezone.utc),
        peak_at=datetime(2024, 11, 6, 10, 0, tzinfo=timezone.utc),
        peak_aqi=405,
        peak_category=AqiCategory.SEVERE,
        severity="Severe",
        duration_hours=16.0,
        mean_aqi=330.0,
        data_completeness=0.9,
        uncertainty=0.2,
    )
    context = ContextFeatureVector(
        location_id="delhi-centre",
        latitude=28.61,
        longitude=77.21,
        valid_at=datetime(2024, 11, 6, 10, 0, tzinfo=timezone.utc),
        upwind_fire_count_24h=30,
        wind_speed_ms=2.5,
        wind_direction_deg=300.0,
        boundary_layer_height_m=400.0,
        relative_humidity_pct=70.0,
        is_delhi_winter_season=True,
        feature_completeness=1.0,
    )
    adapted_ep = episode_from_object(episode)
    adapted_ctx = context_from_vector(context)
    assert adapted_ep.aqi_peak == 405.0
    assert adapted_ctx.fire_count_upwind == 30
    result = run_attribution_pipeline(episode, context, Settings())
    assert result.advisory.episode_id == "sib-1"


def test_llm_flag_does_not_require_network():
    settings = Settings(llm_enabled=True, llm_api_key="")
    result = AttributionAgent(settings).run(_stubble_episode(), _stubble_context())
    assert result.method == "rule_score"
    assert any("LLM" in n for n in result.notes)


@pytest.fixture
def api_client():
    from fastapi.testclient import TestClient

    from apps.api.main import app

    return TestClient(app)


def test_attribution_demo_endpoint(api_client):
    res = api_client.get("/v1/attribution/demo")
    assert res.status_code == 200
    body = res.json()
    assert "result" in body
    assert body["result"]["advisory"]["grap_stage"] in {"none", "I", "II", "III", "IV"}
    assert "disclaimer" in body["result"]["advisory"]


def test_attribution_run_endpoint(api_client):
    payload = {
        "episode": _stubble_episode().model_dump(mode="json"),
        "context": _stubble_context().model_dump(mode="json"),
    }
    res = api_client.post("/v1/attribution/run", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["attribution"]["episode_id"] == "ep-stubble-1"
    assert len(body["attribution"]["posteriors"]) == 5
    assert body["attribution"]["scorecard"]


def test_pipeline_run_fixture_endpoint(api_client):
    res = api_client.get("/v1/pipeline/run", params={"mode": "fixture"})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "fixture"
    assert body["episodes_detected"] >= 1
    assert body["science"]["attribution"]["scorecard"]
    assert body["provenance"]["run_id"] == body["run_id"]


def test_metrics_prometheus_text(api_client):
    res = api_client.get("/metrics")
    assert res.status_code == 200
    assert "aether_agents_info" in res.text
    assert "text/plain" in res.headers.get("content-type", "")
