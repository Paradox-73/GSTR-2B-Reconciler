import json
from pathlib import Path

from datagen.__main__ import write
from datagen.generate import BOOKS_MAPPING, generate

V1 = "/api/v1"


def test_health(client):
    assert client.get("/healthz").json() == {"ok": True}
    r = client.get("/readyz")
    assert r.status_code == 200 and r.json()["db"] == "ok"


def test_login(client):
    assert client.post(f"{V1}/auth/login", json={"email": "ca@example.com",
                                                 "password": "nope"}).status_code == 401
    assert client.get(f"{V1}/clients").status_code == 401
    assert client.get(f"{V1}/clients", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_request_id_echoed(client):
    r = client.get("/healthz", headers={"x-request-id": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_client_gstin_validated(client, auth):
    r = client.post(f"{V1}/clients", json={"name": "X", "gstin": "27AAPFU0939F1ZA"}, headers=auth)
    assert r.status_code == 422 and "GSTIN" in r.text


def test_full_flow(client, auth, tmp_path: Path):
    ds = generate(seed=7, n_invoices=120, n_suppliers=15)
    write(ds, tmp_path, xlsx=True)

    r = client.post(f"{V1}/clients", json={"name": "Acme", "gstin": ds.recipient_gstin.lower()},
                    headers=auth)
    assert r.status_code == 201
    cid = r.json()["id"]
    assert any(c["id"] == cid for c in client.get(f"{V1}/clients", headers=auth).json())

    def up(kind, name, period="2025-04"):
        with open(tmp_path / name, "rb") as f:
            return client.post(f"{V1}/clients/{cid}/uploads", headers=auth,
                               data={"kind": kind, "period": period}, files={"file": (name, f)})

    # run before uploads -> told what's missing
    r = client.post(f"{V1}/clients/{cid}/runs", json={"period": "2025-04"}, headers=auth)
    assert r.status_code == 409 and "books and gstr2b" in r.text

    # books before mapping -> 409 with the file's headers so the UI can show the mapping screen
    r = up("books", "books.xlsx")
    assert r.status_code == 409 and "Bill No" in r.json()["detail"]["columns"]
    assert client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": {"invoice_no": "x"}},
                      headers=auth).status_code == 422
    assert client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": BOOKS_MAPPING},
                      headers=auth).status_code == 200

    assert up("gstr2b", "gstr2b.json", period="2025-05").status_code == 422  # wrong period
    r = up("gstr2b", "gstr2b.json")
    assert r.status_code == 201 and r.json()["invoice_count"] == len(
        [t for t in ds.truth if t["gstr2b_id"]])
    r = up("books", "books.xlsx")
    assert r.status_code == 201, r.text

    r = client.post(f"{V1}/clients/{cid}/runs", json={"period": "2025-04"}, headers=auth)
    assert r.status_code == 202
    run_id = r.json()["id"]
    run = client.get(f"{V1}/runs/{run_id}", headers=auth).json()  # ran in-process already
    assert run["status"] == "done" and run["model_version"] == "v1"
    want = {}
    for t in ds.truth:
        want[t["expected_category"]] = want.get(t["expected_category"], 0) + 1
    assert run["summary"]["counts"] == want

    res = client.get(f"{V1}/runs/{run_id}/results", headers=auth,
                     params={"category": "mismatch", "page_size": 500}).json()
    expected = sum(1 for t in ds.truth if t["expected_category"] == "mismatch")
    assert res["total"] == expected == len(res["items"])
    item = res["items"][0]
    assert item["books"]["invoice_no"] and item["gstr2b"]["invoice_no"]
    assert set(item["reason_codes"]) & {"VALUE_DIFF", "TAX_HEAD_DIFF"}

    # decisions: accept, bad link, good link
    rid = item["id"]
    r = client.post(f"{V1}/results/{rid}/decision", json={"decision": "accept"}, headers=auth)
    assert r.status_code == 201
    got = client.get(f"{V1}/runs/{run_id}/results", headers=auth,
                     params={"category": "mismatch", "page_size": 500}).json()["items"]
    assert next(i for i in got if i["id"] == rid)["decision"]["decision"] == "accept"

    missing_2b = client.get(f"{V1}/runs/{run_id}/results", headers=auth,
                            params={"category": "missing_in_2b"}).json()["items"][0]
    missing_books = client.get(f"{V1}/runs/{run_id}/results", headers=auth,
                               params={"category": "missing_in_books"}).json()["items"][0]
    bad = client.post(f"{V1}/results/{missing_2b['id']}/decision", headers=auth,
                      json={"decision": "link", "linked_invoice_id": missing_2b["books"]["id"]})
    assert bad.status_code == 422  # same side
    ok = client.post(f"{V1}/results/{missing_2b['id']}/decision", headers=auth,
                     json={"decision": "link",
                           "linked_invoice_id": missing_books["gstr2b"]["id"]})
    assert ok.status_code == 201


def test_other_users_cannot_see_clients(client, auth, app):
    from api.db import SessionLocal
    from api.security import create_token, hash_password
    from api.tables import User

    with SessionLocal() as db:
        u = User(email="other@example.com", password_hash=hash_password("pw"))
        db.add(u)
        db.commit()
        other = {"Authorization": f"Bearer {create_token(u)}"}
    cid = client.get(f"{V1}/clients", headers=auth).json()[0]["id"]
    assert client.get(f"{V1}/clients", headers=other).json() == []
    assert client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": BOOKS_MAPPING},
                      headers=other).status_code == 404


def test_2b_for_wrong_client_rejected(client, auth, tmp_path):
    ds = generate(seed=8, n_invoices=10, n_suppliers=3)
    cid = client.post(f"{V1}/clients", json={"name": "B", "gstin": "27AAPFU0939F1ZV"},
                      headers=auth).json()["id"]
    r = client.post(f"{V1}/clients/{cid}/uploads", headers=auth,
                    data={"kind": "gstr2b", "period": "2025-04"},
                    files={"file": ("2b.json", json.dumps(ds.gstr2b).encode())})
    assert r.status_code == 422 and "not this client" in r.text


def test_worker_settings_need_no_jwt(monkeypatch):
    import pytest

    from api.settings import Settings

    monkeypatch.delenv("JWT_SECRET")
    s = Settings()  # what the worker does
    with pytest.raises(RuntimeError):
        s.check_api()


def test_vendor_notes_and_export(client, auth):
    import io

    from openpyxl import load_workbook

    cid = next(c["id"] for c in client.get(f"{V1}/clients", headers=auth).json()
               if c["name"] == "Acme")
    run_id = client.get(f"{V1}/clients/{cid}/runs", headers=auth).json()[0]["id"]
    notes = client.get(f"{V1}/runs/{run_id}/vendor-notes", headers=auth).json()
    assert notes and all(n["body"].startswith("Dear ") for n in notes)
    assert any("Not showing in our GSTR-2B" in n["body"] for n in notes)

    r = client.get(f"{V1}/runs/{run_id}/export", headers=auth)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Results"]
    total = client.get(f"{V1}/runs/{run_id}", headers=auth).json()["summary"]["counts"]
    assert wb["Results"].max_row - 1 == sum(total.values())
