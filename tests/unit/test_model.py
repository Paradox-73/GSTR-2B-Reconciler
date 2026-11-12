from datetime import date
from decimal import Decimal as D

import numpy as np
import pytest

from matcher.engine import reconcile
from matcher.model import MatchModel
from matcher.models import BOOKS, GSTR2B, Category, Invoice
from trainer.dataset import synthetic
from trainer.evaluate import gate, metrics
from trainer.train import train

G = "27AAPFU0939F1ZV"


def inv(id_, src, no, taxable="1000"):
    return Invoice(id_, src, G, "X", no, date(2025, 4, 5), D(taxable), D(0), D(90), D(90), D(0))


class FixedScores:
    """Stands in for the model so assignment can be tested on its own."""
    version = "test"

    def __init__(self, table):
        self.table = table

    def score(self, pairs):
        return [self.table.get((b.id, g.id), 0.0) for b, g in pairs]


def test_one_to_one_assignment_takes_highest_score_first():
    books = [inv("B1", BOOKS, "A1"), inv("B2", BOOKS, "A2")]
    g2b = [inv("G1", GSTR2B, "X1"), inv("G2", GSTR2B, "X2")]
    model = FixedScores({("B1", "G1"): 0.95, ("B2", "G1"): 0.97, ("B1", "G2"): 0.6})
    rs = {(r.books_id, r.gstr2b_id): r for r in reconcile(books, g2b, model=model)}
    assert rs[("B2", "G1")].category == Category.PROBABLE  # took G1 first
    assert rs[("B1", "G2")].category == Category.REVIEW  # B1 falls back to its next best
    assert ("B1", "G1") not in rs


def test_below_review_threshold_stays_unmatched():
    rs = reconcile([inv("B1", BOOKS, "A1")], [inv("G1", GSTR2B, "X1")],
                   model=FixedScores({("B1", "G1"): 0.49}))
    assert {r.category for r in rs} == {Category.MISSING_IN_2B, Category.MISSING_IN_BOOKS}


def test_model_pair_with_value_diff_stays_probable_with_reason():
    rs = reconcile([inv("B1", BOOKS, "A1", taxable="900")], [inv("G1", GSTR2B, "X1")],
                   model=FixedScores({("B1", "G1"): 0.99}))
    (r,) = rs
    assert r.category == Category.PROBABLE and "VALUE_DIFF" in r.reasons and r.score == 0.99


def test_committed_model_loads_and_passes_gate():
    m = MatchModel.load()
    assert m.version and not gate(metrics(m))


def test_gate_rejects_a_bad_model():
    x, y = synthetic([7], n_invoices=200)
    bad = train(x, np.random.default_rng(0).permutation(y), "bad")  # labels scrambled
    assert gate(metrics(bad))


def test_feature_list_mismatch_refused():
    m = MatchModel.load()
    with pytest.raises(ValueError):
        MatchModel(m.booster, {**m.meta, "features": ["x"]})


def test_golden_seed_not_allowed_in_training():
    with pytest.raises(ValueError):
        synthetic([42])
