"""Episode-detection metrics with explicit missing-data handling.

Gaps are never silently imputed. Hours with missing observations or missing
predictions are excluded from pairwise scores and reported separately as
coverage diagnostics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Sequence

# CPCB National AQI category thresholds (India).
AQI_VERY_POOR_MIN = 301
AQI_SEVERE_MIN = 401


@dataclass(frozen=True)
class EpisodeWindow:
    """Inclusive start index, exclusive end index on an hourly series."""

    start: int
    end: int
    peak_index: int
    peak_aqi: float
    severity: str  # "very_poor" | "severe"


@dataclass(frozen=True)
class DetectionMetrics:
    """Pairwise episode-hour metrics computed only on jointly observed hours."""

    n_hours: int
    n_scored: int
    n_missing_obs: int
    n_missing_pred: int
    n_missing_either: int
    coverage: float
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float | None
    recall: float | None
    f1: float | None
    onset_error_hours: float | None
    peak_timing_error_hours: float | None
    peak_aqi_error: float | None

    def to_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def aqi_category(aqi: float | None) -> str | None:
    """Map AQI to CPCB category name; None if missing."""
    if aqi is None:
        return None
    if aqi >= AQI_SEVERE_MIN:
        return "severe"
    if aqi >= AQI_VERY_POOR_MIN:
        return "very_poor"
    if aqi >= 201:
        return "poor"
    if aqi >= 101:
        return "moderate"
    if aqi >= 51:
        return "satisfactory"
    if aqi >= 0:
        return "good"
    return None


def is_episode_hour(
    aqi: float | None,
    *,
    threshold: float = AQI_VERY_POOR_MIN,
) -> bool | None:
    """Return True/False for episode membership, or None when AQI is missing."""
    if aqi is None:
        return None
    return aqi >= threshold


def detect_episodes(
    aqi_series: Sequence[float | None],
    *,
    threshold: float = AQI_VERY_POOR_MIN,
    min_duration_hours: int = 6,
) -> list[EpisodeWindow]:
    """Detect sustained Very Poor / Severe windows; gaps break continuity.

    A run of consecutive non-missing hours at or above ``threshold`` lasting at
    least ``min_duration_hours`` becomes an episode. Missing hours terminate
    the current run (no bridging across gaps).
    """
    episodes: list[EpisodeWindow] = []
    run_start: int | None = None
    run_values: list[tuple[int, float]] = []

    def _flush() -> None:
        nonlocal run_start, run_values
        if run_start is None or len(run_values) < min_duration_hours:
            run_start = None
            run_values = []
            return
        peak_i, peak_v = max(run_values, key=lambda iv: iv[1])
        severity = "severe" if peak_v >= AQI_SEVERE_MIN else "very_poor"
        episodes.append(
            EpisodeWindow(
                start=run_start,
                end=run_values[-1][0] + 1,
                peak_index=peak_i,
                peak_aqi=peak_v,
                severity=severity,
            )
        )
        run_start = None
        run_values = []

    for i, value in enumerate(aqi_series):
        if value is None or value < threshold:
            _flush()
            continue
        if run_start is None:
            run_start = i
        run_values.append((i, float(value)))
    _flush()
    return episodes


def _safe_div(num: float, den: float) -> float | None:
    if den == 0:
        return None
    return num / den


def _binary_mask(
    series: Sequence[float | None],
    *,
    threshold: float,
) -> list[bool | None]:
    return [is_episode_hour(v, threshold=threshold) for v in series]


def episode_detection_metrics(
    observed_aqi: Sequence[float | None],
    predicted_aqi: Sequence[float | None],
    *,
    threshold: float = AQI_VERY_POOR_MIN,
    min_duration_hours: int = 6,
) -> DetectionMetrics:
    """Score predicted vs reference AQI series with explicit gap accounting.

    Only hours where both series are non-missing contribute to TP/FP/FN/TN.
    Onset and peak errors compare the first detected episode in each series
    (after applying the same duration rule); if either side has no episode on
    scored hours, timing errors are reported as None.
    """
    if len(observed_aqi) != len(predicted_aqi):
        raise ValueError(
            f"Length mismatch: observed={len(observed_aqi)} predicted={len(predicted_aqi)}"
        )

    n = len(observed_aqi)
    obs_mask = _binary_mask(observed_aqi, threshold=threshold)
    pred_mask = _binary_mask(predicted_aqi, threshold=threshold)

    tp = fp = fn = tn = 0
    n_missing_obs = n_missing_pred = n_missing_either = 0

    for o, p in zip(obs_mask, pred_mask):
        if o is None:
            n_missing_obs += 1
        if p is None:
            n_missing_pred += 1
        if o is None or p is None:
            n_missing_either += 1
            continue
        if o and p:
            tp += 1
        elif p and not o:
            fp += 1
        elif o and not p:
            fn += 1
        else:
            tn += 1

    n_scored = tp + fp + fn + tn
    coverage = _safe_div(float(n_scored), float(n)) or 0.0
    precision = _safe_div(float(tp), float(tp + fp))
    recall = _safe_div(float(tp), float(tp + fn))
    f1 = None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)

    # Timing: detect on full series but compare only when both have episodes.
    obs_eps = detect_episodes(
        observed_aqi, threshold=threshold, min_duration_hours=min_duration_hours
    )
    pred_eps = detect_episodes(
        predicted_aqi, threshold=threshold, min_duration_hours=min_duration_hours
    )
    onset_err = peak_time_err = peak_aqi_err = None
    if obs_eps and pred_eps:
        onset_err = float(pred_eps[0].start - obs_eps[0].start)
        peak_time_err = float(pred_eps[0].peak_index - obs_eps[0].peak_index)
        peak_aqi_err = float(pred_eps[0].peak_aqi - obs_eps[0].peak_aqi)

    return DetectionMetrics(
        n_hours=n,
        n_scored=n_scored,
        n_missing_obs=n_missing_obs,
        n_missing_pred=n_missing_pred,
        n_missing_either=n_missing_either,
        coverage=coverage,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        onset_error_hours=onset_err,
        peak_timing_error_hours=peak_time_err,
        peak_aqi_error=peak_aqi_err,
    )


def missingness_report(series: Iterable[float | None]) -> dict[str, float | int]:
    """Summarize gap structure for a single AQI series."""
    values = list(series)
    n = len(values)
    n_missing = sum(1 for v in values if v is None)
    # Contiguous gap runs
    gaps: list[int] = []
    run = 0
    for v in values:
        if v is None:
            run += 1
        elif run:
            gaps.append(run)
            run = 0
    if run:
        gaps.append(run)
    return {
        "n_hours": n,
        "n_missing": n_missing,
        "missing_fraction": (n_missing / n) if n else 0.0,
        "n_gap_runs": len(gaps),
        "max_gap_hours": max(gaps) if gaps else 0,
        "mean_gap_hours": (sum(gaps) / len(gaps)) if gaps else 0.0,
    }
