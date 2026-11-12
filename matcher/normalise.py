"""Normalisers for invoice numbers, dates and amounts (DESIGN.md 8.2)."""
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# A financial-year token like 2025-26, 25-26, 2025/2026, FY25-26. Only counts if the years are
# consecutive, so "12-34" in an invoice number is left alone.
_FY = re.compile(r"(?<![0-9A-Z])(?:FY)?(?:20)?(\d{2})[-/](?:20)?(\d{2})(?!\d)")
_LEADING_ZEROS = re.compile(r"(?<!\d)0+(?=\d)")
_NON_ALNUM = re.compile(r"[^0-9A-Z]")


def _drop_fy(s: str) -> str:
    # Manual scan instead of re.sub: in "42/25-26" the non-FY "42/25" must not hide "25-26".
    pos = 0
    while m := _FY.search(s, pos):
        if int(m[2]) == (int(m[1]) + 1) % 100:
            s, pos = s[: m.start()] + s[m.end() :], m.start()
        else:
            pos = m.start() + 1
    return s


def invoice_no(raw) -> str:
    """'INV/0042', 'inv-42' and 'INV 42/2025-26' all become 'INV42'."""
    s = _drop_fy(str(raw or "").upper())
    s = _NON_ALNUM.sub(" ", s)
    s = _LEADING_ZEROS.sub("", s)
    return s.replace(" ", "")


def numeric_part(raw) -> str:
    """Digits after dropping the FY token, no leading zeros: 'INV/2025-26/0042' -> '42'."""
    digits = "".join(re.findall(r"\d+", _drop_fy(str(raw or "").upper())))
    return digits.lstrip("0") or ("0" if digits else "")


_DATE_FORMATS = ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y",
                 "%d-%m-%y", "%d/%m/%y", "%Y-%m-%d %H:%M:%S")
_EXCEL_EPOCH = date(1899, 12, 30)


def to_date(value) -> date:
    """Day-first parsing (Indian convention). Accepts date objects and Excel serial numbers."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, float) and value != value:
        raise ValueError("date is blank")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return _EXCEL_EPOCH + timedelta(days=int(value))
    s = str(value or "").strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {value!r}")


_PAISE = Decimal("0.01")


def amount(value) -> Decimal:
    """Money as Decimal rounded to paise. Handles '1,23,456.50', '₹ 100', blanks and NaN."""
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, float) and value != value:  # NaN from pandas empty cells
        return Decimal("0.00")
    s = str(value).replace(",", "").replace("₹", "").strip()
    try:
        return Decimal(s or "0").quantize(_PAISE, rounding=ROUND_HALF_UP)
    except InvalidOperation as e:
        raise ValueError(f"not an amount: {value!r}") from e
