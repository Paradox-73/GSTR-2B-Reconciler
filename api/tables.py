"""Database tables (DESIGN.md 10). Schema changes go through alembic (api/migrations)."""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db import Base

Money = Numeric(14, 2)


def _now():
    return datetime.now(UTC)


def _id():
    return mapped_column(primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _id()
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="staff")


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    gstin: Mapped[str] = mapped_column(String(15))
    column_mapping: Mapped[dict | None] = mapped_column(JSON)
    tolerance: Mapped[Decimal] = mapped_column(Money, default=Decimal("1.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[uuid.UUID] = _id()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    kind: Mapped[str] = mapped_column(String(10))  # gstr2b | books
    original_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    invoice_count: Mapped[int]
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InvoiceRow(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = _id()
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"), index=True)
    ext_id: Mapped[str] = mapped_column(String(20))  # B<row> / G<n> from the parser
    source: Mapped[str] = mapped_column(String(10))
    supplier_gstin: Mapped[str] = mapped_column(String(15))
    supplier_name: Mapped[str] = mapped_column(String(200))
    inv_no_raw: Mapped[str] = mapped_column(String(100))
    inv_no_norm: Mapped[str] = mapped_column(String(100))
    inv_date: Mapped[date] = mapped_column(Date)
    taxable: Mapped[Decimal] = mapped_column(Money)
    igst: Mapped[Decimal] = mapped_column(Money)
    cgst: Mapped[Decimal] = mapped_column(Money)
    sgst: Mapped[Decimal] = mapped_column(Money)
    cess: Mapped[Decimal] = mapped_column(Money)
    itc_available: Mapped[bool] = mapped_column(Boolean, default=True)
    reverse_charge: Mapped[bool] = mapped_column(Boolean, default=False)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[uuid.UUID] = _id()
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))
    books_upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"))
    gstr2b_upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"))
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued|running|done|failed
    model_version: Mapped[str | None] = mapped_column(String(50))
    summary: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (Index("ix_match_results_run_category", "run_id", "category"),)
    id: Mapped[uuid.UUID] = _id()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"))
    books_invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    gstr2b_invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    category: Mapped[str] = mapped_column(String(20))
    reason_codes: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float | None] = mapped_column(Float)
    books: Mapped[InvoiceRow | None] = relationship(foreign_keys=[books_invoice_id], lazy="joined")
    gstr2b: Mapped[InvoiceRow | None] = relationship(foreign_keys=[gstr2b_invoice_id],
                                                     lazy="joined")
    decisions: Mapped[list["ReviewDecision"]] = relationship(order_by="ReviewDecision.decided_at",
                                                             lazy="selectin")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[uuid.UUID] = _id()
    match_result_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("match_results.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(10))  # accept | reject | link
    linked_invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
