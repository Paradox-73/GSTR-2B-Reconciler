from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from matcher import gstin
from matcher.parsers import ParseError, load_books, load_gstr2b, parse_books, parse_gstr2b

FIX = "tests/fixtures/"
MAPPING = {"supplier_gstin": "GSTIN/UIN", "supplier_name": "Party Name", "invoice_no": "Bill No",
           "invoice_date": "Bill Date", "taxable": "Taxable Value", "igst": "IGST",
           "cgst": "CGST", "sgst": "SGST", "cess": "Cess"}


@pytest.mark.parametrize("name", ["gstr2b_items_format.json", "gstr2b_flat_format.json"])
def test_both_2b_shapes_give_same_invoices(name):
    invs = load_gstr2b(FIX + name)
    assert [i.id for i in invs] == ["G1", "G2", "G3"]
    first, _, third = invs
    assert first.supplier_gstin == "27PQRSX5678K1ZY" and gstin.is_valid(first.supplier_gstin)
    assert first.inv_no_raw == "ST/101/24-25" and first.inv_no_norm == "ST101"
    assert first.inv_date == date(2024, 8, 5)
    assert (first.taxable, first.cgst, first.sgst) == (Decimal("10000"), Decimal(900), Decimal(900))
    assert first.igst == 0  # key absent in the file
    assert third.igst == Decimal("9000") and third.reverse_charge
    assert third.total == Decimal("59000")


def test_items_are_summed():
    doc = {"data": {"gstin": "x", "docdata": {"b2b": [{"ctin": "27PQRSX5678K1ZY", "inv": [
        {"inum": "1", "dt": "01-04-2025", "items": [{"txval": 100, "igst": 18},
                                                     {"txval": 50.5, "igst": 2.52}]}]}]}}}
    (inv,) = parse_gstr2b(doc)
    assert inv.taxable == Decimal("150.50") and inv.igst == Decimal("20.52")


def test_gsp_double_wrap_and_missing_b2b():
    assert parse_gstr2b({"data": {"data": {"gstin": "x", "docdata": {}}}}) == []


def test_itc_flag():
    doc = {"data": {"gstin": "x", "docdata": {"b2b": [{"ctin": "27PQRSX5678K1ZY", "inv": [
        {"inum": "1", "dt": "01-04-2025", "itcavl": "N", "txval": 1}]}]}}}
    assert parse_gstr2b(doc)[0].itc_available is False


def test_not_a_2b_file():
    with pytest.raises(ParseError):
        parse_gstr2b({"hello": 1})


def test_bad_invoice_says_where():
    doc = {"data": {"gstin": "x", "docdata": {"b2b": [{"ctin": "27PQRSX5678K1ZY",
                                                        "inv": [{"inum": "X9", "dt": "nope"}]}]}}}
    with pytest.raises(ParseError, match="X9"):
        parse_gstr2b(doc)


def _books_df():
    return pd.DataFrame([
        {"GSTIN/UIN": "27pqrsx5678k1zy", "Party Name": "Shree", "Bill No": "ST-101",
         "Bill Date": "05/08/2024", "Taxable Value": "10,000.00", "IGST": "", "CGST": "900",
         "SGST": "900", "Cess": None},
        {k: None for k in MAPPING.values()},  # blank row is skipped
    ])


def test_books_roundtrip_csv_and_xlsx(tmp_path):
    df = _books_df()
    df.to_csv(tmp_path / "b.csv", index=False)
    df.to_excel(tmp_path / "b.xlsx", index=False)
    for f in ("b.csv", "b.xlsx"):
        (inv,) = load_books(tmp_path / f, MAPPING)
        assert inv.id == "B1" and inv.supplier_gstin == "27PQRSX5678K1ZY"
        assert inv.inv_no_norm == "ST101" and inv.inv_date == date(2024, 8, 5)
        assert inv.taxable == Decimal("10000.00") and inv.igst == 0 and inv.cess == 0


def test_cess_optional():
    m = {k: v for k, v in MAPPING.items() if k != "cess"}
    assert parse_books(_books_df(), m)[0].cess == 0


def test_mapping_errors_are_readable():
    with pytest.raises(ParseError, match="missing: invoice_no"):
        parse_books(_books_df(), {k: v for k, v in MAPPING.items() if k != "invoice_no"})
    with pytest.raises(ParseError, match="not found in file: Bill Number"):
        parse_books(_books_df(), {**MAPPING, "invoice_no": "Bill Number"})


def test_bad_row_reports_line():
    df = _books_df()
    df.loc[0, "Bill Date"] = "someday"
    with pytest.raises(ParseError, match="row 2"):
        parse_books(df, MAPPING)


def test_unsupported_file(tmp_path):
    with pytest.raises(ParseError):
        load_books(tmp_path / "x.pdf", MAPPING)
