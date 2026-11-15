"""Tests for winter case-study rubrics."""

import pytest

from aether_agents.eval.rubric import (
    criteria_for_case,
    demo_scorecards,
    rubric_catalog,
    score_case_study,
)


def test_criteria_cover_three_cases():
    for case_id in ("diwali", "stubble", "stagnation"):
        crit = criteria_for_case(case_id)
        assert len(crit) == 6
        ids = [c.criterion_id for c in crit]
        assert "temporal_alignment" in ids
        assert "uncertainty_language" in ids


def test_score_case_study_validates():
    scores = {
        "temporal_alignment": 2,
        "evidence_citation": 1,
        "uncertainty_language": 2,
        "grap_appropriateness": 1,
        "local_combustion_prior": 2,
        "short_duration_handling": 0,
    }
    card = score_case_study("diwali", scores, reviewer="test")
    assert card.total == 8
    assert card.max_total == 12
    assert card.normalized == pytest.approx(8 / 12)
    payload = card.to_dict()
    assert "not fabricated" in payload["disclaimer"].lower() or "ground truth" in payload["disclaimer"]


def test_score_rejects_unknown_case():
    with pytest.raises(KeyError):
        criteria_for_case("monsoon")


def test_demo_scorecards():
    cards = demo_scorecards()
    assert {c.case_id for c in cards} == {"diwali", "stubble", "stagnation"}
    catalog = rubric_catalog()
    assert "disclaimer" in catalog
    assert set(catalog["cases"]) == {"diwali", "stubble", "stagnation"}
