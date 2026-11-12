"""Labelled pairs from CA review decisions (DESIGN.md 9.1). The latest decision per result wins."""
import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.jobs import to_invoice
from api.tables import InvoiceRow, MatchResult, ReviewDecision
from matcher.models import BOOKS, Invoice


@dataclass(frozen=True)
class Label:
    decision_id: str
    books: Invoice
    gstr2b: Invoice
    same_invoice: bool
    decided_at: datetime

    @property
    def holdout(self) -> bool:
        """A stable 20% slice kept out of training to check the model on real decisions."""
        return int(hashlib.sha256(self.decision_id.encode()).hexdigest(), 16) % 5 == 0


def real_labels(db: Session) -> list[Label]:
    latest: dict = {}
    for d in db.scalars(select(ReviewDecision).order_by(ReviewDecision.decided_at)):
        latest[d.match_result_id] = d
    out = []
    for d in latest.values():
        m = db.get(MatchResult, d.match_result_id)
        if d.decision == "link":
            other = db.get(InvoiceRow, d.linked_invoice_id)
            own = m.books or m.gstr2b
            b, g = (own, other) if own.source == BOOKS else (other, own)
            same = True
        elif m.books and m.gstr2b:
            b, g, same = m.books, m.gstr2b, d.decision == "accept"
        else:
            continue  # accept/reject on a one-sided result says nothing about a pair
        out.append(Label(str(d.id), to_invoice(b), to_invoice(g), same, d.decided_at))
    return out
