"""Full engine on the fixed-seed golden set vs ground truth. Matching regressions fail here."""
import csv
import json
from collections import Counter

import pytest

from matcher import config
from matcher.engine import reconcile
from matcher.model import MatchModel
from matcher.models import Category
from matcher.parsers import load_books, load_gstr2b

GOLDEN = "tests/golden/"
NEEDS_MODEL = {Category.PROBABLE.value}  # pairs only the model can find


def _run(model):
    cfg = config.load()
    books = load_books(GOLDEN + "books.csv", json.load(open(GOLDEN + "mapping.json")))
    g2b = load_gstr2b(GOLDEN + "gstr2b.json")
    results = reconcile(books, g2b, cfg["amount_tolerance"], model, cfg["probable_threshold"],
                        cfg["review_threshold"], cfg["candidate_value_pct"],
                        cfg["candidate_date_days"])
    return results, list(csv.DictReader(open(GOLDEN + "truth.csv")))


@pytest.fixture(scope="module")
def run():
    """Exact pass only: everything except the model's cases must already be right."""
    return _run(None)


@pytest.fixture(scope="module")
def full_run():
    return _run(MatchModel.load())


def test_full_engine_matches_truth_exactly(full_run):
    results, truth = full_run
    by_pair = {(r.books_id or "", r.gstr2b_id or ""): r for r in results}
    wrong = []
    for t in truth:
        r = by_pair.get((t["books_id"], t["gstr2b_id"]))
        got = (r.category.value, "|".join(r.reasons)) if r else ("<not paired>", "")
        if got != (t["expected_category"], t["expected_reasons"]):
            wrong.append(f"{t['books_id']}/{t['gstr2b_id']} {t['error']}: "
                         f"expected {t['expected_category']} {t['expected_reasons']}, got {got}")
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:20])
    assert Counter(r.category.value for r in results) == Counter(
        t["expected_category"] for t in truth)


def test_every_invoice_lands_exactly_once(run):
    results, truth = run
    books_ids = [r.books_id for r in results if r.books_id]
    g2b_ids = [r.gstr2b_id for r in results if r.gstr2b_id]
    assert len(books_ids) == len(set(books_ids)) == sum(1 for t in truth if t["books_id"])
    assert len(g2b_ids) == len(set(g2b_ids)) == sum(1 for t in truth if t["gstr2b_id"])


def test_categories_and_reasons_match_truth(run):
    results, truth = run
    by_pair = {(r.books_id or "", r.gstr2b_id or ""): r for r in results}
    wrong = []
    for t in truth:
        if t["expected_category"] in NEEDS_MODEL:
            continue
        r = by_pair.get((t["books_id"], t["gstr2b_id"]))
        got = (r.category.value, "|".join(r.reasons)) if r else ("<not paired>", "")
        if got != (t["expected_category"], t["expected_reasons"]):
            wrong.append(f"{t['books_id']}/{t['gstr2b_id']} {t['error']}: "
                         f"expected {t['expected_category']} {t['expected_reasons']}, got {got}")
    assert not wrong, f"{len(wrong)} wrong:\n" + "\n".join(wrong[:20])


def test_model_cases_stay_unmatched_without_model(run):
    """Exact pass must not invent matches for the hard cases."""
    results, truth = run
    cats = {r.books_id: r.category for r in results if r.books_id}
    hard = [t for t in truth if t["expected_category"] in NEEDS_MODEL]
    assert hard and all(cats[t["books_id"]] == Category.MISSING_IN_2B for t in hard)


def test_category_counts(run):
    results, truth = run
    got = Counter(r.category.value for r in results)
    expected = Counter(t["expected_category"] for t in truth
                       if t["expected_category"] not in NEEDS_MODEL)
    hard = sum(1 for t in truth if t["expected_category"] in NEEDS_MODEL)
    expected["missing_in_2b"] += hard
    expected["missing_in_books"] += hard
    assert got == expected
