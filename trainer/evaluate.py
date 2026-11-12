"""Model quality gate (DESIGN.md 9.3): python -m trainer.evaluate [--model path]. Exit 1 = fail.

Metrics are on the model stage only (pairs the exact pass missed), on the golden set. Overall
pair metrics would hide a bad model behind the easy exact matches.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import yaml

from matcher import config
from matcher.engine import reconcile
from matcher.model import DEFAULT_PATH, MatchModel
from matcher.parsers import load_books, load_gstr2b

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"
GATE = ROOT / "config" / "quality_gate.yaml"


def metrics(model: MatchModel, golden: Path = GOLDEN) -> dict:
    cfg = config.load()
    books = load_books(golden / "books.csv", json.loads((golden / "mapping.json").read_text()))
    g2b = load_gstr2b(golden / "gstr2b.json")
    results = reconcile(books, g2b, cfg["amount_tolerance"], model, cfg["probable_threshold"],
                        cfg["review_threshold"], cfg["candidate_value_pct"],
                        cfg["candidate_date_days"])
    with open(golden / "truth.csv") as f:
        truth = list(csv.DictReader(f))
    true_pairs = {(t["books_id"], t["gstr2b_id"]) for t in truth}
    hard = {(t["books_id"], t["gstr2b_id"]) for t in truth
            if t["expected_category"] == "probable_match"}
    found = {(r.books_id, r.gstr2b_id) for r in results if r.score is not None}
    tp = len(found & true_pairs)
    precision = tp / len(found) if found else 0.0
    recall = len(found & hard) / len(hard) if hard else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    auto = sum(1 for r in results if r.score is not None and r.score >= cfg["probable_threshold"])
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "model_pairs": len(found), "hard_pairs": len(hard), "auto_matched": auto}


def gate(m: dict, current_f1: float | None = None) -> list[str]:
    g = yaml.safe_load(GATE.read_text())
    fails = []
    if m["precision"] < g["min_precision"]:
        fails.append(f"precision {m['precision']} < {g['min_precision']}")
    if m["recall"] < g["min_recall"]:
        fails.append(f"recall {m['recall']} < {g['min_recall']}")
    if g.get("f1_must_not_drop") and current_f1 is not None and m["f1"] < current_f1:
        fails.append(f"f1 {m['f1']} < current model's {current_f1}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=DEFAULT_PATH)
    a = ap.parse_args()
    model = MatchModel.load(a.model)
    m = metrics(model)
    fails = gate(m)
    print(json.dumps({"model_version": model.version, **m, "passed": not fails}))
    for f in fails:
        print(f"GATE FAIL: {f}", file=sys.stderr)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
