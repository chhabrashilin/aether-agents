"""EpisodeAgent: CPCB AQI Very Poor / Severe window detection (deterministic).

CPCB AQI mapping (v1)
---------------------
Episode hours are defined on the **CPCB National AQI 0–500 scale**
(Very Poor floor = 301). Inputs may arrive as:

1. Explicit station ``aqi`` (preferred when both sources agree),
2. OpenAQ / monitor **PM₂.₅ concentration (µg/m³)** with
   ``value_semantics="concentration"``, mapped via published CPCB PM₂.₅
   breakpoints (:func:`~aether_agents.agents.base.types.pm25_to_cpcb_aqi`),
3. CPCB OGD **pollutant sub-index** with ``value_semantics="sub_index"``,
   used directly as that pollutant's contribution (not re-mapped).

**Preference when both concentration and station AQI exist:** concentration-
derived sub-index is preferred for peak/mean math so OpenAQ hourly history
and CPCB snapshots stay comparable on a documented transfer function.
Station AQI remains available in notes for audit.

Calibration notes: breakpoint mapping is the published table, not a
Delhi-specific co-location calibration. Cross-network bias is uncorrected in v1.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from aether_agents.agents.base.types import (
    EPISODE_AQI_FLOOR,
    AqiCategory,
    EpisodeObject,
    Observation,
    aqi_category,
    pm25_to_cpcb_aqi,
)


def _severity(peak_aqi: int, duration_hours: float) -> str:
    """Map peak AQI + duration to a coarse severity label."""
    cat = aqi_category(peak_aqi)
    if cat == AqiCategory.SEVERE and duration_hours >= 24:
        return "extreme"
    if cat == AqiCategory.SEVERE:
        return "severe"
    if cat == AqiCategory.VERY_POOR and duration_hours >= 24:
        return "high"
    if cat == AqiCategory.VERY_POOR:
        return "elevated"
    return "moderate"


def _uncertainty(*, completeness: float, is_open: bool) -> float:
    """Higher uncertainty when data are incomplete or the episode is still open."""
    gap_penalty = 1.0 - max(0.0, min(1.0, completeness))
    open_penalty = 0.15 if is_open else 0.0
    return round(min(1.0, 0.05 + 0.8 * gap_penalty + open_penalty), 3)


def resolve_episode_aqi(obs: Observation, *, prefer_concentration: bool = True) -> int | None:
    """Resolve AQI for episode detection with explicit concentration preference.

    When ``prefer_concentration`` is True and a PM₂.₅ concentration is present,
    use the CPCB breakpoint mapping even if ``aqi`` is also set. Otherwise
    defer to :meth:`Observation.resolved_aqi` (which never mixes unknown
    semantics).
    """
    pollutant = obs.pollutant.lower().replace(".", "")
    if (
        prefer_concentration
        and obs.value is not None
        and obs.value_semantics == "concentration"
        and pollutant in {"pm25", "pm2.5"}
    ):
        return pm25_to_cpcb_aqi(float(obs.value))
    return obs.resolved_aqi()


class EpisodeAgent:
    """Detect sustained Very Poor / Severe AQI episodes from observation series.

    Rules (v1, classical):
    - CPCB categories via :func:`aqi_category`.
    - An episode hour is any hour with resolved AQI >= 301 (Very Poor floor).
    - Prefer PM₂.₅ concentration→AQI when ``prefer_concentration`` (default).
    - A contiguous run of episode hours lasting ``min_duration_hours`` becomes
      an episode (missing hours inside a gap shorter than ``max_gap_hours``
      do not split the run; longer gaps end it).
    - Onset = first episode hour; peak = max AQI timestamp; decay = first hour
      after the peak that falls below the floor (or None if still elevated);
      ended_at = last episode hour when closed.
    """

    def __init__(
        self,
        *,
        min_duration_hours: float = 6.0,
        max_gap_hours: float = 3.0,
        aqi_floor: int = EPISODE_AQI_FLOOR,
        prefer_concentration: bool = True,
    ) -> None:
        self.min_duration_hours = min_duration_hours
        self.max_gap_hours = max_gap_hours
        self.aqi_floor = aqi_floor
        self.prefer_concentration = prefer_concentration

    def detect(self, observations: list[Observation]) -> list[EpisodeObject]:
        by_station: dict[str, list[Observation]] = defaultdict(list)
        for obs in observations:
            by_station[obs.station_id].append(obs)

        episodes: list[EpisodeObject] = []
        for station_id, rows in by_station.items():
            episodes.extend(self._detect_station(station_id, rows))
        episodes.sort(key=lambda e: e.onset_at)
        return episodes

    def _detect_station(
        self,
        station_id: str,
        rows: list[Observation],
    ) -> list[EpisodeObject]:
        series = sorted(rows, key=lambda o: o.observed_at)
        if not series:
            return []

        # Build hourly timeline of (timestamp, aqi|None)
        points: list[tuple[datetime, int | None]] = []
        used_concentration = 0
        used_sub_index = 0
        used_station_aqi = 0
        refused_unknown = 0
        for obs in series:
            ts = obs.observed_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            aqi = resolve_episode_aqi(obs, prefer_concentration=self.prefer_concentration)
            points.append((ts, aqi))
            if obs.value_semantics == "concentration" and obs.value is not None and aqi is not None:
                used_concentration += 1
            elif obs.value_semantics == "sub_index" and obs.value is not None:
                used_sub_index += 1
            elif obs.aqi is not None:
                used_station_aqi += 1
            if any("refused" in n for n in obs.resolution_notes):
                refused_unknown += 1

        # Expected cadence from median step (fallback 1h).
        if len(points) >= 2:
            deltas = [
                (points[i][0] - points[i - 1][0]).total_seconds()
                for i in range(1, len(points))
                if (points[i][0] - points[i - 1][0]).total_seconds() > 0
            ]
            step_s = sorted(deltas)[len(deltas) // 2] if deltas else 3600.0
        else:
            step_s = 3600.0
        step = timedelta(seconds=step_s)

        runs = self._contiguous_runs(points, step)
        series_end = points[-1][0]
        out: list[EpisodeObject] = []
        for run in runs:
            duration_h = (run[-1][0] - run[0][0]).total_seconds() / 3600.0 + step_s / 3600.0
            if duration_h + 1e-9 < self.min_duration_hours:
                continue
            aqi_vals = [aqi for _, aqi in run if aqi is not None]
            if not aqi_vals:
                continue
            peak_aqi = max(aqi_vals)
            peak_at = next(ts for ts, aqi in run if aqi == peak_aqi)
            mean_aqi = sum(aqi_vals) / len(aqi_vals)

            # Completeness: fraction of steps in [onset, end] with non-null AQI.
            onset = run[0][0]
            end = run[-1][0]
            expected = max(1, int(round((end - onset).total_seconds() / step_s)) + 1)
            observed_non_null = sum(1 for _, aqi in run if aqi is not None)
            completeness = min(1.0, observed_non_null / expected)

            # Open only if the elevated run reaches the latest observation and
            # that observation is still at/above the Very Poor floor.
            last_aqi = run[-1][1]
            reaches_series_end = end >= series_end - step
            is_open = (
                reaches_series_end
                and last_aqi is not None
                and last_aqi >= self.aqi_floor
            )

            # Decay: first post-peak hour in the full series that falls below floor.
            decay_at: datetime | None = None
            for ts, aqi in points:
                if ts <= peak_at:
                    continue
                if aqi is not None and aqi < self.aqi_floor:
                    decay_at = ts
                    break
            if decay_at is None and not is_open:
                decay_at = end

            peak_cat = aqi_category(peak_aqi)
            notes = [
                "aqi_scale=CPCB_National_AQI_0_500",
                "episode_floor=Very_Poor_301",
                (
                    "prefer_concentration="
                    f"{self.prefer_concentration}; "
                    f"hours_from_concentration={used_concentration}, "
                    f"sub_index={used_sub_index}, station_aqi={used_station_aqi}"
                ),
                (
                    "calibration=published_CPCB_PM25_breakpoints_only; "
                    "no_Delhi_colocation_transfer_function_in_v1"
                ),
            ]
            if refused_unknown:
                notes.append(
                    f"refused_unknown_semantics_hours={refused_unknown}"
                )
            out.append(
                EpisodeObject(
                    episode_id=f"ep-{station_id}-{uuid4().hex[:10]}",
                    station_id=station_id,
                    onset_at=onset,
                    peak_at=peak_at,
                    decay_at=decay_at,
                    ended_at=None if is_open else end,
                    peak_aqi=peak_aqi,
                    peak_category=peak_cat,
                    category_at_peak=peak_cat,
                    severity=_severity(peak_aqi, duration_h),
                    duration_hours=round(duration_h, 2),
                    mean_aqi=round(mean_aqi, 1),
                    data_completeness=round(completeness, 3),
                    uncertainty=_uncertainty(completeness=completeness, is_open=is_open),
                    is_open=is_open,
                    notes=notes,
                )
            )
        return out

    def _contiguous_runs(
        self,
        points: list[tuple[datetime, int | None]],
        step: timedelta,
    ) -> list[list[tuple[datetime, int | None]]]:
        """Group elevated AQI hours into runs, allowing short missing gaps."""
        max_gap = timedelta(hours=self.max_gap_hours)
        runs: list[list[tuple[datetime, int | None]]] = []
        current: list[tuple[datetime, int | None]] = []

        def flush() -> None:
            nonlocal current
            if current:
                runs.append(current)
                current = []

        for ts, aqi in points:
            elevated = aqi is not None and aqi >= self.aqi_floor
            if not elevated:
                # Missing or below-floor: may bridge a short gap inside a run.
                if current and aqi is None:
                    gap = ts - current[-1][0]
                    if gap <= max_gap + step:
                        current.append((ts, aqi))
                        continue
                flush()
                continue

            if not current:
                current = [(ts, aqi)]
                continue

            gap = ts - current[-1][0]
            if gap <= max_gap + step:
                current.append((ts, aqi))
            else:
                flush()
                current = [(ts, aqi)]

        flush()
        return runs
