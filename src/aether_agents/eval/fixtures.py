"""Synthetic Delhi–NCT winter fixtures for offline evaluation.

These series are constructed to exercise episode detection and case-study
rubrics. They are **not** observational archives and must not be cited as
measured ground truth.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Winter 2023–24 style calendar (synthetic): 1 Oct 2023 – 31 Mar 2024 ≈ 183 days.
WINTER_HOURS = 183 * 24  # 4392


@dataclass(frozen=True)
class CaseStudyMeta:
    """Literature-aligned case window metadata (no fabricated measurements)."""

    case_id: str
    label: str
    # Hour indices into the synthetic winter series (0 = 2023-10-01 00:00 IST).
    window_start: int
    window_end: int
    narrative: str
    expected_source_classes: tuple[str, ...]
    literature_hooks: tuple[str, ...]


CASE_STUDIES: tuple[CaseStudyMeta, ...] = (
    CaseStudyMeta(
        case_id="diwali",
        label="Diwali festival combustion",
        # Approx. early Nov (Diwali 2023 ~ 12 Nov → day index ~42).
        window_start=42 * 24,
        window_end=45 * 24,
        narrative=(
            "Short multi-day festival window with elevated local combustion "
            "signals and often weak nocturnal mixing. Evaluation checks "
            "temporal alignment and local-combustion evidence language, not "
            "a pollutant concentration truth set."
        ),
        expected_source_classes=("local_combustion", "mixed"),
        literature_hooks=(
            "Festival-period PM spikes in Delhi literature",
            "CAQM / GRAP pre-festival advisories (timeline alignment)",
        ),
    ),
    CaseStudyMeta(
        case_id="stubble",
        label="Post-monsoon stubble / regional transport",
        # Mid–late October through early November regional burning season.
        window_start=15 * 24,
        window_end=40 * 24,
        narrative=(
            "Broader post-monsoon window associated with agricultural residue "
            "burning upwind of Delhi–NCR. Rubric scores fire/transport "
            "evidence consistency and uncertainty phrasing against published "
            "case timelines, not station-by-station labels."
        ),
        expected_source_classes=("stubble_transport", "mixed"),
        literature_hooks=(
            "NW India residue-burning seasonality (Oct–Nov)",
            "Transport + local mixture framing in winter episode studies",
        ),
    ),
    CaseStudyMeta(
        case_id="stagnation",
        label="Local winter stagnation",
        # Mid-December cold-pool / low-BLH style window.
        window_start=75 * 24,
        window_end=85 * 24,
        narrative=(
            "Multi-day mid-winter stagnation with suppressed boundary-layer "
            "mixing and dominant local sources. Rubric emphasizes meteorology "
            "context and avoidance of over-attributing distant fires."
        ),
        expected_source_classes=("local_combustion", "industrial", "mixed"),
        literature_hooks=(
            "Winter shallow-BLH / calm-wind stagnation episodes",
            "Local combustion and industrial contributions under poor dispersion",
        ),
    ),
)


def _clamp_aqi(value: float) -> float:
    return max(0.0, min(500.0, value))


def build_synthetic_winter_series(
    *,
    seed: int = 2023,
    include_gaps: bool = True,
) -> dict[str, Any]:
    """Build a deterministic synthetic hourly AQI + context fixture.

    Returns a dict with parallel arrays suitable for JSON serialization and
    notebook plotting. ``observed_aqi`` is the reference series used for
    detection metrics; ``predicted_aqi`` is a slightly lagged, noisier twin
    that mimics an imperfect nowcast. Both contain deliberate missing hours
    when ``include_gaps`` is True.
    """
    # Lightweight LCG so we avoid a numpy dependency for fixtures.
    state = seed & 0xFFFFFFFF

    def _rand() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 0xFFFFFFFF

    hours = list(range(WINTER_HOURS))
    observed: list[float | None] = []
    predicted: list[float | None] = []
    blh_m: list[float | None] = []
    wind_spd: list[float | None] = []
    fire_count_upwind: list[int | None] = []
    in_diwali = []
    in_stubble = []
    in_stagnation = []

    diwali = CASE_STUDIES[0]
    stubble = CASE_STUDIES[1]
    stagnation = CASE_STUDIES[2]

    for h in hours:
        day = h // 24
        hour_of_day = h % 24

        # Baseline winter diurnal: higher overnight / early morning.
        diurnal = 40.0 if 10 <= hour_of_day <= 16 else 90.0
        seasonal = 80.0 + 0.15 * day  # gradual winter rise
        base = seasonal + diurnal + 15.0 * (_rand() - 0.5)

        # Case windows (synthetic elevations).
        if diwali.window_start <= h < diwali.window_end:
            base += 220.0 + 30.0 * (_rand())
        if stubble.window_start <= h < stubble.window_end:
            # Afternoon–evening transport bump
            if hour_of_day >= 14 or hour_of_day <= 2:
                base += 140.0 + 40.0 * _rand()
            else:
                base += 60.0
        if stagnation.window_start <= h < stagnation.window_end:
            base += 180.0 + 25.0 * _rand()
            if hour_of_day < 8 or hour_of_day > 20:
                base += 50.0

        obs_val: float | None = _clamp_aqi(base)
        # Predicted: 2-hour lag + bias, then occasional miss
        lag_src = observed[h - 2] if h >= 2 else obs_val
        if lag_src is None:
            pred_val: float | None = None
        else:
            pred_val = _clamp_aqi(float(lag_src) + 10.0 * (_rand() - 0.4))

        # Explicit gaps (station downtime / ingest holes); never filled.
        if include_gaps:
            # Recurring overnight maintenance hole every ~11 days, 4 hours.
            if day % 11 == 3 and 2 <= hour_of_day <= 5:
                obs_val = None
            # Predicted feed drops mid-stubble for 18 hours.
            if stubble.window_start + 48 <= h < stubble.window_start + 66:
                pred_val = None
            # Random 1% dropouts
            if _rand() < 0.01:
                obs_val = None
            if _rand() < 0.01:
                pred_val = None

        # Context features (synthetic).
        blh: float | None = 400.0 + 600.0 * (
            1.0 if 11 <= hour_of_day <= 16 else 0.25
        )
        wspd: float | None = 1.5 + 2.5 * _rand()
        fires: int | None = 0
        if stubble.window_start <= h < stubble.window_end:
            fires = int(20 + 80 * _rand())
            wspd = 3.0 + 4.0 * _rand()
        if stagnation.window_start <= h < stagnation.window_end:
            blh = 150.0 + 100.0 * _rand()
            wspd = 0.5 + 1.0 * _rand()
            fires = int(2 * _rand())
        if include_gaps and day % 11 == 3 and 2 <= hour_of_day <= 5:
            blh = None
            wspd = None
            fires = None

        observed.append(obs_val)
        predicted.append(pred_val)
        blh_m.append(blh)
        wind_spd.append(wspd)
        fire_count_upwind.append(fires)
        in_diwali.append(diwali.window_start <= h < diwali.window_end)
        in_stubble.append(stubble.window_start <= h < stubble.window_end)
        in_stagnation.append(stagnation.window_start <= h < stagnation.window_end)

    return {
        "meta": {
            "name": "synthetic_delhi_winter_2023_24",
            "description": (
                "Deterministic synthetic hourly fixture for offline episode "
                "evaluation. Not observational data."
            ),
            "season_label": "2023-10-01_to_2024-03-31",
            "timezone": "Asia/Kolkata",
            "n_hours": WINTER_HOURS,
            "seed": seed,
            "include_gaps": include_gaps,
            "disclaimer": (
                "Synthetic construct for method development only; do not treat "
                "as CPCB/OpenAQ measurements or as attribution ground truth."
            ),
        },
        "hours": hours,
        "observed_aqi": observed,
        "predicted_aqi": predicted,
        "blh_m": blh_m,
        "wind_speed_ms": wind_spd,
        "fire_count_upwind": fire_count_upwind,
        "flags": {
            "in_diwali_window": in_diwali,
            "in_stubble_window": in_stubble,
            "in_stagnation_window": in_stagnation,
        },
        "case_studies": [asdict(c) for c in CASE_STUDIES],
    }


def fixture_path() -> Path:
    """Path to the bundled JSON fixture (created on demand if absent)."""
    return Path(__file__).resolve().parent / "data" / "synthetic_winter_2023_24.json"


def ensure_bundled_fixture(*, force: bool = False) -> Path:
    """Write the synthetic winter JSON next to this package if needed."""
    path = fixture_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if force or not path.exists():
        payload = build_synthetic_winter_series()
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def load_synthetic_winter(*, path: Path | None = None) -> dict[str, Any]:
    """Load bundled fixture, generating it if the JSON file is missing."""
    target = path or ensure_bundled_fixture()
    if not target.exists():
        ensure_bundled_fixture(force=True)
        target = fixture_path()
    return json.loads(target.read_text(encoding="utf-8"))
