# CIRRUS onboarding packet

Paste-ready fields for the [CIRRUS request form](http://cirrus.k8s.ucar.edu/request-app).
Update placeholders before submission. Questions: [cirrus-admin@ucar.edu](mailto:cirrus-admin@ucar.edu).

## Request form fields

| Field | Value |
|---|---|
| Application name | AetherAgents |
| Short description | Multi-agent Delhi–NCT winter smog episode intelligence (ingest, detect, attribute, advise) |
| Desired FQDN / Application URL | `https://aether-agents.k8s.ucar.edu` |
| Public / internal | Public (Traefik external ingress, class `traefik-external`) |
| Git repository URL | `https://github.com/chhabrashilin/aether-agents` |
| Default branch / GitHub branch | `main` |
| Helm chart path / folder | `helm/aether-agents` |
| Chart name | `aether-agents` |
| Image registry (initial) | GHCR: `ghcr.io/chhabrashilin/aether-agents-{api,worker,dashboard}` |
| Harbor project (optional later) | `hub.k8s.ucar.edu/<project>/...` (request via Jira when ready; not required for first onboard) |
| Ingress class | `traefik-external` |
| Persistence | CloudNativePG for observations, episodes, agent runs (`postgres.enabled` in chart; off until OpenBao DB secrets exist) |
| Secrets | External Secrets / OpenBao (`bao.k8s.ucar.edu`) for `DATA_GOV_IN_API_KEY`, `OPENAQ_API_KEY`, `FIRMS_MAP_KEY`, optional `LLM_API_KEY`; see [openbao-secrets.md](openbao-secrets.md) |
| Primary contact name | PLACEHOLDER |
| Primary contact email | PLACEHOLDER@ucar.edu |
| Secondary contact | PLACEHOLDER |
| NSF / project code | PLACEHOLDER |
| Expected traffic | Low–moderate research API + dashboard |
| GPU required | No (optional Dask later for spatial grids) |
| Notes | Complementary to CTM/DSS workflows; continuous environmental decision API. Images start on GHCR; Harbor optional. |

## Sample email / Jira body

```text
Hello CIRRUS team,

Please onboard AetherAgents for GitOps deploy on CIRRUS.

- GitHub repository: https://github.com/chhabrashilin/aether-agents
- Branch: main
- Helm chart folder: helm/aether-agents
- Desired URL: https://aether-agents.k8s.ucar.edu (public / traefik-external)
- Images: GHCR (ghcr.io/chhabrashilin/aether-agents-*) for initial deploy; Harbor later if useful
- Persistence: CloudNativePG planned after OpenBao SecretStore + DB credentials
- Secrets: External Secrets from bao.k8s.ucar.edu (app API keys)

Primary contact: PLACEHOLDER <PLACEHOLDER@ucar.edu>

Thank you
```

Submit via:

1. Web form: <http://cirrus.k8s.ucar.edu/request-app>
2. Or email: [cirrus-admin@ucar.edu](mailto:cirrus-admin@ucar.edu)

## Access notes (optional; not required to deploy)

Argo CD deploys from Git without personal cluster access. Request these only if needed:

| Access | Why | How |
|---|---|---|
| **Argo CD (read-only)** | Watch syncs, health, logs | Jira/ticket with project name + UCAR emails |
| **Harbor** | On-cluster private images (`hub.k8s.ucar.edu`) | Optional; GHCR works first. Jira for project create / push |
| **OpenBao / SecretStore** | Inject API keys and DB passwords | Ask `cirrus-admin@ucar.edu` for `user-ro` SecretStore in the app namespace |
| **kubectl / Grafana** | Debug metrics and resources | Separate ticket; scoped to your namespace |

Docs: [CIRRUS getting started](http://cirrus.k8s.ucar.edu/getting-started), [Services](http://cirrus.k8s.ucar.edu/services), [cirrus-examples](https://github.com/NCAR/cirrus-examples).

## Workloads in this chart

- **API:** FastAPI gateway (`Deployment` + `Service`, Ingress path `/api`)
- **Worker:** scheduled ingest + agent pipeline (`Deployment`)
- **Dashboard:** research UI (`Deployment` + `Service`, Ingress path `/`)
- **Postgres:** CloudNativePG (`postgres.enabled`; off until secrets exist)
- **ExternalSecret:** app keys (`externalSecrets.enabled`; off until OpenBao path exists)

## CI → GitOps image updates

1. Push to `main` or tag `v*` → workflow **`build-images`** builds/pushes GHCR packages.
2. Set `api.image.tag` / `worker.image.tag` / `dashboard.image.tag` in `helm/aether-agents/values.yaml` to the published tag.
3. Confirm GHCR image names match `ghcr.io/chhabrashilin/aether-agents-*` (or swap to Harbor).
4. Commit on `main`; Argo CD syncs the new tags.

## Checklist before filing

- [ ] Repo public or CIRRUS-accessible; branch `main` exists
- [ ] Chart lint passes (`helm lint helm/aether-agents`)
- [ ] Image names in `values.yaml` match GHCR packages (or Harbor after swap)
- [ ] Contact and funding fields filled
- [ ] Secrets plan confirmed (no keys in Git); see [openbao-secrets.md](openbao-secrets.md)
- [ ] FQDN `aether-agents.k8s.ucar.edu` confirmed unique
