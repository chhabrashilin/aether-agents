# Science design: Delhi–NCT winter smog

## Thesis

Build an always-on multi-agent air-quality intelligence service for Delhi–NCT that answers: *Is this an acute winter episode, what evidence supports which source classes, and what GRAP-relevant advisory follows, with calibrated uncertainty?*

Focus season: **October–March** (post-monsoon through winter), when stagnant meteorology, local combustion, and regional agricultural burning interact under CAQM / GRAP staging.

## Differentiation

- Complementary to CTM + AOD assimilation DSS systems: this project does **not** replace chemical transport models.
- Distinct from PM₂.₅ washout / visualization-first tools: emphasis on episode science, source-class hypotheses, and transparent agent orchestration.

## Scientific claims (v1): aspirational vs demonstrated

**Demonstrated in-repo:**

1. Heterogeneous station streams (CPCB OGD snapshot + OpenAQ hourly history) can drive reproducible episode detection with explicit missing-data handling and typed value semantics.
2. A multi-agent pipeline can emit exportable evidence scorecards and fail-closed critic decisions offline on fixtures (transparency of *process*, not proven skill).

**Aspirational (need holdout winters + expert protocol; see methods.md):**

3. Source-class *hypotheses* (stubble/transport, local combustion, dust, industrial, mixed) can be usefully scored against historical winter case literature and CAQM/GRAP timelines.
4. CIRRUS GitOps is a viable host for continuous environmental decision APIs (not just static dashboards). Chart exists; production deploy pending onboarding.

Softmax outputs are heuristic class masses, **not** calibrated posteriors. GRAP fields are alignment bands only.

## Data sketch

| Source | Role |
|---|---|
| CPCB Real-time AQI (data.gov.in) | Primary nowcast; filter Delhi/NCR; careful sub-index vs µg/m³ fields |
| OpenAQ v3 | Hourly history for matched stations; gaps stay gaps |
| NASA FIRMS | Upwind fire counts / transport priors |
| Open-Meteo / ERA5-lite | Wind, BLH, humidity context |

## Agent outputs (summary)

| Agent | Output |
|---|---|
| Ingest | Station time series + QA flags |
| Context | Fire/met/calendar feature vector |
| Episode | Onset/peak/decay + severity |
| Attribution | Source-class posterior + cited evidence |
| Critic | Revised uncertainty / consistency checks |
| Advisory | GRAP-stage language + exposure guidance (never invent legal orders) |

## Evaluation

- **Detection metrics** (`aether_agents.eval.metrics`): sustained Very Poor / Severe windows; pairwise precision/recall/F1 only on jointly observed hours; coverage and gap diagnostics; no silent imputation.
- **Case-study rubrics** (`aether_agents.eval.rubric`): Diwali, post-monsoon stubble/transport, and local stagnation; literature-aligned expert review, not fabricated ground truth.
- **Offline fixture + notebook**: synthetic winter series and `notebooks/winter_season_evaluation.ipynb` for a reproducible workflow without live APIs.
- Methods write-up: [methods.md](methods.md). Holdout real winters remain a later validation step using the same rules.
