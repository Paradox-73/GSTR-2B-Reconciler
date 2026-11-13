"""Regression tests for the correctness half of #54."""
from datetime import UTC, datetime, timedelta

V1 = "/api/v1"


def _acme(client, auth):
    cid = next(c["id"] for c in client.get(f"{V1}/clients", headers=auth).json()
               if c["name"] == "Acme")
    run_id = next(r["id"] for r in client.get(f"{V1}/clients/{cid}/runs", headers=auth).json()
                  if r["status"] == "done")
    return cid, run_id


def _results(client, auth, run_id, category):
    return client.get(f"{V1}/runs/{run_id}/results", headers=auth,
                      params={"category": category, "page_size": 500}).json()["items"]


def _missing_sections(client, auth, run_id) -> str:
    """The 'not showing in our GSTR-2B' part of every vendor note."""
    out = []
    for n in client.get(f"{V1}/runs/{run_id}/vendor-notes", headers=auth).json():
        body = n["body"]
        if "Not showing in our GSTR-2B" in body:
            out.append(body.split("Not showing in our GSTR-2B")[1].split("Amounts in your")[0])
    return "\n".join(out)


def test_vendor_notes_follow_review_decisions(client, auth):
    _, run_id = _acme(client, auth)

    # a mismatch the CA rejects: the books invoice is now "missing in 2B", not "amounts differ"
    mm = _results(client, auth, run_id, "mismatch")[0]
    inv_no = mm["books"]["invoice_no"]
    assert f"Invoice {inv_no} dated" not in _missing_sections(client, auth, run_id)
    client.post(f"{V1}/results/{mm['id']}/decision", json={"decision": "reject"}, headers=auth)
    assert f"Invoice {inv_no} dated" in _missing_sections(client, auth, run_id)

    # a missing-in-2B invoice the CA links to a 2B invoice drops out of the "missing" list
    miss = [m for m in _results(client, auth, run_id, "missing_in_2b") if not m["decision"]][0]
    other = _results(client, auth, run_id, "missing_in_books")[-1]
    no = miss["books"]["invoice_no"]
    assert f"Invoice {no} dated" in _missing_sections(client, auth, run_id)
    client.post(f"{V1}/results/{miss['id']}/decision", headers=auth,
                json={"decision": "link", "linked_invoice_id": other["gstr2b"]["id"]})
    assert f"Invoice {no} dated" not in _missing_sections(client, auth, run_id)


def test_failed_results_write_marks_run_failed(client, auth, monkeypatch):
    from api import jobs
    from api.db import SessionLocal
    from api.tables import Run

    cid, _ = _acme(client, auth)
    real_commit = jobs.SessionLocal.class_.commit
    calls = {"n": 0}

    def flaky_commit(self):
        calls["n"] += 1
        if calls["n"] == 3:  # 1 = route creates the run, 2 = status running, 3 = results
            raise RuntimeError("disk full")
        return real_commit(self)

    monkeypatch.setattr(jobs.SessionLocal.class_, "commit", flaky_commit)
    run_id = client.post(f"{V1}/clients/{cid}/runs", json={"period": "2025-04"},
                         headers=auth).json()["id"]
    monkeypatch.setattr(jobs.SessionLocal.class_, "commit", real_commit)
    with SessionLocal() as db:
        run = db.get(Run, __import__("uuid").UUID(run_id))
        assert run.status == "failed" and run.error == "RuntimeError" and run.finished_at


def test_queued_runs_get_a_longer_grace_period(client, auth):
    from api import jobs
    from api.db import SessionLocal
    from api.tables import Run

    with SessionLocal() as db:
        done = db.query(Run).filter(Run.status == "done").first()
        mk = lambda mins: Run(client_id=done.client_id, period=done.period, status="queued",  # noqa: E731
                              books_upload_id=done.books_upload_id,
                              gstr2b_upload_id=done.gstr2b_upload_id,
                              created_at=datetime.now(UTC) - timedelta(minutes=mins))
        waiting, lost = mk(30), mk(180)
        db.add_all([waiting, lost])
        db.commit()
        ids = waiting.id, lost.id
    jobs.reap_stuck_runs()
    with SessionLocal() as db:
        assert db.get(Run, ids[0]).status == "queued"
        assert db.get(Run, ids[1]).status == "failed"


def test_broken_model_version_not_refetched(monkeypatch):
    from api import jobs
    from matcher import registry

    class MV:
        version = 9

    fetches = {"n": 0}

    def broken(mv):
        fetches["n"] += 1
        raise ValueError("feature list changed")

    monkeypatch.setattr(registry, "enabled", lambda: True)
    monkeypatch.setattr(registry, "production_version", lambda: MV())
    monkeypatch.setattr(registry, "load_version", broken)
    holder = jobs.ModelHolder()
    holder.refresh()
    holder.refresh()
    holder.refresh()
    assert fetches["n"] == 1 and holder.get() is not None  # fell back to the bundled model


def test_admin_created_late_by_readyz(client, monkeypatch):
    """Fresh cluster: the api starts before migrations, so the first seed attempt fails."""
    from api import main
    from api.db import SessionLocal
    from api.tables import User

    monkeypatch.setenv("ADMIN_EMAIL", "late-admin@example.com")
    monkeypatch.setattr(main, "_admin_ready", False)
    main.get_settings.cache_clear()
    try:
        assert client.get("/readyz").status_code == 200
        with SessionLocal() as db:
            assert db.query(User).filter(User.email == "late-admin@example.com").one()
        assert main._admin_ready
    finally:
        main.get_settings.cache_clear()
