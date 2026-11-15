# AetherAgents

Multi-agent **episode intelligence** for Delhi–NCT winter smog (October–March).

**Research question:** Is this an acute winter episode, what *evidence* supports which source-class hypotheses, and what GRAP-relevant *alignment-band* advisory follows, with explicit uncertainty?

This is **not** a chemical transport model, not a regulatory DSS, and not a CAQM order generator. It is complementary to CTM / assimilation systems (e.g. NCAR AIRWISE): station-stream ingest, classical episode detection, transparent heuristic attribution, and a CIRRUS-deployable API.

## Problem

Delhi–NCR winter air quality combines stagnant meteorology, local combustion, and regional agricultural burning under CAQM / GRAP staging. Operators and researchers need reproducible episode objects and cited evidence, not a black-box “source answer.”

## Methods (v1)

| Stage | Method |
|---|---|
| Ingest | CPCB Real-time AQI (data.gov.in) + OpenAQ v3; gaps stay gaps; CPCB fields are **sub-indices**, OpenAQ are **concentrations** |
| Episode | Sustained CPCB AQI ≥ 301 (Very Poor) for ≥ 6 h; prefer PM₂.₅ µg/m³→AQI via published CPCB breakpoints when available |
| Context | FIRMS upwind fire counts, Open-Meteo wind/BLH/RH, Delhi calendar hooks |
| Attribution | Softmax of **heuristic** rule scores; exportable feature→weight→contribution scorecard |
| Critic | Consistency checks; **fail-closed** (refuse dominant source) under sparse data |
| Advisory | AQI→GRAP *alignment bands* only; non-authoritative; official portal [caqm.nic.in](https://caqm.nic.in/) |

Eval uses synthetic winters + literature-aligned rubrics. **No fabricated ground-truth accuracy claims.** See [docs/methods.md](docs/methods.md).

## Architecture

```
CPCB / OpenAQ / FIRMS / Open-Meteo
        ↓
   Ingest (+ QA, value_semantics)
        ↓
 EpisodeAgent → ContextAgent → Attribution → Critic → Advisory
        ↓
   FastAPI + research dashboard  (Helm on CIRRUS)
```

## How to run (local)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
uvicorn apps.api.main:app --reload --app-dir .
```

| Check | URL |
|---|---|
| Health | `GET http://127.0.0.1:8000/health` |
| OpenAPI | `http://127.0.0.1:8000/docs` |
| Offline full pipeline | `GET http://127.0.0.1:8000/v1/pipeline/run?mode=fixture` |
| Metrics | `GET http://127.0.0.1:8000/metrics` |

Worker (ingest + fixture pipeline by default):

```powershell
python -m apps.worker.main
```

Dashboard: open `apps/dashboard/index.html` or serve the dashboard container; point API base at the gateway (use `/api` behind CIRRUS ingress).

```powershell
python -m pytest -q
```

## CIRRUS deploy

- Target FQDN: `aether-agents.k8s.ucar.edu`
- Chart: `helm/aether-agents`
- Onboarding packet: [docs/cirrus-onboarding.md](docs/cirrus-onboarding.md)
- Secrets: External Secrets / OpenBao; never in Git ([docs/openbao-secrets.md](docs/openbao-secrets.md))
- Images: GHCR during onboarding; Harbor swap documented in chart values

Ingress serves the dashboard at `/` and the API under `/api` (gateway strips the `/api` prefix).

## Limitations (honest)

- Attribution scores are **heuristics**, not receptor modeling or tagged CTM output.
- Critic uncertainty is **not** probability calibration.
- Live CPCB snapshots alone may not meet the 6 h episode rule without OpenAQ hours.
- No multi-winter holdout labels or expert-review campaign yet (required for a paper; see methods).
- Helm image repositories default to a placeholder GHCR org until onboarding fills them.

Critical review of what is real vs theater: [docs/CRITICAL_ASSESSMENT.md](docs/CRITICAL_ASSESSMENT.md).  
NCAR collaboration framing: [docs/ncar-value-proposition.md](docs/ncar-value-proposition.md).

## Citation

MIT; see [LICENSE](LICENSE). Cite via [CITATION.cff](CITATION.cff).
