# NCAR / CIRRUS value proposition

## Why CIRRUS

AetherAgents is designed as a **continuous environmental decision API**, not a one-off notebook or static dashboard:

- Containers + Helm chart patterned on NCAR CIRRUS examples (ingress, CloudNativePG toggle, External Secrets / OpenBao).
- Target public Traefik host: `aether-agents.k8s.ucar.edu`.
- Reproducible offline pipeline (`/v1/pipeline/run?mode=fixture`) for CI and demo without secrets; live mode when keys exist.
- Prometheus text `/metrics` for platform scraping; structured logs with `run_id` / `episode_id` / `station_id`.

CIRRUS is the right host if the goal is **always-on episode intelligence** that other NCAR tools and external collaborators can call, not a laptop demo.

## Complementarity (honest)

| System | Role | AetherAgents relation |
|---|---|---|
| **AIRWISE** | WRF-Chem + AOD assimilation + DSS science | Complementary. We do not claim CTM skill. We expose station-stream episodes, evidence scorecards, and GRAP *alignment bands* that a DSS might consume or critique. |
| **SkyWash** | PM₂.₅ / washout-oriented visualization | Different job. Visualization-first washout insight ≠ transparent episode + source-hypothesis API. Overlap exists only at “air quality UX”; methods differ. |

**Do not pitch** AetherAgents as replacing AIRWISE attribution or as an official GRAP engine.

## What NCAR staff get in v1

1. Reproducible Delhi–NCT ingest with explicit CPCB sub-index vs concentration semantics.
2. Classical episode detection with documented CPCB breakpoint mapping and calibration notes.
3. Exportable attribution scorecards (feature → weight → contribution) and fail-closed critic.
4. Helm/GitOps path ready for a real onboarding request to cirrus-admin.
5. Honest limitations and a critical self-assessment (`docs/CRITICAL_ASSESSMENT.md`).

## Proposed collaboration path

1. **cirrus-admin@ucar.edu:** submit [CIRRUS app request](http://cirrus.k8s.ucar.edu/request-app) using `docs/cirrus-onboarding.md` (repo, chart path, FQDN, contacts). Fill GHCR/Harbor image names before production sync.
2. **Science touchpoint:** share episode objects + scorecard JSON with AIRWISE / air-quality researchers for qualitative review (not accuracy bake-offs until holdout winters exist).
3. **SIParCS / poster:** methods + offline pipeline + one literature-aligned case window; emphasize missing-data handling and non-authoritative advisory language.
4. **Next research step:** expert-review protocol + labeled holdout winters (see `docs/methods.md`) before any journal claim on attribution skill.

## Contact packet checklist

- [ ] GitHub repo URL + branch `main`
- [ ] Chart path `helm/aether-agents`
- [ ] Desired FQDN `aether-agents.k8s.ucar.edu`
- [ ] OpenBao paths for API keys (CPCB, OpenAQ, FIRMS)
- [ ] Image registry decision (GHCR → Harbor)
- [ ] Named NCAR sponsor / collaborator for science review
