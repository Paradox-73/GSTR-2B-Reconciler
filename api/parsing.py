"""Upload parsing, run in a separate process.

pandas/openpyxl parsing is pure CPU and holds the GIL, so in a thread it still stalled every other
request (and the health probes) for seconds on a big xlsx. In a child process it can't.
Results come back as plain tuples because exceptions like HTTPException don't cross processes.
"""
import io
import json
import zipfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool

import pandas as pd

from matcher import gstin as gst
from matcher.parsers import ParseError, parse_books, parse_gstr2b

MAX_ROWS = 50_000
MAX_XLSX_UNZIPPED = 100 * 1024 * 1024
TIMEOUT_SECONDS = 120
# Anything pandas/openpyxl/json raise on a malformed file is the user's file, not our bug
UNREADABLE = (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError,
              zipfile.BadZipFile, UnicodeDecodeError, pd.errors.ParserError)

_pool: ProcessPoolExecutor | None = None


def parse(kind: str, data: bytes, suffix: str, client_gstin: str, mapping: dict | None,
          period: str):
    """Returns ("ok", invoices) | ("mapping", message, columns) | ("error", message)."""
    try:
        if kind == "gstr2b":
            invoices = _parse_2b(data, client_gstin, period)
        else:
            out = _parse_books(data, suffix, mapping)
            if out[0] == "mapping":
                return out
            invoices = out[1]
    except ParseError as e:
        return ("error", str(e))
    except UNREADABLE:
        return ("error", f"couldn't read this file as a {kind} file")
    if len(invoices) > MAX_ROWS:
        return ("error", f"too many invoices in one file (max {MAX_ROWS})")
    return ("ok", invoices)


def parse_in_child(*args):
    """parse() in the pool. Raises TimeoutError or RuntimeError if the child dies or hangs."""
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=2)
    future = _pool.submit(parse, *args)
    try:
        return future.result(timeout=TIMEOUT_SECONDS)
    except (FutureTimeout, BrokenProcessPool) as e:
        # A hung or crashed child (e.g. out of memory) poisons the pool: kill it, start fresh
        for p in list(getattr(_pool, "_processes", {}).values()):
            p.terminate()
        _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
        raise RuntimeError("parser process failed") from e


def _parse_2b(data: bytes, client_gstin: str, period: str):
    try:
        doc = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ParseError("GSTR-2B file is not valid JSON") from e
    root = doc.get("data", {}) if isinstance(doc, dict) else {}
    if not isinstance(root, dict):
        raise ParseError("not a GSTR-2B file")
    root = root.get("data", root) if "gstin" not in root else root
    if root.get("gstin") and gst.clean(str(root["gstin"])) != client_gstin:
        raise ParseError(f"this GSTR-2B is for {root['gstin']}, not this client ({client_gstin})")
    rtnprd = str(root.get("rtnprd") or "")
    if rtnprd and f"{rtnprd[2:]}-{rtnprd[:2]}" != period:
        raise ParseError(f"this GSTR-2B is for period {rtnprd[:2]}/{rtnprd[2:]}, not {period}")
    return parse_gstr2b(doc)


def _parse_books(data: bytes, suffix: str, mapping: dict | None):
    if suffix not in (".csv", ".xlsx"):
        raise ParseError("purchase register must be .xlsx or .csv")
    if suffix == ".csv":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")  # Excel/Tally exports on Windows
        df = pd.read_csv(io.StringIO(text), dtype=object, keep_default_na=False,
                         nrows=MAX_ROWS + 1)
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as z:  # xlsx is a zip: refuse zip bombs
            if sum(i.file_size for i in z.infolist()) > MAX_XLSX_UNZIPPED:
                raise ParseError("this spreadsheet is too large once unzipped")
        df = pd.read_excel(io.BytesIO(data), dtype=object, nrows=MAX_ROWS + 1)
    if len(df) > MAX_ROWS:
        raise ParseError(f"too many rows in one file (max {MAX_ROWS})")
    columns = [str(x) for x in df.columns]
    # The UI shows the mapping screen with these headers, then uploads again
    if not mapping:
        return ("mapping", "save a column mapping for this client first", columns)
    absent = [h for h in mapping.values() if h not in df.columns]
    if absent:
        return ("mapping", "this file's columns don't match the saved mapping "
                           f"(missing: {', '.join(absent)})", columns)
    return ("ok", parse_books(df, mapping))
