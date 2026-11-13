"""Candidate pairs among exact-pass leftovers (DESIGN.md 8.4). Keeps the model's work small.

Bounded on purpose: one supplier with thousands of unmatched invoices on both sides would
otherwise give millions of pairs and block the shared worker (#54). Filters use float totals and
day numbers: this only picks pairs for the model to score, it never decides amounts.
"""
import heapq
from bisect import bisect_left, bisect_right
from collections import defaultdict

from matcher.models import Invoice
from matcher.normalise import numeric_part

MAX_PER_INVOICE = 25  # far more than the handful of real lookalikes a books invoice has
SAME_SUPPLIER_DAYS = 45


def candidates(books: list[Invoice], g2b: list[Invoice], value_pct: float = 0.05,
               date_days: int = 10) -> list[tuple[Invoice, Invoice]]:
    # (total, day, digits, invoice) per 2B invoice, computed once
    rows = [(float(g.total), g.inv_date.toordinal(), numeric_part(g.inv_no_raw), g) for g in g2b]
    by_pan = defaultdict(list)  # same PAN includes same GSTIN
    for r in rows:
        by_pan[r[3].pan].append(r)
    by_total = sorted(rows, key=lambda r: r[0])
    totals = [r[0] for r in by_total]

    pairs = []
    for b in books:
        bt, bd, bdig = float(b.total), b.inv_date.toordinal(), numeric_part(b.inv_no_raw)
        found = {}
        # Same supplier, or same PAN (GSTIN typo / other-state registration): any invoice number,
        # as long as the date or the amount is in the neighbourhood
        for r in by_pan.get(b.pan, ()):
            if abs(bd - r[1]) <= SAME_SUPPLIER_DAYS or abs(bt - r[0]) <= value_pct * max(bt, r[0]):
                found[r[3].id] = r
        # Mangled number and GSTIN: amount within value_pct and date within date_days
        lo = bisect_left(totals, bt * (1 - value_pct))
        hi = bisect_right(totals, bt / (1 - value_pct)) if value_pct < 1 else len(totals)
        for r in by_total[lo:hi]:
            if abs(bd - r[1]) <= date_days and abs(bt - r[0]) <= value_pct * max(bt, r[0]):
                found[r[3].id] = r
        best = heapq.nsmallest(MAX_PER_INVOICE, found.values(), key=lambda r: (
            r[2] != bdig, abs(bd - r[1]), abs(bt - r[0]), r[3].id))
        pairs.extend((b, r[3]) for r in best)
    return pairs
