# Runtime contract

What every deploy target (compose, K8s, Ansible, Jenkins) can rely on. Change it here first, then
in the code and manifests, in the same PR.

## Images

All images run as non-root uid `10001`. Tags: `:<git-sha>` and `:latest`. Docker Hub repo names:
`<dockerhub-user>/gstr2b-<name>`.

| Image | Built from | Command | Port | Probes |
|---|---|---|---|---|
| `gstr2b-api` | `Dockerfile` target `api` | `uvicorn api.main:app --host 0.0.0.0 --port 8000` | 8000 | liveness `GET /healthz` (no deps), readiness `GET /readyz` (checks DB + Redis) |
| `gstr2b-worker` | `Dockerfile` target `worker` | `rq worker --url $REDIS_URL reconcile` | none | liveness: process alive |
| `gstr2b-frontend` | `frontend/Dockerfile` | nginx | 8080 | `GET /` |
| `gstr2b-trainer` | `Dockerfile` target `trainer` | `python -m trainer` (week 4) | none | CronJob |

Database migrations: the `gstr2b-api` image with command `alembic upgrade head`. Runs as a K8s Job
before each api rollout, and as a one-shot service in compose.

## Environment

| Var | Used by | Example | Secret? |
|---|---|---|---|
| `DATABASE_URL` | api, worker, migrations, trainer | `postgresql+psycopg://gstr2b:<pw>@postgres:5432/gstr2b` | yes |
| `REDIS_URL` | api, worker | `redis://redis:6379/0` | no |
| `JWT_SECRET` | api | 32+ random chars | yes |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | api (creates the first user at startup if missing) | | password yes |
| `UPLOAD_DIR` | api | `/data/uploads` (volume, writable by uid 10001) | no |
| `LOG_LEVEL` | all | `INFO` | no |
| `MLFLOW_TRACKING_URI` | worker, trainer (week 4) | `http://mlflow:5000` | no |
| `VAULT_ADDR` | api (Transit encryption, week 3) | `http://vault.vault.svc:8200` (Vault lives in its own `vault` namespace) | no |

Any secret var can instead be given as `<VAR>_FILE=/path/to/file` and the app reads the file. That is
how Vault Agent Injector hands secrets over (`/vault/secrets/<name>`), so manifests never hold the
value itself.

## Logs

One JSON object per line on stdout. Fields: `ts`, `level`, `service`, `event`, `request_id` (api
requests), `run_id` (reconciliation runs), plus event-specific fields such as `duration_ms`, `counts`,
`status_code`, `path`. Never amounts, invoice numbers or supplier names (DESIGN.md 12).

## HTTP

API under `/api/v1`. The frontend calls relative `/api/v1/...`, so whatever sits in front (nginx in
compose, Ingress in K8s) must route `/api` to the api service and `/` to the frontend.
