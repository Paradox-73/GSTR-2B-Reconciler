"""/api/v1 endpoints (DESIGN.md 11)."""
import io
import json
import re
import uuid
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import pandas as pd
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import jobs, logs, storage
from api.db import get_db
from api.jobs import to_invoice
from api.security import create_token, current_user, verify_password
from api.settings import get_settings
from api.tables import Client, InvoiceRow, MatchResult, ReviewDecision, Run, Upload, User
from matcher import gstin as gst
from matcher.models import Category
from matcher.notes import NoteLine, note
from matcher.parsers import REQUIRED_COLUMNS, ParseError, parse_books, parse_gstr2b

router = APIRouter(prefix="/api/v1")
PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


# ---------- auth ----------

class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        logs.log("login_failed")
        raise HTTPException(401, "wrong email or password")
    logs.log("login_ok", user_id=str(user.id))
    return {"access_token": create_token(user), "token_type": "bearer"}


# ---------- clients ----------

class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    gstin: str
    tolerance: Decimal = Field(default=Decimal("1.00"), ge=0, le=1000)

    @field_validator("gstin")
    @classmethod
    def valid_gstin(cls, v: str) -> str:
        if not gst.is_valid(v):
            raise ValueError("not a valid GSTIN (format or check character is wrong)")
        return gst.clean(v)


def client_out(c: Client) -> dict:
    return {"id": c.id, "name": c.name, "gstin": c.gstin, "tolerance": c.tolerance,
            "column_mapping": c.column_mapping}


def own_client(client_id: uuid.UUID, user: User, db: Session) -> Client:
    c = db.get(Client, client_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(404, "client not found")
    return c


@router.get("/clients")
def list_clients(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Client).where(Client.user_id == user.id).order_by(Client.name))
    return [client_out(c) for c in rows]


