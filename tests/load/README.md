# Load tests (k6)

Two scripts for the demo (DESIGN.md 13.6, 17 steps 4 and 6). Run k6 from Docker, no install needed.

```bash
# from the repo root; on Docker Desktop use host.docker.internal to reach the host
K6="docker run --rm -v $PWD/tests/load:/load -w /load grafana/k6:0.54.0 run"
APP=http://<minikube-ip>          # or http://host.docker.internal:8080 for compose
```

## Zero-downtime rollout (`steady.js`)

Steady 20 req/s against the UI and API. Start it, then trigger a deploy (push a commit, or
`kubectl -n gstr2b rollout restart deploy/api deploy/frontend`). Pass = `http_req_failed 0.00%`.

```bash
$K6 -e BASE_URL=$APP -e EMAIL=<admin> -e PASSWORD=<pw> -e DURATION=3m steady.js
```

## Filing-week spike (`spike.js`)

Many 2000-invoice reconciliations at once, so worker CPU climbs and the HPA scales 1 -> 5.

```bash
python -m datagen --seed 77 --invoices 2000 --suppliers 200 --out tests/load/data
$K6 -e BASE_URL=$APP -e EMAIL=<admin> -e PASSWORD=<pw> -e PEAK=15 spike.js
kubectl -n gstr2b get hpa worker -w     # in another terminal
```

Knobs: `PEAK` (virtual users), `HOLD` (time at peak, default 4m). Threshold: p95 run time < 30s.

## Numbers from compose (one worker, laptop)

| script | settings | result |
|---|---|---|
| steady | 10 req/s, 30s | 600/600 checks, 0 failed, p95 12ms |
| spike | 4 VUs, 40s hold | 211 runs of 2000 invoices, 0 failed, p95 run 3.05s |
