# aether-agents Helm chart

CIRRUS-ready umbrella chart for the AetherAgents API, worker, and dashboard.
Patterns follow [NCAR/cirrus-examples](https://github.com/NCAR/cirrus-examples)
(`web-app-helm`, `postgres-helm`, `external-secret-helm`).

## Workloads

| Component | Kind | Notes |
|---|---|---|
| API | Deployment + Service | FastAPI on port 8000; `/api` via Ingress |
| Worker | Deployment | Scheduled ingest / agent runs; no Ingress |
| Dashboard | Deployment + Service | Static UI on port 8080; `/` via Ingress |
| Postgres | CloudNativePG Cluster (optional) | Off by default; OpenBao credentials required |
| App secrets | ExternalSecret (optional) | Off by default; OpenBao path `aether-agents/app` |

## Required values for CIRRUS onboarding

- `fqdn`: `aether-agents.k8s.ucar.edu`
- `ingress.className`: `traefik-external`
- Image repositories under `api` / `worker` / `dashboard` (GHCR first; Harbor later)

## Local lint / dry-run

```bash
helm lint helm/aether-agents
helm template aether-agents helm/aether-agents
```

## Enabling Postgres and secrets

1. Store credentials in OpenBao (`bao.k8s.ucar.edu`); see `docs/openbao-secrets.md`.
2. Ask `cirrus-admin@ucar.edu` for a `SecretStore` named `user-ro` in your namespace.
3. Set `externalSecrets.enabled: true` and/or `postgres.enabled: true`.
4. Point `config.databaseUrl` at the CNPG RW service (e.g. `aether-agents-pg-rw`).

Alternatively deploy [postgres-helm](https://github.com/NCAR/cirrus-examples/tree/main/helm/postgres-helm)
as a sibling Argo application and only wire `config.databaseUrl` here.

## Harbor image swap

Replace `ghcr.io/PLACEHOLDER/...` with `hub.k8s.ucar.edu/<project>/...` in `values.yaml`
once a Harbor project exists. Keep tags aligned with `.github/workflows/build-images.yml` output.
