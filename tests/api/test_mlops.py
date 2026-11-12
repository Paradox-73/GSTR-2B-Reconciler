"""Review decisions -> retrain -> MLflow registry -> worker hot swap, on a local MLflow store."""
import pytest

V1 = "/api/v1"


@pytest.fixture
def mlflow_store(tmp_path, monkeypatch):
    import mlflow

    uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.chdir(tmp_path)  # local artifact store lands in ./mlruns here
    mlflow.set_tracking_uri(uri)
    return uri


def test_retrain_publish_and_hot_swap(client, auth, mlflow_store, monkeypatch):
    import trainer.__main__ as tr
    from api import jobs
    from matcher import registry

    # some real decisions on the run created by test_full_flow
    cid = next(c["id"] for c in client.get(f"{V1}/clients", headers=auth).json()
               if c["name"] == "Acme")
    run_id = client.get(f"{V1}/clients/{cid}/runs", headers=auth).json()[0]["id"]
    items = client.get(f"{V1}/runs/{run_id}/results", headers=auth,
                       params={"category": "probable_match", "page_size": 500}).json()["items"]
    assert items
    for i, it in enumerate(items):
        decision = "reject" if i == 0 else "accept"
        client.post(f"{V1}/results/{it['id']}/decision", json={"decision": decision},
                    headers=auth)

    holder = jobs.ModelHolder()
    assert tr.bootstrap() == 0
    holder.refresh()
    assert holder.get().version == "r1"
    assert tr.bootstrap() == 0  # idempotent: production exists, nothing new registered

    monkeypatch.setattr(tr, "TRAIN_SEEDS", [100, 101])  # small, keeps the test fast
    assert tr.retrain(force=False) == 0  # fewer than 50 new labels -> skipped
    c = registry.client()
    assert len(c.search_model_versions(f"name='{registry.NAME}'")) == 1

    assert tr.retrain(force=True) == 0
    versions = {v.version: v for v in c.search_model_versions(f"name='{registry.NAME}'")}
    assert set(versions) == {1, 2}
    gate = versions[2].tags["gate"]
    prod = registry.production_version().version
    assert prod == (2 if gate == "pass" else 1)

    # force the alias to r2 and check the worker swaps without a restart
    c.set_registered_model_alias(registry.NAME, registry.ALIAS, "2")
    before = holder.get()
    holder.refresh()
    assert holder.get().version == "r2" and holder.get() is not before


def test_labels_from_decisions(client, auth, app):
    from api.db import SessionLocal
    from trainer.labels import real_labels

    with SessionLocal() as db:
        labels = real_labels(db)
    assert labels
    assert any(lb.same_invoice for lb in labels) and any(not lb.same_invoice for lb in labels)
    assert all(lb.books.source == "books" and lb.gstr2b.source == "2b" for lb in labels)
