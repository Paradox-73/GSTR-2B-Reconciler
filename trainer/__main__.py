"""Retrain from review decisions, gate, publish to MLflow (DESIGN.md 9).

python -m trainer              nightly CronJob: skips unless enough new labels
python -m trainer --force      on demand (Jenkins job)
python -m trainer --bootstrap  registers the bundled model as production if the registry is empty
Exit 0 = trained or skipped (a gate failure just keeps the current model), 1 = error.
"""
import argparse
import os
import sys
import time
from datetime import UTC, datetime

import numpy as np
import yaml

from api import logs
from api.db import SessionLocal, engine
from matcher import config, registry
from matcher.features import features
from matcher.model import MatchModel
from trainer.evaluate import GATE, gate, metrics
from trainer.labels import Label, real_labels
from trainer.train import TRAIN_SEEDS, git_sha, train


def as_utc(ts: datetime) -> datetime:
    """SQLite hands back naive UTC; Postgres hands back aware times in the session's timezone,
    which isn't always UTC, so only label the naive ones."""
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)


def holdout_metrics(model: MatchModel, labels: list[Label]) -> dict:
    review = config.load()["review_threshold"]
    scores = model.score([(lb.books, lb.gstr2b) for lb in labels])
    pred = [s >= review for s in scores]
    truth = [lb.same_invoice for lb in labels]
    tp = sum(p and t for p, t in zip(pred, truth, strict=True))
    precision = tp / sum(pred) if any(pred) else 1.0
    recall = tp / sum(truth) if any(truth) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "n": len(labels)}


def holdout_gate(cand: dict, current: dict, g: dict) -> list[str]:
    if cand["n"] < g["min_holdout_labels"]:
        return []
    fails = [f"holdout {k} {cand[k]} < {g[f'min_{k}']}" for k in ("precision", "recall")
             if cand[k] < g[f"min_{k}"]]
    if g.get("f1_must_not_drop") and cand["f1"] < current["f1"]:
        fails.append(f"holdout f1 {cand['f1']} < current model's {current['f1']}")
    return fails


def bootstrap() -> int:
    if registry.production_version() is not None:
        logs.log("trainer_bootstrap_skipped", reason="production model exists")
        return 0
    model = MatchModel.load()
    version = registry.publish(model, metrics(model), True,
                               {"source": "bundled", "bundled_version": model.version})
    logs.log("model_promoted", model_version=f"r{version}", source="bundled")
    return 0


def retrain(force: bool) -> int:
    g = yaml.safe_load(GATE.read_text())
    prod = registry.production_version()
    current = registry.load_version(prod) if prod else MatchModel.load()
    engine()
    with SessionLocal() as db:
        labels = real_labels(db)
    since = datetime.fromtimestamp(prod.creation_timestamp / 1000, UTC) if prod else None
    new = sum(1 for lb in labels if since is None or as_utc(lb.decided_at) > since)
    if new < g["min_new_labels"] and not force:
        logs.log("trainer_skipped", new_labels=new, needed=g["min_new_labels"])
        return 0

    started = time.perf_counter()
    train_lb = [lb for lb in labels if not lb.holdout]
    holdout = [lb for lb in labels if lb.holdout]
    from trainer.dataset import synthetic

    x, y = synthetic(TRAIN_SEEDS)
    if train_lb:
        x = np.vstack([x, np.array([features(lb.books, lb.gstr2b) for lb in train_lb],
                                   dtype=np.float32)])
        y = np.concatenate([y, np.array([lb.same_invoice for lb in train_lb], dtype=np.float32)])
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    cand = train(x, y, f"cand-{stamp}", {"real_labels": len(train_lb)})

    golden, golden_now = metrics(cand), metrics(current)
    hold, hold_now = holdout_metrics(cand, holdout), holdout_metrics(current, holdout)
    fails = gate(golden, golden_now["f1"]) + holdout_gate(hold, hold_now, g)
    flat = {**{f"golden_{k}": v for k, v in golden.items()},
            **{f"holdout_{k}": v for k, v in hold.items()},
            "new_labels": new, "real_labels_train": len(train_lb)}
    version = registry.publish(cand, flat, not fails, {"git_sha": git_sha(),
                                                      "data_hash": cand.meta["data_hash"],
                                                      "fails": "; ".join(fails)[:500]})
    logs.log("gate_result", passed=not fails, fails=fails, model_version=f"r{version}",
             current_version=current.version, golden_f1=golden["f1"],
             current_golden_f1=golden_now["f1"], holdout_f1=hold["f1"], holdout_n=hold["n"],
             real_labels=len(train_lb), duration_ms=round((time.perf_counter() - started) * 1000))
    if not fails:
        logs.log("model_promoted", model_version=f"r{version}", source="trainer")
    return 0


def main() -> int:
    os.environ.setdefault("SERVICE_NAME", "trainer")
    logs.setup()
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    a = ap.parse_args()
    if not registry.enabled():
        logs.log("trainer_error", 40, reason="MLFLOW_TRACKING_URI is not set")
        return 1
    return bootstrap() if a.bootstrap else retrain(a.force)


if __name__ == "__main__":
    sys.exit(main())
