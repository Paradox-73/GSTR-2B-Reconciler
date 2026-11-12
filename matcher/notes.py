"""Vendor follow-up notes (DESIGN.md 8.9). Template-based, so the same input gives the same text."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from matcher.models import Invoice, Reason

CHASE_VALUES = {Reason.VALUE_DIFF, Reason.TAX_DIFF, Reason.TAX_HEAD_DIFF}


def inr(x: Decimal) -> str:
    """Indian digit grouping: 1234567.5 -> '₹12,34,567.50'."""
    sign = "-" if x < 0 else ""
    whole, frac = f"{abs(x):.2f}".split(".")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"{sign}₹{','.join([*groups, tail])}.{frac}"


@dataclass(frozen=True)
class NoteLine:
    reasons: tuple[str, ...]
    books: Invoice | None
    gstr2b: Invoice | None


def _when(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def note(supplier_name: str, period: str, client_name: str, client_gstin: str,
         lines: list[NoteLine]) -> str | None:
    """None when nothing needs chasing with this supplier."""
    missing = [ln.books for ln in lines if Reason.MISSING_IN_2B in ln.reasons and ln.books]
    differ = [ln for ln in lines if CHASE_VALUES & set(ln.reasons) and ln.books and ln.gstr2b]
    if not missing and not differ:
        return None
    month = date(int(period[:4]), int(period[5:]), 1).strftime("%B %Y")
    out = [f"Dear {supplier_name or 'Sir/Madam'},", "",
           f"While reconciling our GSTR-2B for {month} (GSTIN {client_gstin}), we found the "
           "following invoices from you that need your attention.", ""]
    if missing:
        out.append("Not showing in our GSTR-2B. Please check that these are filed in your "
                   "GSTR-1 against our GSTIN:")
        for b in sorted(missing, key=lambda i: (i.inv_date, i.inv_no_raw)):
            out.append(f"- Invoice {b.inv_no_raw} dated {_when(b.inv_date)}, taxable value "
                       f"{inr(b.taxable)}, tax {inr(b.total_tax)}")
        out.append("")
    if differ:
        out.append("Amounts in your GSTR-1 differ from the invoice we received. Please check and "
                   "amend if needed:")
        for ln in sorted(differ, key=lambda x: (x.books.inv_date, x.books.inv_no_raw)):
            b, g = ln.books, ln.gstr2b
            out.append(f"- Invoice {b.inv_no_raw} dated {_when(b.inv_date)}: as per invoice, "
                       f"taxable {inr(b.taxable)}, IGST {inr(b.igst)}, CGST {inr(b.cgst)}, SGST "
                       f"{inr(b.sgst)}; as per GSTR-2B, taxable {inr(g.taxable)}, IGST "
                       f"{inr(g.igst)}, CGST {inr(g.cgst)}, SGST {inr(g.sgst)}")
        out.append("")
    out += ["We can claim input tax credit only once these are correct in your return. "
            "Please let us know once done.", "", "Regards,", client_name]
    return "\n".join(out)
