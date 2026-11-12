# GSTR-2B Reconciler

Matches a client's purchase register against their GSTR-2B (the government's auto-generated ITC statement), explains every mismatch, and drafts follow-up notes for vendors. Exact matching handles the clean cases; an XGBoost model handles typos, rounding and date shifts, and retrains from the CA's review decisions.

CSE 816 (Software Production Engineering) final project. Full design: [DESIGN.md](DESIGN.md).

## Layout

| Folder | What's in it |
|---|---|
| `matcher/` | GSTIN checks, normalisers, parsers, matching engine |
| `datagen/` | synthetic data generator (real client data is confidential) |
| `api/` | FastAPI service |
| `trainer/` | retraining from review decisions, quality gate, MLflow publishing |
| `config/` | tolerances, thresholds, model quality gate |
| `tests/` | unit tests and the golden set |
| `docs/` | research notes, runtime contract (ports, env vars, images) |
| `deploy/` | docker compose, ELK config and dashboards |
| `scripts/` | smoke test |

## Running the whole stack locally

```bash
cp deploy/.env.example deploy/.env      # put random values in it
docker compose -f deploy/docker-compose.yml up -d --build
```

| What | Where |
|---|---|
| App (login = `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `deploy/.env`) | http://localhost:8080 (`FRONTEND_PORT` changes it) |
| API | http://localhost:8000/api/v1, health at `/healthz`, `/readyz` |
| MLflow (model registry) | http://localhost:5000 |
| Vault (dev mode) | http://localhost:8200 |

Test files to upload: `python -m datagen --seed 1 --invoices 200 --out somedir --xlsx`, then upload
`gstr2b.json` and `books.xlsx` for period `2025-04`.

Useful extras:

```bash
# end-to-end check against a running stack
SMOKE_EMAIL=... SMOKE_PASSWORD=... python scripts/smoke_test.py --base-url http://127.0.0.1:8080
# retrain from review decisions now (nightly it skips under 50 new decisions)
docker compose -f deploy/docker-compose.yml run trainer --force
# logs + Kibana dashboards (needs ~3GB more RAM), Kibana on http://localhost:5601
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.elk.yml up -d
```

Load tests: `tests/load/README.md`. Kubernetes, Ansible and Jenkins: PR #39 until it merges.

## Running tests

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
ruff check .
pytest
```

## How we work

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: every change starts as an issue, goes on a branch, and lands through a PR.
