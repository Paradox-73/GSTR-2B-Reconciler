"""End-to-end check against a running deployment (Jenkins runs this after every deploy).

python scripts/smoke_test.py --base-url http://localhost:8000
Credentials come from SMOKE_EMAIL / SMOKE_PASSWORD. Exit code 0 = healthy and correct.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datagen.generate import BOOKS_MAPPING, generate  # noqa: E402

# Categories the exact pass decides on its own, so they must match ground truth exactly
# whatever model version is deployed.
EXACT = ("mismatch", "itc_not_available")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("APP_URL", "http://localhost:8000"))
    ap.add_argument("--invoices", type=int, default=20)
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()
    email, password = os.environ.get("SMOKE_EMAIL"), os.environ.get("SMOKE_PASSWORD")
    if not (email and password):
        print("set SMOKE_EMAIL and SMOKE_PASSWORD")
        return 2

    api = httpx.Client(base_url=a.base_url.rstrip("/"), timeout=30)
    api.get("/healthz").raise_for_status()
    token = api.post("/api/v1/auth/login", json={"email": email, "password": password})
    token.raise_for_status()
    api.headers["Authorization"] = f"Bearer {token.json()['access_token']}"

    ds = generate(seed=int(time.time()), n_invoices=a.invoices, n_suppliers=5)
    client = api.post("/api/v1/clients", json={"name": f"smoke-{int(time.time())}",
                                                "gstin": ds.recipient_gstin})
    client.raise_for_status()
    cid = client.json()["id"]
    api.put(f"/api/v1/clients/{cid}/mapping", json={"mapping": BOOKS_MAPPING}).raise_for_status()

    import pandas as pd

    books_csv = pd.DataFrame(ds.books).assign(
        Date=lambda d: pd.to_datetime(d["Date"]).dt.strftime("%d-%m-%Y")).to_csv(index=False)
    for kind, name, body in (("gstr2b", "2b.json", json.dumps(ds.gstr2b)),
                             ("books", "books.csv", books_csv)):
        r = api.post(f"/api/v1/clients/{cid}/uploads", data={"kind": kind, "period": ds.period},
                     files={"file": (name, body.encode())})
        r.raise_for_status()

    run = api.post(f"/api/v1/clients/{cid}/runs", json={"period": ds.period})
    run.raise_for_status()
    run_id, deadline = run.json()["id"], time.time() + a.timeout
    while (status := api.get(f"/api/v1/runs/{run_id}").json())["status"] in ("queued", "running"):
        if time.time() > deadline:
            print(f"FAIL: run {run_id} still {status['status']} after {a.timeout}s")
            return 1
        time.sleep(1)
    if status["status"] != "done":
        print(f"FAIL: run {run_id} ended {status['status']}: {status['error']}")
        return 1

    got = status["summary"]["counts"]
    want = Counter(t["expected_category"] for t in ds.truth)
    wrong = {c: (got.get(c, 0), want.get(c, 0)) for c in EXACT if got.get(c, 0) != want.get(c, 0)}
    total = sum(got.values())
    if wrong or total < len(ds.books):
        print(f"FAIL: run {run_id} counts (got, expected): {wrong}, total {total}")
        return 1
    print(f"OK: run {run_id} model {status['model_version']} counts {got}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
