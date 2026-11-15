"""Tests for episode detection metrics and missing-data handling."""

from aether_agents.eval.fixtures import build_synthetic_winter_series, load_synthetic_winter
from aether_agents.eval.metrics import (
    AQI_VERY_POOR_MIN,
    detect_episodes,
    episode_detection_metrics,
    is_episode_hour,
    missingness_report,
)


def test_is_episode_hour_missing():
    assert is_episode_hour(None) is None
    assert is_episode_hour(300) is False
    assert is_episode_hour(301) is True


def test_detect_episodes_requires_duration_and_breaks_on_gaps():
    # 8 hours above threshold → one episode
    series = [100.0] * 5 + [350.0] * 8 + [100.0] * 5
    eps = detect_episodes(series, min_duration_hours=6)
    assert len(eps) == 1
    assert eps[0].start == 5
    assert eps[0].end == 13

    # Gap in the middle breaks the run into two short fragments → none kept
    gappy = [350.0] * 4 + [None] + [350.0] * 4
    assert detect_episodes(gappy, min_duration_hours=6) == []


def test_metrics_exclude_missing_pairs():
    observed = [400.0, None, 100.0, 400.0]
    predicted = [400.0, 400.0, None, 100.0]
    m = episode_detection_metrics(observed, predicted, min_duration_hours=1)
    # Scored hours: index 0 (TP) and index 3 (FN) → 2 scored
    assert m.n_hours == 4
    assert m.n_scored == 2
    assert m.n_missing_either == 2
    assert m.true_positives == 1
    assert m.false_negatives == 1
    assert m.precision == 1.0
    assert m.recall == 0.5


def test_metrics_length_mismatch():
    try:
        episode_detection_metrics([1.0], [1.0, 2.0])
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Length mismatch" in str(exc)


def test_missingness_report():
    report = missingness_report([1.0, None, None, 2.0, None])
    assert report["n_missing"] == 3
    assert report["n_gap_runs"] == 2
    assert report["max_gap_hours"] == 2


def test_synthetic_fixture_has_gaps_and_episodes():
    data = build_synthetic_winter_series(seed=2023, include_gaps=True)
    obs = data["observed_aqi"]
    pred = data["predicted_aqi"]
    assert len(obs) == data["meta"]["n_hours"]
    assert any(v is None for v in obs)
    assert any(v is None for v in pred)
    eps = detect_episodes(obs, threshold=AQI_VERY_POOR_MIN, min_duration_hours=6)
    assert len(eps) >= 1
    metrics = episode_detection_metrics(obs, pred, min_duration_hours=6)
    assert 0.0 < metrics.coverage < 1.0
    assert metrics.n_missing_either > 0
    assert metrics.f1 is not None


def test_bundled_fixture_roundtrip(tmp_path):
    from aether_agents.eval.fixtures import ensure_bundled_fixture

    path = ensure_bundled_fixture()
    assert path.exists()
    loaded = load_synthetic_winter(path=path)
    assert loaded["meta"]["name"] == "synthetic_delhi_winter_2023_24"
    assert "case_studies" in loaded
