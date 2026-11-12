# GSTR-2B Reconciler

Matches a client's purchase register against their GSTR-2B (the government's auto-generated ITC statement), explains every mismatch, and drafts follow-up notes for vendors. Exact matching handles the clean cases; an XGBoost model handles typos, rounding and date shifts, and retrains from the CA's review decisions.

CSE 816 (Software Production Engineering) final project. Full design: [DESIGN.md](DESIGN.md).

## Layout

| Folder | What's in it |
|---|---|
| `matcher/` | GSTIN checks, normalisers, parsers, matching engine |
| `datagen/` | synthetic data generator (real client data is confidential) |
| `api/` | FastAPI service |
| `trainer/` | retraining + evaluation |
| `config/` | tolerances, thresholds, model quality gate |
| `tests/` | unit tests and the golden set |
| `docs/` | research notes and decisions |

## Running tests

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
ruff check .
pytest
```

## How we work

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: every change starts as an issue, goes on a branch, and lands through a PR.
