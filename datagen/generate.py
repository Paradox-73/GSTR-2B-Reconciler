"""Synthetic books + GSTR-2B pairs with planted errors and known answers (DESIGN.md 7.3).

Each invoice gets at most one planted error, so its expected category is unambiguous.
"""
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from matcher import gstin as gst
from matcher.models import Category as C
from matcher.models import Reason as R

RECIPIENT_STATE = "27"
BOOKS_COLUMNS = ["Date", "Particulars", "GSTIN/UIN", "Bill No", "Taxable Value", "IGST", "CGST",
                 "SGST", "Cess"]
BOOKS_MAPPING = {"invoice_date": "Date", "supplier_name": "Particulars",
                 "supplier_gstin": "GSTIN/UIN", "invoice_no": "Bill No",
                 "taxable": "Taxable Value", "igst": "IGST", "cgst": "CGST", "sgst": "SGST",
                 "cess": "Cess"}

# error -> (weight, expected category, expected reason codes)
ERRORS = {
    "clean": (55, C.MATCHED, ()),
    "inv_no_format_easy": (5, C.MATCHED, (R.INV_NO_FORMAT,)),  # same after normalising
    "inv_no_format_hard": (5, C.PROBABLE, (R.INV_NO_FORMAT,)),  # needs the model
    "date_shift": (5, C.MATCHED, (R.DATE_DIFF,)),
    "rounding": (5, C.MATCHED, ()),
    "value_error": (5, C.MISMATCH, (R.VALUE_DIFF, R.TAX_DIFF)),
    "gstin_typo": (4, C.PROBABLE, (R.GSTIN_TYPO,)),
    "tax_head_swap": (4, C.MISMATCH, (R.TAX_HEAD_DIFF,)),
    "not_filed": (6, C.MISSING_IN_2B, (R.MISSING_IN_2B,)),
    "itc_ineligible": (3, C.ITC_NOT_AVAILABLE, (R.ITC_INELIGIBLE,)),
    "extra_in_2b": (3, C.MISSING_IN_BOOKS, (R.MISSING_IN_BOOKS,)),
    # Several errors on one invoice, like real registers
    "combo_hard": (3, C.PROBABLE, (R.INV_NO_FORMAT, R.DATE_DIFF)),  # + rounding within tolerance
    "combo_typo": (2, C.PROBABLE, (R.GSTIN_TYPO, R.DATE_DIFF)),
    "combo_value_hard": (2, C.PROBABLE, (R.INV_NO_FORMAT, R.VALUE_DIFF, R.TAX_DIFF)),
    # Hard negative: two different invoices from one supplier, same amount, close dates
    # (recurring bills like rent). One is only in books, the other only in 2B. Must not pair.
    "lookalike": (3, None, ()),
    "lookalike_books": (0, C.MISSING_IN_2B, (R.MISSING_IN_2B,)),
    "lookalike_2b": (0, C.MISSING_IN_BOOKS, (R.MISSING_IN_BOOKS,)),
}
MODEL_CATEGORIES = {C.PROBABLE.value, C.REVIEW.value}  # either is fine for a model-found pair

NAMES_A = ["Shree", "Om", "Sai", "Ganesh", "Laxmi", "Balaji", "Krishna", "Mahalaxmi", "Jai",
           "Sunrise", "Patel", "Sharma", "Mehta", "Global", "National", "Royal", "Prime"]
NAMES_B = ["Traders", "Enterprises", "Industries", "Steels", "Agencies", "Logistics", "Polymers",
           "Chemicals", "Textiles", "Distributors", "Electricals", "Packaging", "Hardware"]
SUFFIX = ["", " Pvt Ltd", " LLP", " & Co", " Pvt. Ltd."]
OTHER_STATES = ["24", "29", "07", "33", "09", "06", "19", "08", "23"]
RATES = [5, 12, 18, 18, 18, 28]
PAISE = Decimal("0.01")


@dataclass
class Supplier:
    gstin: str
    name: str
    style: int  # which invoice-number template this supplier uses
    prefix: str
    next_no: int


@dataclass
class Dataset:
    period: str  # YYYY-MM
    recipient_gstin: str
    books: list[dict] = field(default_factory=list)  # rows with BOOKS_COLUMNS
    gstr2b: dict = field(default_factory=dict)  # portal-shaped JSON
    truth: list[dict] = field(default_factory=list)


def _money(x) -> Decimal:
    return Decimal(str(x)).quantize(PAISE, rounding=ROUND_HALF_UP)


def _fy(d: date) -> tuple[str, str]:
    start = d.year if d.month >= 4 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}", f"{start % 100:02d}-{(start + 1) % 100:02d}"


def _official_no(s: Supplier, n: int, d: date) -> str:
    fy_long, fy_short = _fy(d)
    return [f"{s.prefix}/{n:04d}", f"{s.prefix}-{n}", f"{s.prefix}/{n}/{fy_short}",
            f"{fy_long}/{s.prefix}{n:03d}", f"{n:05d}"][s.style]


