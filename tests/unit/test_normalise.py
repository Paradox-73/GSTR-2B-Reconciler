from datetime import date, datetime
from decimal import Decimal

import pytest

from matcher.normalise import amount, invoice_no, numeric_part, to_date


@pytest.mark.parametrize("raw", ["INV/0042", "INV-42", "inv 42", " Inv_042 ", "INV/2025-26/42",
                                 "INV/42/25-26", "FY25-26/INV/0042"])
def test_invoice_variants_collide(raw):
    assert invoice_no(raw) == "INV42"


def test_fy_only_prefix():
    assert invoice_no("2025-26/42") == "42"
    assert invoice_no("2025-2026/0042") == "42"


def test_non_fy_number_pairs_kept():
    # 12-34 is not a financial year, so it stays part of the number
    assert invoice_no("A/12-34") == "A1234"
    assert invoice_no("2025-27/5") == "2025275"


def test_distinct_invoices_stay_distinct():
    assert invoice_no("INV-42") != invoice_no("INV-420")
    assert invoice_no("INV-1") != invoice_no("INV-10")


def test_numeric_part():
    assert numeric_part("INV/2025-26/0042") == "42"
    assert numeric_part("ABC") == ""
    assert numeric_part("INV-000") == "0"


def test_empty():
    assert invoice_no(None) == ""
    assert invoice_no("") == ""


@pytest.mark.parametrize("value", ["05-04-2025", "05/04/2025", "05.04.2025", "2025-04-05",
                                   "05-Apr-2025", "05 Apr 2025", "05-04-25", date(2025, 4, 5),
                                   datetime(2025, 4, 5, 10, 30), 45752])
def test_dates_day_first(value):
    assert to_date(value) == date(2025, 4, 5)


def test_bad_date():
    with pytest.raises(ValueError):
        to_date("31-31-2025")


@pytest.mark.parametrize("value,expected", [("1,23,456.50", "123456.50"), ("₹ 100", "100.00"),
                                            (None, "0.00"), ("", "0.00"), (float("nan"), "0.00"),
                                            (10.005, "10.01"), (7, "7.00"), ("2.345", "2.35")])
def test_amount(value, expected):
    assert amount(value) == Decimal(expected)


def test_bad_amount():
    with pytest.raises(ValueError):
        amount("abc")


def test_nan_date_is_an_error():
    with pytest.raises(ValueError):
        to_date(float("nan"))
