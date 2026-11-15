# Critical assessment: AetherAgents as NSF NCAR / CIRRUS research software

**Date:** 2026-11-15  
**Scope:** Code, Helm, tests, notebooks, and docs as they exist in-tree.  
**Tone:** Review-board blunt. No marketing.

---

## 1. What is real vs stub / theater

### Real (ships and is tested)

| Piece | Reality |
|---|---|
| CPCB OGD client + Delhi/NCR filter | Real parsers, explicit `value_semantics="sub_index"`, QA flags, fixtures |
| OpenAQ v3 client + station matching | Real parsers; gaps not filled; fixture tests |
| Postgres/SQLite ingest persistence | ORM with `value_semantics`, raw payload provenance |
| EpisodeAgent (threshold + duration) | Deterministic CPCB category rules; unit tests |
| ContextAgent (FIRMS / meteo / calendar) | Injectable clients; deterministic calendar hooks |
| Attribution → Critic → Advisory | Rule/score path works offline without LLM |
| FastAPI read + demo attribution routes | Importable; demo chain runs |
| Helm chart skeleton | Deployments, probes, ingress, CNPG + ExternalSecrets toggles |
| Eval metrics + case rubrics | Honest about no fake ground truth; synthetic winter fixture |

### Theater / incomplete (looks finished, is not)

| Piece | Reality |
|---|---|
| Full pipeline on worker | Worker runs **ingest only**. Episode → Context → Attribution → Advisory is **not** scheduled. |
| End-to-end offline pipeline API | No `/v1/pipeline/run` that executes ingest→…→advisory with provenance. Demo is hand-built Episode/Context JSON. |
| Observation agent types vs DB | `agents.base.types.Observation` lacks `value_semantics`; `resolved_aqi()` can derive AQI from `value` without knowing if that value is a sub-index or µg/m³. |
| Dual episode schemas | `EpisodeObject` (detection) and `EpisodeOutput` (attribution) with adapters: friction and silent field remapping (`data_completeness` → `station_coverage`). |
| Attribution “evidence” | Features are listed and weighted for display, but class scores are **hard-coded if-blocks**, not transparent feature→contribution scorecards exportable as reproducible JSON. |
| Critic “calibrated uncertainty” | Softens posteriors; still always emits a `dominant_class`. Does **not** fail closed under sparse data. |
| LLM path | Settings flag exists; no live adapter. Notes claim enrichment that does not run. |
| Dashboard | Usable demo UI, not a research console (no evidence scorecard table, weak uncertainty surfacing, no run provenance). |
| CIRRUS “ready” | Image repos are `ghcr.io/PLACEHOLDER/...`; postgres + secrets default **off**; no retention/SLO docs. |
| Scientific claim #2–3 in science-design | Multi-agent “improves transparency” and “can be scored against literature” are **aspirational**; only synthetic/rubric scaffolding exists. |

**Verdict:** Stronger than a pure scaffold (ingest + classical episode + rule attribution are real), but still a **research prototype** that over-signals operational completeness via Helm + agent naming.

---

## 2. Scientific credibility gaps (Delhi winter / GRAP / attribution)

1. **Units / semantics risk.** CPCB OGD `pollutant_avg` is a **sub-index**, OpenAQ is **concentration**. Agent-layer `Observation.resolved_aqi()` will call `pm25_to_cpcb_aqi(value)` whenever `aqi` is missing: dangerous if a CPCB sub-index is ever passed as `value` without semantics.
2. **Episode detection prefers AQI integers**, not concentrations. Winter science often wants PM₂.₅ µg/m³ with documented mapping; mapping notes exist in ingest docs but are not enforced at the agent boundary.
3. **Attribution is a heuristic prior**, not receptor modeling, chemical fingerprints, or tagged CTM. Calling outputs “posteriors” without a generative model is review-bait unless methods state “softmax of heuristic scores.”
4. **No holdout winter validation** against CPCB/OpenAQ archives or CAQM timeline concurrence; only synthetic fixture + rubric templates.
5. **GRAP alignment ≠ official staging.** CAQM activates stages with institutional process; AQI-band mapping is an **alignment band**, not an order. Docs partially say this; UI/API must shout it.
6. **Source classes lack negative controls** (e.g. monsoon dust vs winter stagnation) and no pollutant ratios (NO₂/PM, CO) that NCAR/CPCB analysts expect.
7. **FIRMS upwind counts** are a weak proxy for stubble contribution (detection efficiency, FRP, plume chemistry ignored).
8. **Uncertainty is ad hoc** (coverage penalties, shrink-to-uniform), not calibrated probabilities.

