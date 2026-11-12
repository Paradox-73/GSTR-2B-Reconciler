"""Candidate pairs among exact-pass leftovers (DESIGN.md 8.4). Keeps the model's work small."""
from collections import defaultdict
from decimal import Decimal

from matcher.models import Invoice


def candidates(books: list[Invoice], g2b: list[Invoice], value_pct: float = 0.05,
               date_days: int = 10) -> list[tuple[Invoice, Invoice]]:
    pct = Decimal(str(value_pct))
    by_gstin, by_pan = defaultdict(list), defaultdict(list)
    for g in g2b:
        by_gstin[g.supplier_gstin].append(g)
        by_pan[g.pan].append(g)

    pairs, seen = [], set()

    def add(b, g):
        if (b.id, g.id) not in seen:
            seen.add((b.id, g.id))
            pairs.append((b, g))

    for b in books:
        for g in by_gstin.get(b.supplier_gstin, ()):  # same supplier, any invoice number
            add(b, g)
        for g in by_pan.get(b.pan, ()):  # GSTIN typo or other-state registration
            add(b, g)
        for g in g2b:  # mangled number and GSTIN: fall back to value + date
            close_value = abs(b.total - g.total) <= pct * max(b.total, g.total)
            if close_value and abs((b.inv_date - g.inv_date).days) <= date_days:
                add(b, g)
    return pairs
