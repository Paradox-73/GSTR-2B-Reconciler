# Individual Contribution Statement

CSE 816 Software Production Engineering, Capstone Project, 2026-27
Project: GSTR-2B Reconciler, https://github.com/Paradox-73/GSTR-2B-Reconciler

Each line names work the member did, with the issues or pull requests that show it. Commit counts are from `git shortlog -sn main`, taken on 23 November 2026 and re-checked before submission.

## Kanav Bhardwaj (GitHub: Paradox-73)

Commits on `main`: 66 (two Git identities, `Kanav Bhardwaj` and `Paradox_73`)

| Area | Work | Evidence |
|---|---|---|
| Design | System design document, proposal, issue board and work split | `DESIGN.md`, #1 |
| Code | Synthetic data generator and golden set; parsers, normalisers, exact and ML matcher; XGBoost model, trainer, MLflow gate and hot-swap; FastAPI service; React frontend | #2-#13, #22, #23, #37, #45, #54 |
| DevOps | GitHub Actions CI; first drafts of the Jenkinsfile, K8s manifests, Ansible roles, Vault and ELK, each proven on a local k3s cluster before handover; Prometheus and Grafana in the cluster; CycloneDX SBOM per image; Jenkins reading the Docker Hub token from Vault | #9, #39, #81, #82, #83 |
| Report | Report, proposal, requirement map, review of every pull request | #65, #69 |

## Bhavya Jain (GitHub: Bhavzzzzzz)

Commits on `main`: 11 (two Git identities, both his)

| Area | Work | Evidence |
|---|---|---|
| Code | Review of the whole application, seven defects found and filed, then fixed with tests: blank spreadsheet cells, over-long passwords, export sanitising, cess in vendor notes, trainer timezone; Prometheus metrics on the api and worker; warning for the GSTR-2B sections v1 does not reconcile | #70-#75, #76-#80, #84, #85 |
| DevOps | Minikube bring-up and the fresh-cluster deploy fix; Jenkins with Docker Hub on the real cluster; ELK and Vault in-cluster; zero-downtime and HPA load tests; rollback skip for same-sha rebuilds; `site.yml` on a fresh machine; GitHub webhook trigger | #39, #18, #19, #14 |
| Report | Challenges section, from his own cluster runs, and the screenshots | #90 |

## Signatures

We confirm that the statement above is accurate.

| Name | Signature | Date |
|---|---|---|
| Kanav Bhardwaj | | |
| Bhavya Jain | | |
