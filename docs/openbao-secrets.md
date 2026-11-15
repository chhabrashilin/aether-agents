# OpenBao / External Secrets on CIRRUS

Application and database credentials must live in OpenBao (`bao.k8s.ucar.edu`),
never in Git. This chart follows
[NCAR/cirrus-examples external-secret-helm](https://github.com/NCAR/cirrus-examples/tree/main/helm/external-secret-helm)
and [postgres-helm](https://github.com/NCAR/cirrus-examples/tree/main/helm/postgres-helm).

## Prerequisites

1. Namespace for the app (created during CIRRUS onboarding).
2. A `SecretStore` named `user-ro` that can read your OpenBao paths.
   Request from [cirrus-admin@ucar.edu](mailto:cirrus-admin@ucar.edu) if missing.
3. Secrets written under your OpenBao mount/path before enabling chart flags.

## Application API keys

Suggested OpenBao path (matches `externalSecrets.secretPath` in values):

```text
aether-agents/app
  ├── DATA_GOV_IN_API_KEY
  ├── OPENAQ_API_KEY
  ├── FIRMS_MAP_KEY
  └── LLM_API_KEY          # optional
```

Enable injection:

```yaml
externalSecrets:
  enabled: true
  secretPath: aether-agents/app
  targetSecretName: aether-agents-app-secrets
```

The chart creates an `ExternalSecret` and mounts those keys as env vars on the
**API** and **worker** Deployments. The dashboard does not receive them.

## Postgres (CloudNativePG) credentials

Suggested paths (matches `postgres.*.secretPath`):

```text
aether-agents/postgres/appuser
  ├── username   # must match postgres.app.owner (e.g. aether_agents_user)
  └── password

aether-agents/postgres/superuser   # only if postgres.superUser.enabled
  ├── username   # must be postgres
  └── password
```

Then:

```yaml
postgres:
  enabled: true
config:
  databaseUrl: "postgresql+psycopg://aether_agents_user@aether-agents-pg-rw:5432/aether_agents"
```

Password for `DATABASE_URL` can instead be composed at runtime from the CNPG
app-user secret once you wire a connection string helper; for v1, prefer storing
a full URL only in OpenBao if needed, or use the in-cluster RW service with
secrets managed by CNPG bootstrap.

**Alternative:** deploy postgres as a sibling Argo app from
`cirrus-examples/helm/postgres-helm` and keep `postgres.enabled: false` here,
setting only `config.databaseUrl`.

## Local development

Use `.env` from `.env.example`. Do not copy production OpenBao values into Git
or into committed `.env` files.

## Enabling order

1. Onboard the app with secrets/Postgres flags **off** (default).
2. Request SecretStore + store OpenBao keys.
3. Flip `externalSecrets.enabled` / `postgres.enabled`, commit to `main`.
4. Confirm pods receive env vars (Argo CD / pod describe); never print secret values in tickets.