def _easy_variant(raw: str, rng: random.Random) -> str:
    """Different punctuation/case/zeros, same normalised key."""
    variant = raw.replace("/", rng.choice(["-", " ", "_"])).lower()
    if rng.random() < 0.5:
        variant = variant.replace("-0", "-").replace(" 0", " ")
    return variant if variant != raw else raw.lstrip("0")  # all-digit numbers like 00042


def _hard_variant(s: Supplier, n: int, d: date) -> str:
    """Normalises differently from the official number, but the digits survive."""
    fy_long, _ = _fy(d)
    if s.style == 3:  # official is FY/PREFIXnnn
        return f"{s.prefix[:1]}{n}"
    if s.style == 4:  # official is bare digits
        return f"{s.prefix}/{n}"
    return f"{fy_long}/{n}"


def _gstin_typo(g: str, rng: random.Random) -> str:
    pos = rng.choice([0, 1, 12, 14])  # outside the PAN, so same-PAN candidates still catch it
    pool = "0123456789" if pos < 2 else "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return g[:pos] + rng.choice([c for c in pool if c != g[pos]]) + g[pos + 1:]


def _tax(taxable: Decimal, rate: int, inter_state: bool) -> dict:
    if inter_state:
        return {"igst": _money(taxable * rate / 100), "cgst": _money(0), "sgst": _money(0)}
    half = _money(taxable * rate / 200)
    return {"igst": _money(0), "cgst": half, "sgst": half}


