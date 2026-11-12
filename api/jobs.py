"""Reconciliation job. Runs in the rq worker, or in-process when REDIS_URL is unset."""
import logging
import time
import uuid
from collections import Counter
from datetime import UTC, datetime

from fastapi import BackgroundTasks
from sqlalchemy import select

from api import logs
from api.db import SessionLocal, engine
from api.settings import get_settings
from api.tables import Client, InvoiceRow, MatchResult, Run
from matcher.engine import reconcile
from matcher.models import BOOKS, GSTR2B, Invoice

MODEL_VERSION = "exact-v1"  # replaced by the MLflow model version in #11 / #23
QUEUE = "reconcile"


def enqueue(run_id: uuid.UUID, background: BackgroundTasks) -> None:
    url = get_settings().redis_url
    if url:
        from redis import Redis
        from rq import Queue

        Queue(QUEUE, connection=Redis.from_url(url)).enqueue(
            run_reconciliation, str(run_id), job_timeout=600)
    else:
        background.add_task(run_reconciliation, str(run_id))


def to_invoice(r: InvoiceRow) -> Invoice:
    return Invoice(id=r.ext_id, source=r.source, supplier_gstin=r.supplier_gstin,
                   supplier_name=r.supplier_name, inv_no_raw=r.inv_no_raw, inv_date=r.inv_date,
                   taxable=r.taxable, igst=r.igst, cgst=r.cgst, sgst=r.sgst, cess=r.cess,
                   itc_available=r.itc_available, reverse_charge=r.reverse_charge)


def run_reconciliation(run_id: str) -> None:
    if not logging.getLogger().handlers:
        logs.setup()  # in the rq worker process nothing else configures logging
    logs.run_id.set(run_id)
    started = time.perf_counter()
    engine()
    with SessionLocal() as db:
        run = db.get(Run, uuid.UUID(run_id))
        run.status, run.started_at = "running", datetime.now(UTC)
        db.commit()
        logs.log("run_started")
        try:
            rows = db.scalars(select(InvoiceRow).where(
                InvoiceRow.upload_id.in_([run.books_upload_id, run.gstr2b_upload_id]))).all()
            by_ext = {(r.source, r.ext_id): r.id for r in rows}
            books = [to_invoice(r) for r in rows if r.source == BOOKS]
            g2b = [to_invoice(r) for r in rows if r.source == GSTR2B]
            tolerance = db.get(Client, run.client_id).tolerance
            results = reconcile(books, g2b, tolerance)
            db.add_all(MatchResult(
                run_id=run.id, category=res.category.value, score=res.score,
                reason_codes=[r.value for r in res.reasons],
                books_invoice_id=by_ext.get((BOOKS, res.books_id)),
                gstr2b_invoice_id=by_ext.get((GSTR2B, res.gstr2b_id))) for res in results)
            counts = dict(Counter(res.category.value for res in results))
            run.summary = {"counts": counts, "books": len(books), "gstr2b": len(g2b)}
            run.status, run.model_version = "done", MODEL_VERSION
        except Exception as e:
            db.rollback()
            run = db.get(Run, uuid.UUID(run_id))
            run.status, run.error = "failed", type(e).__name__  # no message: may contain data
            counts = None
            logs.log("run_failed", logging.ERROR, exc_info=True, error_type=type(e).__name__)
        run.finished_at = datetime.now(UTC)
        db.commit()
    if counts is not None:
        logs.log("run_completed", duration_ms=round((time.perf_counter() - started) * 1000),
                 model_version=MODEL_VERSION, counts=counts,
                 invoices=len(books) + len(g2b))
