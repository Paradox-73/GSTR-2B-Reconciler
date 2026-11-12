"""Reconciliation engine: exact pass, then categorise (DESIGN.md 8.3, 8.7, 8.8)."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from matcher.models import Category, Invoice, Reason

HEADS = ("igst", "cgst", "sgst", "cess")


@dataclass(frozen=True)
class Result:
    books_id: str | None
    gstr2b_id: str | None
    category: Category
    reasons: tuple[Reason, ...] = ()
    score: float | None = None  # model probability; None for exact-pass results


def compare(b: Invoice, g: Invoice, tolerance: Decimal) -> tuple[Reason, ...]:
    """Reason codes for a books/2B pair that are believed to be the same invoice."""
    reasons = []
    if b.inv_no_raw.strip() != g.inv_no_raw.strip():
        reasons.append(Reason.INV_NO_FORMAT)
    if b.supplier_gstin != g.supplier_gstin:
        reasons.append(Reason.GSTIN_TYPO)
    if b.inv_date != g.inv_date:
        reasons.append(Reason.DATE_DIFF)
    if abs(b.taxable - g.taxable) > tolerance:
        reasons.append(Reason.VALUE_DIFF)
    if abs(b.total_tax - g.total_tax) > tolerance:
        reasons.append(Reason.TAX_DIFF)
    elif any(abs(getattr(b, h) - getattr(g, h)) > tolerance for h in HEADS):
        reasons.append(Reason.TAX_HEAD_DIFF)  # same total tax, split differently
    return tuple(reasons)


AMOUNT_REASONS = {Reason.VALUE_DIFF, Reason.TAX_DIFF, Reason.TAX_HEAD_DIFF}


def categorise(b: Invoice, g: Invoice, tolerance: Decimal, matched_as=Category.MATCHED,
               score: float | None = None) -> Result:
    reasons = compare(b, g, tolerance)
    if not g.itc_available:
        category, reasons = Category.ITC_NOT_AVAILABLE, (*reasons, Reason.ITC_INELIGIBLE)
    elif AMOUNT_REASONS & set(reasons):
        category = Category.MISMATCH
    else:
        category = matched_as
    return Result(b.id, g.id, category, reasons, score)


def exact_pass(books: list[Invoice], g2b: list[Invoice], tolerance: Decimal):
    """Pairs on (supplier GSTIN, normalised invoice no). Returns results + unpaired leftovers."""
    by_key = defaultdict(list)
    for g in g2b:
        by_key[(g.supplier_gstin, g.inv_no_norm)].append(g)
    results, left_books = [], []
    for b in books:
        candidates = by_key.get((b.supplier_gstin, b.inv_no_norm))
        if candidates:
            results.append(categorise(b, candidates.pop(0), tolerance))
        else:
            left_books.append(b)
    paired = {r.gstr2b_id for r in results}
    return results, left_books, [g for g in g2b if g.id not in paired]


def unmatched(left_books: list[Invoice], left_g2b: list[Invoice]) -> list[Result]:
    out = [Result(b.id, None, Category.MISSING_IN_2B, (Reason.MISSING_IN_2B,)) for b in left_books]
    for g in left_g2b:
        if g.itc_available:
            out.append(Result(None, g.id, Category.MISSING_IN_BOOKS, (Reason.MISSING_IN_BOOKS,)))
        else:  # no ITC to claim anyway, so the CA has nothing to chase
            out.append(Result(None, g.id, Category.ITC_NOT_AVAILABLE,
                              (Reason.MISSING_IN_BOOKS, Reason.ITC_INELIGIBLE)))
    return out


def reconcile(books: list[Invoice], g2b: list[Invoice], tolerance=Decimal("1.00")) -> list[Result]:
    results, left_books, left_g2b = exact_pass(books, g2b, Decimal(str(tolerance)))
    # ML pass on the leftovers goes here (#10, #11)
    return results + unmatched(left_books, left_g2b)
