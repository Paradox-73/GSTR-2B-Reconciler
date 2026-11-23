# GSTR-2B Reconciler: Project Proposal

| | |
|---|---|
| Course | CSE 816 Software Production Engineering, Capstone Project, 2026-27 |
| Team | Kanav Bhardwaj (Paradox-73), Bhavya Jain (Bhavzzzzzz) |
| Track | Machine Learning / MLOps, finance domain |
| Repository | https://github.com/Paradox-73/GSTR-2B-Reconciler |

## Application

Every month, a GST-registered business must match its purchase register against GSTR-2B, the government's statement of claimable input tax credit, before filing its return. Small CA firms do this by hand in Excel. Our web app takes a client's GSTR-2B JSON and purchase register (xlsx/csv), matches the invoices, explains every mismatch with reason codes, and drafts a follow-up note per supplier. Exact matching handles clean pairs; an XGBoost model scores the rest (typos, rounding, date shifts, a wrong GSTIN character) and is retrained from the CA's accept/reject decisions. Synthetic data with known answers replaces confidential client data.

## Architecture

React frontend (Nginx) and FastAPI api behind an Ingress; a Redis queue feeds matcher workers that scale with an HPA; PostgreSQL stores clients, invoices, runs and decisions; an MLflow registry holds model versions; a trainer CronJob retrains and promotes models. Everything runs on minikube on a laptop (4 CPU, 6 GB).

## Pipeline and tools

| Stage | Tool | What it does |
|---|---|---|
| Source control | Git + GitHub | Issues, branches, pull requests, protected `main` |
| CI/CD | Jenkins (webhook trigger) | Tests, golden-set test, model quality gate, build, scan, push, deploy, smoke test, automatic rollback |
| Build | Docker | One image per service, tagged with the git sha, pushed to Docker Hub |
| Configuration | Ansible roles | Machine setup (Docker, minikube) and every deploy |
| Orchestration | Kubernetes (minikube) | Rolling updates with zero downtime, HPA for api and workers |
| Observability | Prometheus + Grafana, ELK | Metrics dashboards in Grafana; JSON logs per request and per run in Kibana |

## Cutting-edge extensions

- **MLOps:** MLflow registry, a quality gate (precision/recall thresholds) that blocks a worse model in CI and at retraining, and workers that swap in a promoted model without a restart.
- **DevSecOps:** HashiCorp Vault for secrets (Kubernetes auth, Agent Injector) and Transit encryption of uploaded files; Trivy image scanning that fails the build on critical CVEs.

## Demo plan

A pushed change reaches the cluster with zero failed requests; a commit that breaks matching is blocked by the golden-set test; workers scale under a load spike; a retrained model goes live without a restart; metrics in Grafana, logs in Kibana.
