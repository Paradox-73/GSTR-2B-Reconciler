"""Parsers for the two inputs. Field names and quirks: docs/gstr2b-schema.md."""
import json
from pathlib import Path

import pandas as pd

from matcher import gstin as gst
from matcher.models import BOOKS, GSTR2B, Invoice
from matcher.normalise import amount, to_date

AMOUNT_KEYS = ("txval", "igst", "cgst", "sgst", "cess")

# Logical columns the purchase register must map to (DESIGN.md 7.2). Cess is optional.
REQUIRED_COLUMNS = ("supplier_gstin", "supplier_name", "invoice_no", "invoice_date", "taxable",
                    "igst", "cgst", "sgst")
OPTIONAL_COLUMNS = ("cess",)


class ParseError(ValueError):
    pass


def _gstin(raw) -> str:
    """Cleaned but not checksum-validated: a typo'd GSTIN is a case the matcher handles."""
    g = gst.clean(str(raw or ""))
    if len(g) != 15:
        raise ValueError("supplier GSTIN must be 15 characters")
    return g


def _unwrap(doc: dict) -> dict:
    root = doc.get("data", doc)
    # GSP APIs wrap the portal file in one more "data"
    if "gstin" not in root and isinstance(root.get("data"), dict):
        root = root["data"]
    if "docdata" not in root and "gstin" not in root:
        raise ParseError("not a GSTR-2B file: no data.gstin / data.docdata")
    return root


def _invoice_amounts(inv: dict) -> dict:
    # Up to Sep-2024 amounts are in items[]; from Oct-2024 they sit on the invoice. Missing = 0.
    lines = inv["items"] if "items" in inv else [inv]
    return {k: sum((amount(line.get(k)) for line in lines), amount(0)) for k in AMOUNT_KEYS}


def parse_gstr2b(doc: dict) -> list[Invoice]:
    root = _unwrap(doc)
    out = []
    for supplier in root.get("docdata", {}).get("b2b", []):
        for inv in supplier.get("inv", []):
            try:
                a = _invoice_amounts(inv)
                out.append(Invoice(
                    id=f"G{len(out) + 1}",
                    source=GSTR2B,
                    supplier_gstin=_gstin(supplier["ctin"]),
                    supplier_name=supplier.get("trdnm", ""),
                    inv_no_raw=str(inv["inum"]),
                    inv_date=to_date(inv["dt"]),
                    taxable=a["txval"], igst=a["igst"], cgst=a["cgst"], sgst=a["sgst"],
                    cess=a["cess"],
                    itc_available=inv.get("itcavl", "Y") != "N",
                    reverse_charge=inv.get("rev", "N") == "Y",
                ))
            except (KeyError, ValueError) as e:
                raise ParseError(f"2B supplier {supplier.get('ctin')} invoice "
                                 f"{inv.get('inum')}: {e}") from e
    return out


def load_gstr2b(path: str | Path) -> list[Invoice]:
    with open(path, encoding="utf-8") as f:
        return parse_gstr2b(json.load(f))


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path, dtype=object)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=object, keep_default_na=False)
    raise ParseError(f"purchase register must be .xlsx or .csv, got {path.suffix}")


def parse_books(df: pd.DataFrame, mapping: dict[str, str]) -> list[Invoice]:
    """mapping: logical column -> the client's column header, e.g. {"invoice_no": "Bill No"}."""
    missing = [c for c in REQUIRED_COLUMNS if c not in mapping]
    if missing:
        raise ParseError(f"column mapping is missing: {', '.join(missing)}")
    absent = [h for h in mapping.values() if h not in df.columns]
    if absent:
        raise ParseError(f"columns not found in file: {', '.join(absent)}. "
                         f"File has: {', '.join(map(str, df.columns))}")

    def col(row, name):
        return row[mapping[name]] if name in mapping else None

    out = []
    for i, row in enumerate(df.to_dict("records"), start=1):
        if all(pd.isna(v) or str(v).strip() == "" for v in row.values()):
            continue  # blank trailing rows are common in exported registers
        try:
            out.append(Invoice(
                id=f"B{i}",
                source=BOOKS,
                supplier_gstin=_gstin(col(row, "supplier_gstin")),
                supplier_name=str(col(row, "supplier_name") or ""),
                inv_no_raw=str(col(row, "invoice_no")),
                inv_date=to_date(col(row, "invoice_date")),
                taxable=amount(col(row, "taxable")), igst=amount(col(row, "igst")),
                cgst=amount(col(row, "cgst")), sgst=amount(col(row, "sgst")),
                cess=amount(col(row, "cess")),
            ))
        except ValueError as e:
            raise ParseError(f"purchase register row {i + 1}: {e}") from e  # +1 for header row
    return out


def load_books(path: str | Path, mapping: dict[str, str]) -> list[Invoice]:
    return parse_books(read_table(path), mapping)
