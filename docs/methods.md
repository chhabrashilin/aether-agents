# Methods note: winter episode evaluation

Short methods summary for poster and paper drafts. Focus season: Delhi–NCT, October–March.

## Scope

AetherAgents evaluates **episode detection** and **case-study attribution review** for winter smog intelligence. Detection uses classical threshold-and-duration rules on hourly AQI. Attribution quality is scored with structured rubrics aligned to published festival, residue-burning, and stagnation narratives, not with fabricated station-level source labels.

## Observation semantics

- CPCB OGD `pollutant_*` fields are **AQI sub-indices** (0–500), not µg/m³.
- OpenAQ values are **concentrations**; PM₂.₅ µg/m³ may be mapped to CPCB sub-index via published National AQI breakpoints.
- EpisodeAgent prefers concentration→AQI when both are present; unknown semantics refuse silent conversion.
- Mapping is the published breakpoint table, **not** a Delhi co-location calibration.

## Episode detection

1. Map hourly AQI to CPCB categories; treat **Very Poor** (AQI ≥ 301) and **Severe** (AQI ≥ 401) as episode-eligible hours.
2. Require a minimum sustained duration (default **6 hours**) of consecutive hours at or above threshold (short missing gaps may bridge; long gaps end the run).
3. Gaps are never imputed for detection metrics; coverage is reported.

## Attribution & critic

- Class scores are **heuristic rule increments** recorded in an exportable scorecard (feature → weight → contribution). Softmax masses are **not** calibrated posteriors.
- Critic **fails closed** under sparse evidence: refuses `dominant_source`, shrinks toward uniform, raises uncertainty.

## Advisory

GRAP stage fields are **alignment bands** from AQI categories only. Official activation is CAQM / competent authorities only: https://caqm.nic.in/

## Pairwise metrics (explicit missing data)

Given a reference series \(y_t\) and a predicted series \(\hat{y}_t\):

- An hour enters the confusion matrix only if **both** \(y_t\) and \(\hat{y}_t\) are observed.
- Report coverage \(n_{\mathrm{scored}} / n\), counts of missing observations and missing predictions, and gap-run statistics.
- From scored hours, compute precision, recall, and F1 for episode-hour membership.
- When both series yield at least one detected episode, also report onset error, peak-timing error, and peak-AQI error (first episode vs first episode).

Silent gap-filling is out of scope; coverage and missingness are first-class outputs.

## Case-study rubrics (no fake ground truth)

Three literature-aligned windows are used for structured review:

| Case | Emphasis |
|---|---|
| Diwali festival combustion | Short multi-day local combustion / mixed priors |
| Post-monsoon stubble / transport | Upwind fire and wind consistency; mixture allowed |
| Local winter stagnation | Low BLH / weak winds; guard against fire over-attribution |

Shared criteria: temporal alignment, evidence citation, uncertainty language, GRAP-relevant framing (without inventing legal orders). Rubric totals are expert-review scores, **not** measurement ground truth or certified source apportionment.

## Offline reproducibility

A deterministic **synthetic** winter fixture (`synthetic_winter_2023_24`) and a multi-hour pipeline series (`pipeline_episode_series`) exercise gaps, elevations, and the full agent chain. Fixtures are method-development constructs and must not be cited as CPCB/OpenAQ observations.

```powershell
pip install -e ".[dev]"
pytest tests/ -q
jupyter notebook notebooks/winter_season_evaluation.ipynb
```

No external API keys are required for the offline workflow. Full chain:

```powershell
# or GET /v1/pipeline/run?mode=fixture
python -c "from aether_agents.pipeline import run_full_pipeline; print(run_full_pipeline().model_dump())"
```

## What a real paper would still need

v1 deliberately stops short of journal claims. A credible paper would additionally require:

1. **Labeled holdout winters:** at least two independent Oct–Mar seasons of CPCB/OpenAQ archives with documented QA, held out from any rule tuning.
2. **Expert review protocol:** ≥3 domain reviewers scoring rubrics blind to model confidence; inter-rater reliability reported; adjudication rules fixed a priori.
3. **Negative controls:** monsoon / clean periods where the system must not invent severe episodes or dominant sources.
4. **Calibration study:** if probabilities are reported, reliability diagrams / Brier scores against expert consensus (still not physical truth).
5. **Comparison baselines:** simple climatology and single-feature heuristics; optionally AIRWISE or published receptor studies as *context*, not as stolen ground truth.
6. **Uncertainty communication audit:** check that fail-closed and disclaimer language survive UI/API packaging.

Until those exist, report **coverage, rubric totals, and qualitative case narratives only**. Never report “X% attribution accuracy.”

## Relation to operational agents

Numerical detection stays classical. Agent reasoning (attribution, critic, advisory) is evaluated via rubrics and evidence-object inspection. Holdout real winters remain a later validation step using the same missing-data rules.
