"""The invoice record every parser produces, so the engine doesn't care where data came from."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from matcher import gstin as gst
from matcher.normalise import invoice_no

BOOKS, GSTR2B = "books", "2b"


@dataclass(frozen=True)
class Invoice:
    id: str  # B<row> for books, G<n> for 2B, in file order; datagen truth refers to these
    source: str  # BOOKS or GSTR2B
    supplier_gstin: str
    supplier_name: str
    inv_no_raw: str
    inv_date: date
    taxable: Decimal
    igst: Decimal
    cgst: Decimal
    sgst: Decimal
    cess: Decimal
    itc_available: bool = True
    reverse_charge: bool = False

    @property
    def inv_no_norm(self) -> str:
        return invoice_no(self.inv_no_raw)

    @property
    def pan(self) -> str:
        return gst.pan(self.supplier_gstin)

    @property
    def total_tax(self) -> Decimal:
        return self.igst + self.cgst + self.sgst + self.cess

    @property
    def total(self) -> Decimal:
        return self.taxable + self.total_tax
