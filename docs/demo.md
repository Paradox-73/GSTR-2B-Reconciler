# Demo runbook

The demo script from DESIGN.md section 17, with the exact commands. Everything here was run on a
k3s test cluster; numbers in brackets are what that run gave. On the demo laptop minikube replaces
k3s, so the app URL is `http://$(minikube ip)`.

## Before the demo (30 min)

1. Cluster up, app deployed, Vault mode:
   `ansible-playbook -i deploy/ansible/inventory/hosts.ini deploy/ansible/site.yml`
   then `... deploy.yml -e image_tag=<sha> -e dockerhub_user=<user> -e app_use_vault=true`
2. Vault forgets everything if its pod restarted (dev mode). Re-run the Vault role: it restores
   engines, policies and the KV secrets in one go.
3. Jenkins up: `docker compose -f deploy/jenkins/docker-compose.yml --profile tunnel up -d`,
   update the GitHub webhook to the new tunnel URL (`deploy/jenkins/README.md`).
4. Kibana dashboards imported (`deploy/elk/README.md`).
5. Test data: `python -m datagen --seed 1 --invoices 300 --out demo-data --xlsx`
6. Workers idle at 1 replica: `kubectl -n gstr2b get hpa worker` shows `REPLICAS 1`.

## 1. The app

Log in, create a client (GSTIN from `demo-data/gstr2b.json` -> `data.gstin`), upload
`gstr2b.json` and `books.xlsx` for 2025-04, map the columns, run. Walk through the categories,
reason codes, a vendor note, the Excel export, and the model version on the run page.

## 2-4. Push -> pipeline -> visible on refresh, zero downtime

1. Start steady traffic (keep it running):
   `docker run --rm -v $PWD/tests/load:/load -w /load grafana/k6:0.54.0 run -e BASE_URL=http://<app> -e EMAIL=... -e PASSWORD=... -e DURATION=6m steady.js`
2. Make a visible change (e.g. a word in the header in `frontend/src`), commit, push to `main`.
3. Jenkins starts by itself (webhook). Stages: tests -> golden set -> model gate -> build ->
   Trivy -> push -> Ansible deploy -> smoke test.
4. Refresh the browser: the change and the new build label (git sha) in the header.
5. k6 finishes: `http_req_failed 0.00%` [0 of 4,131 during an api+frontend rollout].

## 5. A bad commit gets blocked

Break invoice number normalisation (e.g. stop stripping leading zeros in
`matcher/normalise.py`), push. The golden-set stage fails and lists the wrong pairs [8 wrong];
nothing is built or deployed. Revert and push.

## 6. Filing-week spike -> HPA 1 -> 5

```bash
python -m datagen --seed 77 --invoices 2000 --suppliers 200 --out tests/load/data
docker run --rm -v $PWD/tests/load:/load -w /load grafana/k6:0.54.0 run -e BASE_URL=http://<app> -e EMAIL=... -e PASSWORD=... -e PEAK=8 -e HOLD=2m spike.js
kubectl -n gstr2b get hpa worker -w          # second terminal
```

[1 -> 4 -> 5 workers in ~85s; 234 runs of 2000 invoices, 0 failed, p95 run 10.1s]

## 7. Review -> retrain -> new model live, no restart

1. Accept/reject probable matches in the UI (50+ decisions, or the trainer skips).
2. `kubectl -n gstr2b create job --from=cronjob/trainer trainer-demo`
3. `kubectl -n gstr2b logs job/trainer-demo | grep -E 'gate_result|model_promoted'` [r2 promoted]
4. Within a minute every worker logs `model_swapped` [5 of 5 in 35s, 0 restarts]
   (`kubectl -n gstr2b get pods` shows the same pods, no restarts).
5. Start a new run: the run page shows the new model version. MLflow UI shows the version history
   and the `production` alias.

## 8. Kibana

Operations, Reconciliation, Model (versions, decisions, gate history, swaps), Pipeline (deploys
per build sha).

## 9. Vault

- `kubectl -n vault exec vault-0 -- vault kv get secret/gstr2b/db` (credentials live in Vault)
- `kubectl -n gstr2b get pod <api-pod> -o jsonpath='{.spec.containers[*].name}'` -> `api vault-agent`
- An uploaded file on the volume is ciphertext:
  `kubectl -n gstr2b exec deploy/api -c api -- sh -c 'head -c 40 $(ls -t /data/uploads/*/* | head -1)'`
  -> `vault:v1:...`