---

## 3. Operational gaps for CIRRUS / NCAR

| Area | Gap |
|---|---|
| Observability | No Prometheus `/metrics`, no structured `run_id` / `episode_id` / `station_id` logging end-to-end |
| Secrets | OpenBao pattern documented; chart defaults leave ExternalSecrets off (first deploy has no keys) |
| Data retention | Raw payloads stored unbounded; no retention policy, no archive tier |
| Failure modes | Worker logs and sleeps; no dead-letter, no partial-run markers, no backfill CLI |
| SLOs | None defined (ingest freshness, API latency, episode lag) |
| Image registry | Placeholder GHCR org; onboarding packet incomplete for cirrus-admin |
| Ingress path map | `/api` → API but FastAPI routes are not under `/api` prefix by default (first-deploy footgun) |
| AuthN/Z | Public research API with CORS `*`; fine for open science, wrong if treated as operational DSS |

---

## 4. Differentiation vs SkyWash and AIRWISE: honesty check

| System | What it actually is | Honest AetherAgents niche |
|---|---|---|
| **AIRWISE** (NCAR) | WRF-Chem + AOD assimilation + decision-support science | We do **not** compete on CTM skill. We offer station-stream episode objects + transparent heuristics for Delhi winter. |
| **SkyWash** | PM₂.₅ / washout-oriented visualization | We are not a visualization-first product. Episode + source-hypothesis + GRAP-aligned language is the claimed difference, and only valuable if evidence objects are reproducible. |

**Honest value proposition:** A CIRRUS-hosted, GitOps-deployable **episode intelligence API** with explicit missing-data handling and exportable evidence, complementary to CTMs.  
**Dishonest pitch to avoid:** “multi-agent attribution that knows winter smog sources” or “GRAP advisor.”

---

## 5. Top 10 issues by impact

1. **Silent unit/semantics mixing** at agent Observation boundary (scientific integrity).
2. **No full offline pipeline** (ingest→episode→context→attribution→advisory) for reproducible demos and CI.
3. **Critic never refuses** a dominant source under sparse data (overconfidence theater).
4. **Attribution scores not exportable as feature→contribution scorecards** (non-reproducible “evidence”).
5. **Worker does not run the science chain** (ops theater).
6. **Dual schemas / adapters** hide field meaning (`completeness` vs `coverage`).
7. **Eval stops at synthetic + rubric templates**; no labeled holdout winter protocol documented as required for a paper.
8. **Helm placeholders + ingress/API path mismatch** block a credible first CIRRUS deploy.
9. **Dashboard under-delivers** for research review (no scorecard / uncertainty / provenance).
10. **Science-design claims ahead of evidence** (transparency/literature scoring stated as if demonstrated).

---

## 6. What NCAR staff would reject in a review

- Calling heuristic softmax outputs **calibrated posteriors** without uncertainty calibration study.
- Implying **GRAP stage issuance** or regulatory authority.
- Mixing CPCB sub-index and µg/m³ in figures or episode peaks without unit labels.
- Claiming complementarity to AIRWISE while presenting attribution as competitive skill.
- CIRRUS deploy docs with `PLACEHOLDER` registries and secrets disabled as “production-ready.”
- Accuracy / F1 numbers on **synthetic** winters presented as scientific performance.
- LLM “reasoning” flags that do not invoke a model (or invoke one without audit trail).
- Dashboard demo sold as operational DSS.

---

## Remediation direction (this pass)

Close integrity gaps first: typed semantics + fail-closed critic + scorecards + full offline pipeline + honest README/methods + research dashboard + metrics/logging + Helm NOTES. Leave CTM-grade attribution, multi-winter holdout labels, and formal SLOs as **explicit v1 out-of-scope**.
