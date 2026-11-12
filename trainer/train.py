"""python -m trainer.train --version v1   (writes models/matcher.json + matcher.meta.json)"""
import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xgboost as xgb

from matcher.features import NAMES
from matcher.model import DEFAULT_PATH, MatchModel
from trainer.dataset import synthetic
from trainer.evaluate import gate, metrics

PARAMS = {"objective": "binary:logistic", "eval_metric": "logloss", "max_depth": 4, "eta": 0.1,
          "subsample": 0.9, "colsample_bytree": 0.9, "min_child_weight": 2, "seed": 0,
          "nthread": 1}  # nthread=1 keeps training bit-for-bit reproducible
ROUNDS = 200
TRAIN_SEEDS = list(range(100, 160))


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def train(x: np.ndarray, y: np.ndarray, version: str, extra_meta: dict | None = None):
    booster = xgb.train(PARAMS, xgb.DMatrix(x, label=y, feature_names=NAMES), ROUNDS)
    data_hash = hashlib.sha256(x.tobytes() + y.tobytes()).hexdigest()[:16]
    meta = {"version": version, "features": NAMES, "params": PARAMS, "rounds": ROUNDS,
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"), "git_sha": git_sha(),
            "train_rows": int(len(y)), "train_positives": int(y.sum()), "data_hash": data_hash,
            **(extra_meta or {})}
    return MatchModel(booster, meta)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", type=Path, default=DEFAULT_PATH)
    a = ap.parse_args()
    x, y = synthetic(TRAIN_SEEDS)
    model = train(x, y, a.version, {"train_seeds": [TRAIN_SEEDS[0], TRAIN_SEEDS[-1]]})
    m = metrics(model)
    model.meta["golden_metrics"] = m
    fails = gate(m)
    print(json.dumps({"version": a.version, "rows": len(y), **m, "gate_fails": fails}))
    if fails:
        raise SystemExit("not saving: " + "; ".join(fails))
    model.save(a.out)
    print(f"saved {a.out}")


if __name__ == "__main__":
    main()