@router.get("/clients/{client_id}")
def get_client(client_id: uuid.UUID, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    return client_out(own_client(client_id, user, db))


@router.get("/clients/{client_id}/uploads")
def list_uploads(client_id: uuid.UUID, period: str | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_client(client_id, user, db)
    q = select(Upload).where(Upload.client_id == client_id)
    if period:
        q = q.where(Upload.period == period)
    return [{"id": u.id, "kind": u.kind, "period": u.period, "original_name": u.original_name,
             "invoice_count": u.invoice_count, "uploaded_at": u.uploaded_at}
            for u in db.scalars(q.order_by(Upload.uploaded_at.desc()))]


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    c = Client(user_id=user.id, name=body.name.strip(), gstin=body.gstin,
               tolerance=body.tolerance)
    db.add(c)
    db.commit()
    logs.log("client_created", client_id=str(c.id))
    return client_out(c)


class MappingIn(BaseModel):
    mapping: dict[str, str]

    @field_validator("mapping")
    @classmethod
    def has_required(cls, v: dict[str, str]) -> dict[str, str]:
        missing = [c for c in REQUIRED_COLUMNS if not v.get(c)]
        if missing:
            raise ValueError(f"mapping is missing: {', '.join(missing)}")
        return v


@router.put("/clients/{client_id}/mapping")
def save_mapping(client_id: uuid.UUID, body: MappingIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    c = own_client(client_id, user, db)
    c.column_mapping = body.mapping
    db.commit()
    return client_out(c)


# ---------- uploads ----------

@router.post("/clients/{client_id}/uploads", status_code=201)
async def upload(client_id: uuid.UUID, kind: str = Form(pattern="^(gstr2b|books)$"),
                 period: str = Form(), file: UploadFile = File(),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_client(client_id, user, db)
    if not PERIOD.match(period):
        raise HTTPException(422, "period must look like 2025-04")
    data = await file.read()
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "file too large")
    suffix = Path(file.filename or "").suffix.lower()

    try:
        if kind == "gstr2b":
            invoices = _parse_2b(data, c, period)
        else:
            invoices = _parse_books(data, suffix, c)
    except ParseError as e:
        raise HTTPException(422, str(e)) from e

    try:
        path, sha = storage.save(c.id, data, suffix)
    except OSError as e:  # Vault unreachable: refuse rather than write plaintext to disk
        logs.log("upload_store_failed", 40, error_type=type(e).__name__)
        raise HTTPException(503, "file storage is unavailable, try again shortly") from e
    up = Upload(client_id=c.id, period=period, kind=kind, original_name=file.filename or "",
                file_path=path, sha256=sha, invoice_count=len(invoices))
    db.add(up)
    db.flush()
    db.add_all(InvoiceRow(upload_id=up.id, ext_id=i.id, source=i.source,
                          supplier_gstin=i.supplier_gstin, supplier_name=i.supplier_name[:200],
                          inv_no_raw=i.inv_no_raw[:100], inv_no_norm=i.inv_no_norm[:100],
                          inv_date=i.inv_date, taxable=i.taxable, igst=i.igst, cgst=i.cgst,
                          sgst=i.sgst, cess=i.cess, itc_available=i.itc_available,
                          reverse_charge=i.reverse_charge) for i in invoices)
    db.commit()
    logs.log("upload_saved", client_id=str(c.id), upload_id=str(up.id), kind=kind,
             invoices=len(invoices))
    return {"id": up.id, "kind": kind, "period": period, "invoice_count": len(invoices),
            "sha256": sha}


def _parse_2b(data: bytes, c: Client, period: str):
    try:
        doc = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ParseError("GSTR-2B file is not valid JSON") from e
    root = doc.get("data", {}) if isinstance(doc, dict) else {}
    root = root.get("data", root) if "gstin" not in root else root
    if root.get("gstin") and gst.clean(root["gstin"]) != c.gstin:
        raise ParseError(f"this GSTR-2B is for {root['gstin']}, not this client ({c.gstin})")
    rtnprd = root.get("rtnprd")
    if rtnprd and f"{rtnprd[2:]}-{rtnprd[:2]}" != period:
        raise ParseError(f"this GSTR-2B is for period {rtnprd[:2]}/{rtnprd[2:]}, not {period}")
    return parse_gstr2b(doc)


def _parse_books(data: bytes, suffix: str, c: Client):
    if suffix not in (".csv", ".xlsx", ".xls"):
        raise ParseError("purchase register must be .xlsx or .csv")
    df = (pd.read_csv(io.BytesIO(data), dtype=object, keep_default_na=False) if suffix == ".csv"
          else pd.read_excel(io.BytesIO(data), dtype=object))
    columns = [str(x) for x in df.columns]
    # 409 + the file's headers = the UI shows the mapping screen, then uploads again
    if not c.column_mapping:
        raise HTTPException(409, {"message": "save a column mapping for this client first",
                                  "columns": columns})
    absent = [h for h in c.column_mapping.values() if h not in df.columns]
    if absent:
        raise HTTPException(409, {"message": "this file's columns don't match the saved mapping "
                                             f"(missing: {', '.join(absent)})",
                                  "columns": columns})
    return parse_books(df, c.column_mapping)


# ---------- runs ----------

class RunIn(BaseModel):
    period: str = Field(pattern=PERIOD.pattern)


def run_out(r: Run) -> dict:
    return {"id": r.id, "client_id": r.client_id, "period": r.period, "status": r.status,
            "model_version": r.model_version, "summary": r.summary, "error": r.error,
            "created_at": r.created_at, "started_at": r.started_at,
            "finished_at": r.finished_at}


@router.post("/clients/{client_id}/runs", status_code=202)
def start_run(client_id: uuid.UUID, body: RunIn, background: BackgroundTasks,
              user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = own_client(client_id, user, db)
    latest = {}
    for kind in ("books", "gstr2b"):
        latest[kind] = db.scalar(select(Upload).where(
            Upload.client_id == c.id, Upload.period == body.period, Upload.kind == kind)
            .order_by(Upload.uploaded_at.desc()).limit(1))
    missing = [k for k, v in latest.items() if v is None]
    if missing:
        raise HTTPException(409, f"upload {' and '.join(missing)} for {body.period} first")
    run = Run(client_id=c.id, period=body.period, books_upload_id=latest["books"].id,
              gstr2b_upload_id=latest["gstr2b"].id)
    db.add(run)
    db.commit()
    logs.log("run_queued", run_id=str(run.id), client_id=str(c.id))
    jobs.enqueue(run.id, background)
    return run_out(run)


def own_run(run_id: uuid.UUID, user: User, db: Session) -> Run:
    r = db.get(Run, run_id)
    if r is None:
        raise HTTPException(404, "run not found")
    own_client(r.client_id, user, db)
    return r


@router.get("/clients/{client_id}/runs")
def list_runs(client_id: uuid.UUID, user: User = Depends(current_user),
              db: Session = Depends(get_db)):
    own_client(client_id, user, db)
    rows = db.scalars(select(Run).where(Run.client_id == client_id)
                      .order_by(Run.created_at.desc()))
    return [run_out(r) for r in rows]


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    return run_out(own_run(run_id, user, db))


def invoice_out(i: InvoiceRow | None) -> dict | None:
    if i is None:
        return None
    return {"id": i.id, "supplier_gstin": i.supplier_gstin, "supplier_name": i.supplier_name,
            "invoice_no": i.inv_no_raw, "invoice_date": i.inv_date, "taxable": i.taxable,
            "igst": i.igst, "cgst": i.cgst, "sgst": i.sgst, "cess": i.cess,
            "itc_available": i.itc_available}


def result_out(m: MatchResult) -> dict:
    last = m.decisions[-1] if m.decisions else None
    return {"id": m.id, "category": m.category, "reason_codes": m.reason_codes,
            "score": m.score, "books": invoice_out(m.books), "gstr2b": invoice_out(m.gstr2b),
            "decision": last and {"decision": last.decision, "decided_at": last.decided_at,
                                  "linked_invoice_id": last.linked_invoice_id}}


@router.get("/runs/{run_id}/results")
def get_results(run_id: uuid.UUID, category: Category | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    own_run(run_id, user, db)
    q = select(MatchResult).where(MatchResult.run_id == run_id)
    if category:
        q = q.where(MatchResult.category == category.value)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(MatchResult.category, MatchResult.id)
                      .offset((page - 1) * page_size).limit(page_size)).unique()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [result_out(m) for m in rows]}


# ---------- review decisions ----------

class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(accept|reject|link)$")
    linked_invoice_id: uuid.UUID | None = None  # for "link": the invoice on the other side


@router.post("/results/{result_id}/decision", status_code=201)
def decide(result_id: uuid.UUID, body: DecisionIn, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    m = db.get(MatchResult, result_id)
    if m is None:
        raise HTTPException(404, "result not found")
    run = own_run(m.run_id, user, db)
    if body.decision == "link":
        other = body.linked_invoice_id and db.get(InvoiceRow, body.linked_invoice_id)
        mine = m.books or m.gstr2b
        allowed = {run.books_upload_id, run.gstr2b_upload_id}
        if not other or other.upload_id not in allowed or other.source == mine.source:
            raise HTTPException(422, "link needs an invoice from the other side of this run")
    elif body.linked_invoice_id:
        raise HTTPException(422, "linked_invoice_id only goes with decision=link")
    d = ReviewDecision(match_result_id=m.id, user_id=user.id, decision=body.decision,
                       linked_invoice_id=body.linked_invoice_id)
    db.add(d)
    db.commit()
    logs.log("review_decision", run_id=str(run.id), result_id=str(m.id),
             decision=body.decision, category=m.category)
    return {"id": d.id, "decision": d.decision}


# ---------- vendor notes + export ----------

def _run_results(run: Run, db: Session) -> list[MatchResult]:
    return list(db.scalars(select(MatchResult).where(MatchResult.run_id == run.id)
                           .order_by(MatchResult.category, MatchResult.id)).unique())


@router.get("/runs/{run_id}/vendor-notes")
def vendor_notes(run_id: uuid.UUID, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    run = own_run(run_id, user, db)
    client = db.get(Client, run.client_id)
    by_supplier: dict[str, list[NoteLine]] = defaultdict(list)
    names: dict[str, str] = {}
    for m in _run_results(run, db):
        side = m.gstr2b or m.books
        gstin = (m.books or m.gstr2b).supplier_gstin  # books GSTIN: that's who the CA writes to
        names.setdefault(gstin, side.supplier_name)
        by_supplier[gstin].append(NoteLine(tuple(m.reason_codes),
                                           m.books and to_invoice(m.books),
                                           m.gstr2b and to_invoice(m.gstr2b)))
    out = []
    for gstin in sorted(by_supplier):
        body = note(names[gstin], run.period, client.name, client.gstin, by_supplier[gstin])
        if body:
            out.append({"supplier_gstin": gstin, "supplier_name": names[gstin], "body": body})
    return out


EXPORT_COLUMNS = ["Category", "Reasons", "Score", "Decision",
                  "Books GSTIN", "Books supplier", "Books invoice no", "Books date",
                  "Books taxable", "Books IGST", "Books CGST", "Books SGST", "Books cess",
                  "2B GSTIN", "2B supplier", "2B invoice no", "2B date", "2B taxable", "2B IGST",
                  "2B CGST", "2B SGST", "2B cess", "2B ITC available"]


def _side(i: InvoiceRow | None) -> list:
    if i is None:
        return [None] * 9
    return [i.supplier_gstin, i.supplier_name, i.inv_no_raw, i.inv_date, float(i.taxable),
            float(i.igst), float(i.cgst), float(i.sgst), float(i.cess)]


@router.get("/runs/{run_id}/export")
def export(run_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    run = own_run(run_id, user, db)
    client = db.get(Client, run.client_id)
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Client", client.name])
    summary.append(["GSTIN", client.gstin])
    summary.append(["Period", run.period])
    summary.append(["Model version", run.model_version])
    summary.append([])
    summary.append(["Category", "Count"])
    for cat, n in sorted(((run.summary or {}).get("counts") or {}).items()):
        summary.append([cat, n])
    sheet = wb.create_sheet("Results")
    sheet.append(EXPORT_COLUMNS)
    for m in _run_results(run, db):
        last = m.decisions[-1].decision if m.decisions else None
        itc = m.gstr2b.itc_available if m.gstr2b else None
        sheet.append([m.category, ", ".join(m.reason_codes), m.score, last,
                      *_side(m.books), *_side(m.gstr2b), itc])
    sheet.auto_filter.ref = sheet.dimensions
    sheet.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    logs.log("export", run_id=str(run.id))
    name = f"reconciliation-{client.gstin}-{run.period}.xlsx"
    return Response(buf.getvalue(),
                    headers={"Content-Disposition": f'attachment; filename="{name}"'},
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
