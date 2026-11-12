"""Labelled candidate pairs. Synthetic now; CA review decisions get added in #22."""
from decimal import Decimal

import numpy as np
import pandas as pd

from datagen.generate import BOOKS_MAPPING, generate
from matcher.candidates import candidates
from matcher.engine import exact_pass
from matcher.features import features
from matcher.parsers import parse_books, parse_gstr2b

GOLDEN_SEED = 42  # never train on the golden set


def synthetic(seeds, n_invoices: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """Features + labels for the pairs the engine would actually ask the model about."""
    xs, ys = [], []
    for seed in seeds:
        if seed == GOLDEN_SEED:
            raise ValueError("seed 42 is the golden set")
        ds = generate(seed=seed, n_invoices=n_invoices, n_suppliers=max(10, n_invoices // 10))
        books = parse_books(pd.DataFrame(ds.books), BOOKS_MAPPING)
        g2b = parse_gstr2b(ds.gstr2b)
        _, left_b, left_g = exact_pass(books, g2b, Decimal("1"))
        truth = {(t["books_id"], t["gstr2b_id"]) for t in ds.truth}
        for b, g in candidates(left_b, left_g):
            xs.append(features(b, g))
            ys.append((b.id, g.id) in truth)
    return np.array(xs, dtype=np.float32), np.array(ys, dtype=np.float32)
