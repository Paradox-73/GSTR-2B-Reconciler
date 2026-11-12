from datetime import date
from decimal import Decimal as D

from matcher.models import BOOKS, GSTR2B, Invoice
from matcher.notes import NoteLine, inr, note


def inv(src, no, taxable="1000", igst="0", cgst="90", sgst="90"):
    return Invoice(f"{src}1", src, "27AAPFU0939F1ZV", "Shree", no, date(2025, 4, 5), D(taxable),
                   D(igst), D(cgst), D(sgst), D(0))


def test_inr_grouping():
    assert inr(D("1234567.5")) == "₹12,34,567.50"
    assert inr(D("999")) == "₹999.00"
    assert inr(D("100000")) == "₹1,00,000.00"
    assert inr(D("-12345")) == "-₹12,345.00"
    assert inr(D("0")) == "₹0.00"


def test_note_lists_missing_and_differing():
    text = note("Shree Traders", "2025-04", "Acme Pvt Ltd", "27ABCDE1234F1Z0", [
        NoteLine(("MISSING_IN_2B",), inv(BOOKS, "ST/1"), None),
        NoteLine(("VALUE_DIFF", "TAX_DIFF"), inv(BOOKS, "ST/2", "1000"),
                 inv(GSTR2B, "ST/2", "1100", cgst="99", sgst="99")),
        NoteLine(("DATE_DIFF",), inv(BOOKS, "ST/3"), inv(GSTR2B, "ST/3")),  # nothing to chase
    ])
    assert text.startswith("Dear Shree Traders,") and "April 2025" in text
    assert "ST/1 dated 05-04-2025" in text and "₹1,000.00" in text
    assert "ST/2" in text and "taxable ₹1,100.00" in text
    assert "ST/3" not in text and text.endswith("Acme Pvt Ltd")


def test_no_note_when_nothing_to_chase():
    assert note("X", "2025-04", "A", "G", [NoteLine(("DATE_DIFF",), inv(BOOKS, "1"),
                                                    inv(GSTR2B, "1"))]) is None


def test_deterministic():
    lines = [NoteLine(("MISSING_IN_2B",), inv(BOOKS, n), None) for n in ("B", "A")]
    assert note("X", "2025-04", "A", "G", lines) == note("X", "2025-04", "A", "G", lines[::-1])