def generate(seed: int = 42, n_invoices: int = 400, n_suppliers: int = 40,
             period: str = "2025-04", flat: bool = True) -> Dataset:
    """flat=True writes the Oct-2024+ 2B shape (amounts on the invoice), else items[]."""
    rng = random.Random(seed)
    year, month = map(int, period.split("-"))
    month_start = date(year, month, 1)
    days_in_month = ((month_start + timedelta(days=32)).replace(day=1) - month_start).days

    recipient = gst.generate(rng, state=RECIPIENT_STATE)
    suppliers = []
    for _ in range(n_suppliers):
        state = RECIPIENT_STATE if rng.random() < 0.6 else rng.choice(OTHER_STATES)
        name = f"{rng.choice(NAMES_A)} {rng.choice(NAMES_B)}{rng.choice(SUFFIX)}"
        prefix = "".join(w[0] for w in name.split()[:2]).upper() + rng.choice(["", "INV", "S"])
        suppliers.append(Supplier(gst.generate(rng, state=state), name, rng.randrange(5), prefix,
                                  rng.randint(1, 900)))

    errors, weights = zip(*((k, v[0]) for k, v in ERRORS.items()), strict=True)
    pairs = []  # (books_row | None, (supplier, 2b_invoice) | None, error)
    for _ in range(n_invoices):
        s = rng.choice(suppliers)
        n, s.next_no = s.next_no, s.next_no + rng.randint(1, 3)
        d = month_start + timedelta(days=rng.randrange(days_in_month))
        taxable = _money(rng.lognormvariate(10, 1.1)).max(_money(500))
        rate = rng.choice(RATES)
        inter = s.gstin[:2] != RECIPIENT_STATE
        tax = _tax(taxable, rate, inter)
        cess = _money(taxable * Decimal("0.12")) if rate == 28 and rng.random() < 0.2 else _money(0)
        official = _official_no(s, n, d)
        inv2b = {"inum": official, "typ": "R", "dt": d.strftime("%d-%m-%Y"),
                 "val": float(taxable + sum(tax.values()) + cess), "pos": RECIPIENT_STATE,
                 "rev": "N", "itcavl": "Y", "rsn": "", "diffprcnt": 1,
                 "txval": taxable, **tax, "cess": cess}
        row = {"Date": d, "Particulars": s.name, "GSTIN/UIN": s.gstin, "Bill No": official,
               "Taxable Value": taxable, "IGST": tax["igst"], "CGST": tax["cgst"],
               "SGST": tax["sgst"], "Cess": cess}

        err = rng.choices(errors, weights)[0]
        if err == "lookalike":
            n2 = n + rng.randint(20, 60)
            s.next_no = n2 + 1
            d2 = d + timedelta(days=rng.randint(0, 3))
            twin = {**inv2b, "inum": _official_no(s, n2, d2), "dt": d2.strftime("%d-%m-%Y")}
            pairs.append((row, None, "lookalike_books"))
            pairs.append((None, (s, twin), "lookalike_2b"))
            continue
        if err == "combo_hard":
            row["Bill No"] = _hard_variant(s, n, d)
            row["Date"] = d + timedelta(days=rng.choice([-1, 1]) * rng.randint(1, 5))
            row["Taxable Value"] = taxable + rng.choice([-1, 1]) * _money(rng.uniform(0.01, 1))
        elif err == "combo_typo":
            row["GSTIN/UIN"] = _gstin_typo(s.gstin, rng)
            row["Date"] = d + timedelta(days=rng.choice([-1, 1]) * rng.randint(1, 5))
        elif err == "combo_value_hard":
            row["Bill No"] = _hard_variant(s, n, d)
            off = taxable * Decimal(str(rng.uniform(0.02, 0.2))) * rng.choice([-1, 1])
            row["Taxable Value"] = _money(taxable + off).max(_money(100))
            new_tax = _tax(row["Taxable Value"], rate, inter)
            row.update(IGST=new_tax["igst"], CGST=new_tax["cgst"], SGST=new_tax["sgst"])
        elif err == "inv_no_format_easy":
            row["Bill No"] = _easy_variant(official, rng)
        elif err == "inv_no_format_hard":
            row["Bill No"] = _hard_variant(s, n, d)
        elif err == "date_shift":
            row["Date"] = d + timedelta(days=rng.choice([-1, 1]) * rng.randint(1, 5))
        elif err == "rounding":
            row["Taxable Value"] = taxable + rng.choice([-1, 1]) * _money(rng.uniform(0.01, 1))
        elif err == "value_error":
            off = taxable * Decimal(str(rng.uniform(0.02, 0.2))) * rng.choice([-1, 1])
            row["Taxable Value"] = _money(taxable + off).max(_money(100))
            new_tax = _tax(row["Taxable Value"], rate, inter)
            row.update(IGST=new_tax["igst"], CGST=new_tax["cgst"], SGST=new_tax["sgst"])
        elif err == "gstin_typo":
            row["GSTIN/UIN"] = _gstin_typo(s.gstin, rng)
        elif err == "tax_head_swap":
            total = tax["igst"] + tax["cgst"] + tax["sgst"]
            if inter:  # books wrongly split IGST into CGST+SGST
                row.update(IGST=_money(0), CGST=_money(total / 2), SGST=total - _money(total / 2))
            else:
                row.update(IGST=total, CGST=_money(0), SGST=_money(0))
        elif err == "itc_ineligible":
            inv2b.update(itcavl="N", rsn=rng.choice(["P", "C"]))

        pairs.append((None if err == "extra_in_2b" else row,
                      None if err == "not_filed" else (s, inv2b), err))

    ds = Dataset(period=period, recipient_gstin=recipient)
    # Books: sorted by date like a real register. 2B: grouped by supplier like the portal.
    book_order = sorted((p for p in pairs if p[0]), key=lambda p: (p[0]["Date"], p[0]["Bill No"]))
    books_id = {id(p): f"B{i}" for i, p in enumerate(book_order, start=1)}
    ds.books = [p[0] for p in book_order]

    b2b, g2b_id = [], {}
    for s in suppliers:
        mine = sorted((p for p in pairs if p[1] and p[1][0] is s),
                      key=lambda p: (p[1][1]["dt"][6:] + p[1][1]["dt"][3:5] + p[1][1]["dt"][:2]))
        if not mine:
            continue
        invs = []
        for p in mine:
            g2b_id[id(p)] = f"G{len(g2b_id) + 1}"
            invs.append(_json_invoice(p[1][1], flat))
        b2b.append({"ctin": s.gstin, "trdnm": s.name.upper(),
                    "supfildt": (month_start.replace(day=1) + timedelta(days=days_in_month + 10))
                    .strftime("%d-%m-%Y"), "supprd": f"{month:02d}{year}", "inv": invs})
    ds.gstr2b = {"chksum": f"synthetic-seed-{seed}", "data": {
        "gstin": recipient, "rtnprd": f"{month:02d}{year}", "version": "1.0",
        "gendt": (month_start + timedelta(days=days_in_month + 13)).strftime("%d-%m-%Y"),
        "docdata": {"b2b": b2b}}}

    for p in pairs:
        _, category, reasons = ERRORS[p[2]]
        ds.truth.append({"books_id": books_id.get(id(p), ""), "gstr2b_id": g2b_id.get(id(p), ""),
                         "error": p[2], "expected_category": category.value,
                         "expected_reasons": "|".join(r.value for r in reasons)})
    ds.truth.sort(key=lambda t: (t["books_id"] == "", int(t["books_id"][1:] or 0),
                                 int(t["gstr2b_id"][1:] or 0)))
    return ds


def _json_invoice(inv: dict, flat: bool) -> dict:
    out = {k: (float(v) if isinstance(v, Decimal) else v) for k, v in inv.items()}
    amounts = {k: out.pop(k) for k in ("txval", "igst", "cgst", "sgst", "cess")}
    if not amounts["igst"]:
        del amounts["igst"]  # real files leave zero heads out (docs/gstr2b-schema.md)
    if flat:
        return {**out, **amounts}
    rate = round((sum(v for k, v in amounts.items() if k != "txval") / amounts["txval"]) * 100)
    return {**out, "items": [{"num": rate * 100 + 1, "rt": rate, **amounts}]}
