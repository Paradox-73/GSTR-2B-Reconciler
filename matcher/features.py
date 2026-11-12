"""Features for a books/2B candidate pair (DESIGN.md 8.5). Order is part of the model contract:
add new features at the end and retrain."""
import re

from rapidfuzz.distance import JaroWinkler, Levenshtein

from matcher.models import Invoice
from matcher.normalise import numeric_part

NAMES = [
    "inv_lev_ratio", "inv_jaro_winkler", "inv_numeric_equal", "inv_token_overlap", "inv_len_diff",
    "gstin_equal", "pan_equal", "gstin_edit_distance",
    "date_diff_days", "same_month",
    "taxable_abs_diff", "taxable_rel_diff", "tax_abs_diff", "tax_rel_diff", "total_abs_diff",
    "total_rel_diff",
    "tax_head_mismatch",
]


def _tokens(raw: str) -> set[str]:
    return {t.lstrip("0") or "0" for t in re.findall(r"[A-Z]+|\d+", raw.upper())}


def _rel(a, b) -> float:
    top = max(abs(a), abs(b))
    return float(abs(a - b) / top) if top else 0.0


def features(b: Invoice, g: Invoice) -> list[float]:
    nb, ng = b.inv_no_norm, g.inv_no_norm
    tb, tg = _tokens(b.inv_no_raw), _tokens(g.inv_no_raw)
    num_b, num_g = numeric_part(b.inv_no_raw), numeric_part(g.inv_no_raw)
    b_igst, g_igst = b.igst > 0, g.igst > 0
    b_split, g_split = (b.cgst + b.sgst) > 0, (g.cgst + g.sgst) > 0
    return [
        Levenshtein.normalized_similarity(nb, ng),
        JaroWinkler.similarity(nb, ng),
        float(bool(num_b) and num_b == num_g),
        len(tb & tg) / len(tb | tg) if tb | tg else 0.0,
        float(abs(len(nb) - len(ng))),
        float(b.supplier_gstin == g.supplier_gstin),
        float(b.pan == g.pan),
        float(Levenshtein.distance(b.supplier_gstin, g.supplier_gstin)),
        float(abs((b.inv_date - g.inv_date).days)),
        float((b.inv_date.year, b.inv_date.month) == (g.inv_date.year, g.inv_date.month)),
        float(abs(b.taxable - g.taxable)),
        _rel(b.taxable, g.taxable),
        float(abs(b.total_tax - g.total_tax)),
        _rel(b.total_tax, g.total_tax),
        float(abs(b.total - g.total)),
        _rel(b.total, g.total),
        float((b_igst, b_split) != (g_igst, g_split)),
    ]
