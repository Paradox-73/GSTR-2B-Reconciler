from dataclasses import replace
from datetime import date
from decimal import Decimal as D

from matcher.engine import reconcile
from matcher.models import BOOKS, GSTR2B, Category, Invoice, Reason

G = "27AAPFU0939F1ZV"


def inv(id_, src=BOOKS, no="INV/42", **kw):
    base = dict(id=id_, source=src, supplier_gstin=G, supplier_name="X", inv_no_raw=no,
                inv_date=date(2025, 4, 5), taxable=D("1000"), igst=D("0"), cgst=D("90"),
                sgst=D("90"), cess=D("0"))
    return Invoice(**{**base, **kw})


def one(books, g2b, tol=D("1")):
    (r,) = reconcile(books, g2b, tol)
    return r


def test_clean_match():
    r = one([inv("B1")], [inv("G1", GSTR2B)])
    assert (r.books_id, r.gstr2b_id, r.category, r.reasons) == ("B1", "G1", Category.MATCHED, ())


def test_tolerance_is_inclusive():
    assert one([inv("B1", taxable=D("1001"))], [inv("G1", GSTR2B)]).category == Category.MATCHED
    r = one([inv("B1", taxable=D("1001.01"))], [inv("G1", GSTR2B)])
    assert r.category == Category.MISMATCH and r.reasons == (Reason.VALUE_DIFF,)


def test_tax_head_swap_vs_tax_diff():
    swap = inv("B1", igst=D("180"), cgst=D("0"), sgst=D("0"))
    assert one([swap], [inv("G1", GSTR2B)]).reasons == (Reason.TAX_HEAD_DIFF,)
    more_tax = inv("B1", cgst=D("100"))
    assert one([more_tax], [inv("G1", GSTR2B)]).reasons == (Reason.TAX_DIFF,)


def test_format_and_date_are_informational():
    r = one([inv("B1", no="inv-0042", inv_date=date(2025, 4, 7))], [inv("G1", GSTR2B)])
    assert r.category == Category.MATCHED
    assert r.reasons == (Reason.INV_NO_FORMAT, Reason.DATE_DIFF)


def test_itc_ineligible_wins():
    r = one([inv("B1")], [inv("G1", GSTR2B, itc_available=False)])
    assert r.category == Category.ITC_NOT_AVAILABLE and r.reasons == (Reason.ITC_INELIGIBLE,)


def test_missing_both_sides():
    rs = reconcile([inv("B1", no="1")], [inv("G1", GSTR2B, no="2"),
                                         inv("G2", GSTR2B, no="3", itc_available=False)])
    assert [(r.books_id, r.gstr2b_id, r.category) for r in rs] == [
        ("B1", None, Category.MISSING_IN_2B), (None, "G1", Category.MISSING_IN_BOOKS),
        (None, "G2", Category.ITC_NOT_AVAILABLE)]


def test_duplicate_keys_pair_once_each():
    b = [inv("B1"), inv("B2"), inv("B3")]
    g = [inv("G1", GSTR2B), inv("G2", GSTR2B)]
    rs = reconcile(b, g)
    assert sorted(r.gstr2b_id or "-" for r in rs) == ["-", "G1", "G2"]


def test_different_supplier_same_number_not_matched():
    other = replace(inv("G1", GSTR2B), supplier_gstin="29AAGCB7383J1Z4")
    assert len(reconcile([inv("B1")], [other])) == 2
