# Logs and dashboards

App services log one JSON object per line (`docs/runtime-contract.md`). Filebeat ships container
logs to Logstash, which parses the JSON into `app.*` fields and writes daily `gstr2b-logs-*`
indices to Elasticsearch. Kibana has 4 dashboards (DESIGN.md 14.3): Operations, Reconciliation,
Model, Pipeline.

## Local (compose)

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.elk.yml up -d
```

Kibana on http://localhost:5601, dashboards are imported by the `kibana-setup` one-shot. Needs about
3GB more RAM than the app alone.

## Kubernetes

`roles/elk` deploys the same `logstash.conf`; `filebeat.yml` is the DaemonSet version. Import the
dashboards once Kibana is up:

```bash
kubectl -n logging port-forward svc/kibana 5601:5601 &
curl -X POST "localhost:5601/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" --form file=@deploy/elk/kibana-export.ndjson
```

## Changing dashboards

Edit `build_dashboards.py`, run `python deploy/elk/build_dashboards.py`, commit the regenerated
`kibana-export.ndjson`. Don't edit the ndjson by hand.

Events the dashboards use: `request` (path, status_code, duration_ms), `run_completed` (counts,
duration_ms, model_version), `run_failed`, `runs_reaped`, `review_decision`, `gate_result`,
`model_promoted`, `model_swapped`, `app_started` (version = build's git sha).
