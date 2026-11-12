import time
from datetime import date
from decimal import Decimal as D

from datagen.generate import generate
from matcher.candidates import candidates
from matcher.engine import exact_pass
from matcher.features import NAMES, features
from matcher.models import BOOKS, GSTR2B, Invoice
from matcher.parsers import parse_books, parse_gstr2b


def leftovers(seed, n):
    import pandas as pd

    from datagen.generate import BOOKS_MAPPING

    ds = generate(seed=seed, n_invoices=n, n_suppliers=max(10, n // 10))
    books = parse_books(pd.DataFrame(ds.books), BOOKS_MAPPING)
    g2b = parse_gstr2b(ds.gstr2b)
    _, lb, lg = exact_pass(books, g2b, D("1"))
    return ds, lb, lg


def test_candidates_contain_every_true_hard_pair():
    for seed in (42, 1, 2):
        ds, lb, lg = leftovers(seed, 400)
        pairs = {(b.id, g.id) for b, g in candidates(lb, lg)}
        hard = [(t["books_id"], t["gstr2b_id"]) for t in ds.truth
                if t["expected_category"] == "probable_match"]
        assert hard and all(p in pairs for p in hard), seed


def test_candidate_count_stays_small_at_2000():
    _, lb, lg = leftovers(9, 2000)
    t = time.perf_counter()
    pairs = candidates(lb, lg)
    elapsed = time.perf_counter() - t
    assert len(pairs) < 10 * max(len(lb), len(lg)), len(pairs)
    assert elapsed < 5, elapsed


def inv(id_, src, no, gstin="27AAPFU0939F1ZV", d=date(2025, 4, 5), taxable="1000", igst="0",
        cgst="90", sgst="90"):
    return Invoice(id_, src, gstin, "X", no, d, D(taxable), D(igst), D(cgst), D(sgst), D("0"))


def f(b, g):
    return dict(zip(NAMES, features(b, g), strict=True))


def test_features_identical_pair():
    x = f(inv("B1", BOOKS, "INV/42"), inv("G1", GSTR2B, "INV/42"))
    assert x["inv_lev_ratio"] == 1 and x["inv_numeric_equal"] == 1 and x["gstin_equal"] == 1
    assert x["date_diff_days"] == 0 and x["total_rel_diff"] == 0 and x["tax_head_mismatch"] == 0


def test_features_fy_prefix_variant():
    x = f(inv("B1", BOOKS, "2025-26/42"), inv("G1", GSTR2B, "SPI/0042"))
    assert x["inv_numeric_equal"] == 1 and x["inv_lev_ratio"] < 1


def test_features_gstin_typo_and_head_swap():
    x = f(inv("B1", BOOKS, "1", gstin="28AAPFU0939F1ZV", igst="180", cgst="0", sgst="0"),
          inv("G1", GSTR2B, "1"))
    assert x["gstin_equal"] == 0 and x["pan_equal"] == 1 and x["gstin_edit_distance"] == 1
    assert x["tax_head_mismatch"] == 1 and x["tax_abs_diff"] == 0


def test_feature_vector_length_matches_names():
    assert len(features(inv("B1", BOOKS, "1"), inv("G1", GSTR2B, "2"))) == len(NAMES)
