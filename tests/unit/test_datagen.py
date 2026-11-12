import json
from collections import Counter

from datagen.__main__ import write
from datagen.generate import BOOKS_MAPPING, ERRORS, generate
from matcher import gstin
from matcher.parsers import load_books, load_gstr2b, parse_gstr2b


def test_same_seed_same_data():
    a, b = generate(seed=3, n_invoices=50), generate(seed=3, n_invoices=50)
    assert a.truth == b.truth and a.gstr2b == b.gstr2b and a.books == b.books
    assert generate(seed=4, n_invoices=50).truth != a.truth


def test_every_error_type_planted():
    counts = Counter(t["error"] for t in generate(seed=42).truth)
    assert set(counts) == set(ERRORS)
    assert min(counts.values()) >= 5


def _roundtrip(tmp_path, **kw):
    ds = generate(**kw)
    write(ds, tmp_path, xlsx=False)
    books = {i.id: i for i in load_books(tmp_path / "books.csv", BOOKS_MAPPING)}
    g2b = {i.id: i for i in load_gstr2b(tmp_path / "gstr2b.json")}
    return ds, books, g2b


def test_truth_points_at_the_right_invoices(tmp_path):
    ds, books, g2b = _roundtrip(tmp_path, seed=42)
    assert len(books) == sum(1 for t in ds.truth if t["books_id"])
    assert len(g2b) == sum(1 for t in ds.truth if t["gstr2b_id"])
    for t in ds.truth:
        b, g = books.get(t["books_id"]), g2b.get(t["gstr2b_id"])
        e = t["error"]
        if e == "not_filed":
            assert b and not g
        elif e == "extra_in_2b":
            assert g and not b
        else:
            assert b and g, t
            same_key = (b.supplier_gstin, b.inv_no_norm) == (g.supplier_gstin, g.inv_no_norm)
            assert same_key == (e not in ("inv_no_format_hard", "gstin_typo")), t
            if e == "clean":
                assert b.inv_no_raw == g.inv_no_raw and b.inv_date == g.inv_date
                assert (b.taxable, b.igst, b.cgst, b.sgst, b.cess) == \
                       (g.taxable, g.igst, g.cgst, g.sgst, g.cess)
            if e == "inv_no_format_easy":
                assert b.inv_no_raw != g.inv_no_raw
            if e == "rounding":
                assert 0 < abs(b.taxable - g.taxable) <= 1
            if e == "value_error":
                assert abs(b.taxable - g.taxable) > 1
            if e == "tax_head_swap":
                assert b.total_tax == g.total_tax and (b.igst == 0) != (g.igst == 0)
            if e == "gstin_typo":
                assert b.pan == g.pan and b.supplier_gstin != g.supplier_gstin
            if e == "itc_ineligible":
                assert not g.itc_available
            if e == "date_shift":
                assert 1 <= abs((b.inv_date - g.inv_date).days) <= 5


def test_suppliers_have_valid_gstins():
    doc = generate(seed=42).gstr2b
    assert all(gstin.is_valid(s["ctin"]) for s in doc["data"]["docdata"]["b2b"])


def test_items_format_parses_the_same():
    flat, items = generate(seed=5, flat=True).gstr2b, generate(seed=5, flat=False).gstr2b
    assert parse_gstr2b(flat) == parse_gstr2b(items)


def test_golden_set_matches_generator(tmp_path):
    """Fails if datagen changed without regenerating tests/golden (see its README)."""
    write(generate(seed=42, n_invoices=400), tmp_path, xlsx=False)
    for name in ("gstr2b.json", "books.csv", "truth.csv"):
        assert (tmp_path / name).read_text() == open(f"tests/golden/{name}").read(), name
    assert json.load(open("tests/golden/mapping.json")) == BOOKS_MAPPING
