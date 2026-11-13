"""Reconciliation job. Runs in the rq worker, or in-process when REDIS_URL is unset."""
import logging
import time
import uuid
from collections import Counter
from datetime import UTC, datetime

import xgboost as xgb
from fastapi import BackgroundTasks
from sqlalchemy import select

from api import logs
from api.db import SessionLocal, engine
from api.settings import env, get_settings
from api.tables import Client, InvoiceRow, MatchResult, Run
from matcher import config, registry
from matcher.engine import reconcile
from matcher.model import DEFAULT_PATH, MatchModel
from matcher.models import BOOKS, GSTR2B, Invoice

QUEUE = "reconcile"
EXACT_ONLY = "exact-only"


class ModelHolder:
    """The model workers score with. refresh() swaps in a new production model from MLflow;
    a reference swap is atomic, so a job in flight keeps the model it started with."""

    def __init__(self):
        self.model = None
        self.loaded = False
        self.registry_version = None
        self.bad_version = None  # a promoted version that failed to load: don't refetch it

    def get(self):
        # Never wait on MLflow here: a job uses the baked-in model until the poller swaps in
        # the registry one. MLflow being down must not stop reconciliations.
        if not self.loaded:
            self._load_bundled()
        return self.model

    def refresh(self) -> None:
        if registry.enabled():
            try:
                mv = registry.production_version()
                if mv is not None and mv.version not in (self.registry_version,
                                                         self.bad_version):
                    self.bad_version = mv.version  # cleared below once it loads
                    new = registry.load_version(mv)
                    self.bad_version = None
                    old = self.model.version if self.model else None
                    self.model, self.registry_version, self.loaded = new, mv.version, True
                    logs.log("model_swapped", from_version=old, model_version=new.version)
                    return
            except Exception:  # registry down: keep serving the model we have
                logs.log("model_refresh_failed", logging.WARNING, exc_info=True)
        if not self.loaded:
            self._load_bundled()

    def _load_bundled(self) -> None:
        path = env("MODEL_PATH") or DEFAULT_PATH
        try:
            self.model = MatchModel.load(path)
            logs.log("model_loaded", model_version=self.model.version, source="bundled")
        except (OSError, ValueError, xgb.core.XGBoostError):
            logs.log("model_missing", logging.WARNING, exc_info=True)
            self.model = None  # runs record model_version=exact-only, so this shows in the UI
        self.loaded = True


models = ModelHolder()


def get_model():
    return models.get()


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
            model, cfg = get_model(), config.load()
            version = model.version if model else EXACT_ONLY
            results = reconcile(books, g2b, tolerance, model, cfg["probable_threshold"],
                                cfg["review_threshold"], cfg["candidate_value_pct"],
                                cfg["candidate_date_days"])
            db.add_all(MatchResult(
                run_id=run.id, category=res.category.value, score=res.score,
                reason_codes=[r.value for r in res.reasons],
                books_invoice_id=by_ext.get((BOOKS, res.books_id)),
                gstr2b_invoice_id=by_ext.get((GSTR2B, res.gstr2b_id))) for res in results)
            counts = dict(Counter(res.category.value for res in results))
            run.summary = {"counts": counts, "books": len(books), "gstr2b": len(g2b)}
            run.status, run.model_version = "done", version
            run.finished_at = datetime.now(UTC)
            db.commit()  # inside the try: a failed results write must mark the run failed
        except Exception as e:
            db.rollback()
            run = db.get(Run, uuid.UUID(run_id))
            run.status, run.error = "failed", type(e).__name__  # no message: may contain data
            run.finished_at = datetime.now(UTC)
            counts, version = None, None
            logs.log("run_failed", logging.ERROR, exc_info=True, error_type=type(e).__name__)
            db.commit()
    if counts is not None:
        logs.log("run_completed", duration_ms=round((time.perf_counter() - started) * 1000),
                 model_version=version, counts=counts,
                 invoices=len(books) + len(g2b))


STUCK_AFTER_MINUTES = 15  # a 2000-invoice run takes ~1-2s, so this is very generous
QUEUED_LOST_AFTER_MINUTES = 120


def reap_stuck_runs(now: datetime | None = None) -> int:
    """Marks runs failed when their worker died mid-job, so the UI stops polling and the CA can
    start a new run. Safe to call from every worker: it's one conditional UPDATE."""
    from datetime import timedelta

    from sqlalchemy import or_, update

    now = now or datetime.now(UTC)
    started_cutoff = now - timedelta(minutes=STUCK_AFTER_MINUTES)
    # Queued runs get far longer: in a filing-week spike they wait behind others, they aren't lost
    queued_cutoff = now - timedelta(minutes=QUEUED_LOST_AFTER_MINUTES)
    engine()
    with SessionLocal() as db:
        n = db.execute(update(Run).where(or_(
            (Run.status == "running") & (Run.started_at < started_cutoff),
            (Run.status == "queued") & (Run.created_at < queued_cutoff)))
            .values(status="failed", error="WorkerLost", finished_at=datetime.now(UTC))).rowcount
        db.commit()
    if n:
        logs.log("runs_reaped", logging.WARNING, count=n)
    return n
