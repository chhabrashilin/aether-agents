# Container images

One Containerfile-style Dockerfile per workload. GitHub Actions builds and pushes
them to GHCR via `.github/workflows/build-images.yml`.

| File | Image name | Port |
|---|---|---|
| `Dockerfile.api` | `aether-agents-api` | 8000 |
| `Dockerfile.worker` | `aether-agents-worker` | n/a |
| `Dockerfile.dashboard` | `aether-agents-dashboard` | 8080 |

## Local builds

```bash
docker build -f docker/Dockerfile.api -t aether-agents-api:local .
docker build -f docker/Dockerfile.worker -t aether-agents-worker:local .
docker build -f docker/Dockerfile.dashboard -t aether-agents-dashboard:local .
```

## Registries

1. **GHCR (default for onboarding):** `ghcr.io/<owner>/aether-agents-<svc>:<tag>`
2. **Harbor (optional, on-cluster):** `hub.k8s.ucar.edu/<project>/aether-agents-<svc>:<tag>`

After Harbor is available, retag/push or rebuild, then update
`helm/aether-agents/values.yaml` image repositories and commit so Argo CD syncs.
