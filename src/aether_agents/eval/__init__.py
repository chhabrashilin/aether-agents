"""Winter-season evaluation helpers: detection metrics, fixtures, case rubrics."""

from aether_agents.eval.fixtures import (
    CASE_STUDIES,
    CaseStudyMeta,
    build_synthetic_winter_series,
    ensure_bundled_fixture,
    load_synthetic_winter,
)
from aether_agents.eval.metrics import (
    AQI_SEVERE_MIN,
    AQI_VERY_POOR_MIN,
    DetectionMetrics,
    EpisodeWindow,
    aqi_category,
    detect_episodes,
    episode_detection_metrics,
    is_episode_hour,
    missingness_report,
)
from aether_agents.eval.rubric import (
    CaseStudyScorecard,
    CriterionScore,
    RubricCriterion,
    criteria_for_case,
    demo_scorecards,
    rubric_catalog,
    score_case_study,
)

__all__ = [
    "AQI_SEVERE_MIN",
    "AQI_VERY_POOR_MIN",
    "CASE_STUDIES",
    "CaseStudyMeta",
    "CaseStudyScorecard",
    "CriterionScore",
    "DetectionMetrics",
    "EpisodeWindow",
    "RubricCriterion",
    "aqi_category",
    "build_synthetic_winter_series",
    "criteria_for_case",
    "demo_scorecards",
    "detect_episodes",
    "ensure_bundled_fixture",
    "episode_detection_metrics",
    "is_episode_hour",
    "load_synthetic_winter",
    "missingness_report",
    "rubric_catalog",
    "score_case_study",
]
