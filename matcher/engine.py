"""Reconciliation engine: exact pass, then categorise (DESIGN.md 8.3, 8.7, 8.8)."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from matcher.candidates import candidates
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


def categorise(b: Invoice, g: Invoice, tolerance: Decimal, model_category: Category | None = None,
               score: float | None = None) -> Result:
    """model_category is set for pairs the model found: they stay probable/review even with
    amount differences, because the CA still has to confirm it's the same invoice first."""
    reasons = compare(b, g, tolerance)
    if not g.itc_available:
        category, reasons = Category.ITC_NOT_AVAILABLE, (*reasons, Reason.ITC_INELIGIBLE)
    elif model_category:
        category = model_category
    elif AMOUNT_REASONS & set(reasons):
        category = Category.MISMATCH
    else:
        category = Category.MATCHED
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


def model_pass(books: list[Invoice], g2b: list[Invoice], model, tolerance: Decimal,
               probable: float, review: float, value_pct: float, date_days: int):
    """Scores candidate pairs, then assigns one-to-one by highest probability (DESIGN.md 8.6)."""
    pairs = candidates(books, g2b, value_pct, date_days)
    scored = sorted(zip(model.score(pairs), range(len(pairs)), pairs, strict=True), reverse=True)
    used_b, used_g, results = set(), set(), []
    for score, _, (b, g) in scored:
        if score < review:
            break
        if b.id in used_b or g.id in used_g:
            continue
        used_b.add(b.id)
        used_g.add(g.id)
        category = Category.PROBABLE if score >= probable else Category.REVIEW
        results.append(categorise(b, g, tolerance, category, round(score, 4)))
    return (results, [b for b in books if b.id not in used_b],
            [g for g in g2b if g.id not in used_g])


def reconcile(books: list[Invoice], g2b: list[Invoice], tolerance=Decimal("1.00"), model=None,
              probable: float = 0.90, review: float = 0.50, value_pct: float = 0.05,
              date_days: int = 10) -> list[Result]:
    """model=None runs the exact pass only."""
    tolerance = Decimal(str(tolerance))
    results, left_books, left_g2b = exact_pass(books, g2b, tolerance)
    if model is not None:
        found, left_books, left_g2b = model_pass(left_books, left_g2b, model, tolerance,
                                                 probable, review, value_pct, date_days)
        results += found
    return results + unmatched(left_books, left_g2b)
