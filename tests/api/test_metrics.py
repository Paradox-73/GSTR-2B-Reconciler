"""Prometheus metrics (#66). The dashboard in deploy/k8s-monitoring queries these names."""
import csv
import io
import json
import re

V1 = "/api/v1"


def scrape(client) -> str:
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    return r.text


def value(text: str, name: str, **labels) -> float:
    """Sum of every sample of `name` whose labels include `labels`."""
    total = 0.0
    for line in text.splitlines():
        m = re.match(rf"^{name}(?:\{{(.*)\}})? (\S+)$", line)
        if m and all(f'{k}="{v}"' in (m[1] or "") for k, v in labels.items()):
            total += float(m[2])
    return total


def test_http_metrics_use_the_route_template(client, auth):
    r = client.post(f"{V1}/clients", json={"name": "Metrics", "gstin": "27AAPFU0939F1ZV"},
                    headers=auth)
    cid = r.json()["id"]
    before = value(scrape(client), "http_requests_total", method="GET",
                   route="/api/v1/clients/{client_id}", status="200")
    assert client.get(f"{V1}/clients/{cid}", headers=auth).status_code == 200
    text = scrape(client)
    after = value(text, "http_requests_total", method="GET",
                  route="/api/v1/clients/{client_id}", status="200")
    assert after == before + 1
    assert cid not in text  # raw ids would give one time series per client / run
    assert 'http_request_duration_seconds_bucket{le="+Inf",route="/api/v1/clients/{client_id}"}' \
        in text
    assert 'app_info{version="' in text


def test_unknown_paths_are_one_series(client):
    client.get("/no/such/page/123")
    client.get("/no/such/page/456")
    text = scrape(client)
    assert "/no/such/page" not in text
    assert value(text, "http_requests_total", route="unmatched", status="404") >= 2


def test_run_metrics(client, auth):
    from datagen.generate import BOOKS_MAPPING, generate

    ds = generate(seed=21, n_invoices=20, n_suppliers=3)
    cid = client.post(f"{V1}/clients", json={"name": "Metrics run", "gstin": ds.recipient_gstin},
                      headers=auth).json()["id"]
    client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": BOOKS_MAPPING}, headers=auth)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(ds.books[0]))
    w.writeheader()
    w.writerows(ds.books)
    for kind, name, body in (("gstr2b", "2b.json", json.dumps(ds.gstr2b).encode()),
                             ("books", "b.csv", buf.getvalue().encode())):
        r = client.post(f"{V1}/clients/{cid}/uploads", headers=auth,
                        data={"kind": kind, "period": ds.period}, files={"file": (name, body)})
        assert r.status_code == 201, r.text

    before = scrape(client)
    run = client.post(f"{V1}/clients/{cid}/runs", json={"period": ds.period}, headers=auth)
    run = client.get(f"{V1}/runs/{run.json()['id']}", headers=auth).json()
    assert run["status"] == "done"
    after = scrape(client)

    assert value(after, "reconcile_runs_total", status="done") == \
        value(before, "reconcile_runs_total", status="done") + 1
    assert value(after, "reconcile_run_seconds_count") == \
        value(before, "reconcile_run_seconds_count") + 1
    added = value(after, "reconcile_invoices_total") - value(before, "reconcile_invoices_total")
    assert added == sum(run["summary"]["counts"].values())
    assert value(after, "model_version_info", version=run["model_version"]) == 1
