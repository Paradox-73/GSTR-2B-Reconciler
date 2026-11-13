"""Regression tests for the review findings in #54."""
import io
import json
import logging
import sys
import zipfile

import pytest

from api.logs import JsonFormatter

V1 = "/api/v1"
G = "27AAPFU0939F1ZV"
SUPPLIER = "29AAGCB7383J1Z4"
HEADER = "GSTIN,Name,Bill,Date,Taxable,IGST,CGST,SGST\n"
MAPPING = {"supplier_gstin": "GSTIN", "supplier_name": "Name", "invoice_no": "Bill",
           "invoice_date": "Date", "taxable": "Taxable", "igst": "IGST", "cgst": "CGST",
           "sgst": "SGST"}


@pytest.fixture(scope="module")
def cid(client, auth):
    r = client.post(f"{V1}/clients", json={"name": "Hardening", "gstin": G}, headers=auth)
    cid = r.json()["id"]
    client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": MAPPING}, headers=auth)
    return cid


def upload(client, auth, cid, kind, name, body, period="2025-04"):
    return client.post(f"{V1}/clients/{cid}/uploads", headers=auth,
                       data={"kind": kind, "period": period}, files={"file": (name, body)})


def test_logged_errors_carry_no_exception_message():
    message = "".join(["SEC", "RET SUPPLIER Rs ", "123456.78"])  # not in any source line
    try:
        raise ValueError(message)
    except ValueError:
        rec = logging.LogRecord("x", 40, __file__, 1, "boom", None, sys.exc_info())
    out = JsonFormatter().format(rec)
    assert "SECRET" not in out and "123456" not in out
    assert json.loads(out)["error_type"] == "ValueError"


def test_db_errors_hide_row_values(app):
    from api.db import engine

    assert engine().hide_parameters


@pytest.mark.parametrize("row,why", [
    (f"{SUPPLIER}XXXXXX,SECRETNAME,1,01-04-2025,100,0,9,9", "GSTIN"),
    (f"{SUPPLIER},X,1,01-04-2025,NaN,0,9,9", "amount"),
    (f"{SUPPLIER},X,1,01-04-2025,10000000000000,0,9,9", "amount"),
])
def test_bad_books_rows_are_422_not_500(client, auth, cid, row, why):
    r = upload(client, auth, cid, "books", "b.csv", (HEADER + row + "\n").encode())
    assert r.status_code == 422 and why in r.text
    assert "SECRETNAME" not in r.text


@pytest.mark.parametrize("name,body", [
    ("2b.json", b'{"data": []}'),
    ("2b.json", b'{"data": {"gstin": "' + G.encode() + b'", "rtnprd": 42}}'),
    ("2b.json", b"\xff\xfe not json"),
])
def test_malformed_2b_is_422(client, auth, cid, name, body):
    assert upload(client, auth, cid, "gstr2b", name, body).status_code == 422


def test_fake_xlsx_and_xls_are_422(client, auth, cid):
    assert upload(client, auth, cid, "books", "b.xlsx", b"not a zip").status_code == 422
    assert upload(client, auth, cid, "books", "b.xls", b"whatever").status_code == 422


def test_xlsx_zip_bomb_refused(client, auth, cid):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"0" * (101 * 1024 * 1024))
    assert len(buf.getvalue()) < 1024 * 1024  # small on the wire
    r = upload(client, auth, cid, "books", "b.xlsx", buf.getvalue())
    assert r.status_code == 422 and "too large" in r.text


def test_cp1252_csv_is_read(client, auth, cid):
    body = (HEADER + f"{SUPPLIER},Café Traders,1,01-04-2025,100,0,9,9\n").encode("cp1252")
    r = upload(client, auth, cid, "books", "b.csv", body)
    assert r.status_code == 201, r.text


def test_export_keeps_formulas_as_text_and_strips_control_chars(client, auth):
    from openpyxl import load_workbook

    from datagen.generate import generate

    ds = generate(seed=11, n_invoices=5, n_suppliers=2)
    r = client.post(f"{V1}/clients", json={"name": "Export", "gstin": ds.recipient_gstin},
                    headers=auth)
    cid = r.json()["id"]
    client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": MAPPING}, headers=auth)
    first = ds.gstr2b["data"]["docdata"]["b2b"][0]
    first["trdnm"] = '=HYPERLINK("http://evil","x")'
    inv = first["inv"][0]
    evil = f'{first["ctin"]},"=1+1\x0bCo",{inv["inum"]},{inv["dt"]},{inv["txval"]},0,0,0\n'
    assert upload(client, auth, cid, "gstr2b", "2b.json",
                  json.dumps(ds.gstr2b).encode()).status_code == 201
    assert upload(client, auth, cid, "books", "b.csv",
                  (HEADER + evil).encode()).status_code == 201
    run_id = client.post(f"{V1}/clients/{cid}/runs", json={"period": "2025-04"},
                         headers=auth).json()["id"]
    r = client.get(f"{V1}/runs/{run_id}/export", headers=auth)
    assert r.status_code == 200
    cells = [c for row in load_workbook(io.BytesIO(r.content))["Results"].iter_rows()
             for c in row if isinstance(c.value, str)]
    assert all(c.data_type != "f" for c in cells)
    assert any(c.value.startswith("=HYPERLINK") for c in cells)
    assert not any("\x0b" in c.value for c in cells)


def test_example_secrets_refused(monkeypatch):
    from api.settings import Settings

    monkeypatch.setenv("JWT_SECRET", "CHANGE_ME_TO_AT_LEAST_32_RANDOM_CHARACTERS")
    with pytest.raises(RuntimeError, match="example value"):
        Settings().check_api()


def test_export_summary_sheet_is_sanitised_too(client, auth):
    from openpyxl import load_workbook

    from datagen.generate import generate

    ds = generate(seed=12, n_invoices=5, n_suppliers=2)
    r = client.post(f"{V1}/clients", json={"name": "=1+1\x0bCo", "gstin": ds.recipient_gstin},
                    headers=auth)
    cid = r.json()["id"]
    client.put(f"{V1}/clients/{cid}/mapping", json={"mapping": MAPPING}, headers=auth)
    assert upload(client, auth, cid, "gstr2b", "2b.json",
                  json.dumps(ds.gstr2b).encode()).status_code == 201
    inv = ds.gstr2b["data"]["docdata"]["b2b"][0]
    row = f'{inv["ctin"]},X,{inv["inv"][0]["inum"]},{inv["inv"][0]["dt"]},1,0,0,0\n'
    assert upload(client, auth, cid, "books", "b.csv", (HEADER + row).encode()).status_code == 201
    run_id = client.post(f"{V1}/clients/{cid}/runs", json={"period": "2025-04"},
                         headers=auth).json()["id"]
    r = client.get(f"{V1}/runs/{run_id}/export", headers=auth)
    assert r.status_code == 200
    name = load_workbook(io.BytesIO(r.content))["Summary"]["B1"]
    assert name.value == "=1+1Co" and name.data_type == "s"
