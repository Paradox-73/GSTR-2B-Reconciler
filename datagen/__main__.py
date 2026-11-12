"""python -m datagen --seed 42 --invoices 400 --out tests/golden"""
import argparse
import csv
import json
from pathlib import Path

import pandas as pd

from datagen.generate import BOOKS_COLUMNS, BOOKS_MAPPING, generate


def write(ds, out: Path, xlsx: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "gstr2b.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(ds.gstr2b, f, indent=1)
    books = pd.DataFrame(ds.books, columns=BOOKS_COLUMNS)
    books["Date"] = pd.to_datetime(books["Date"]).dt.strftime("%d-%m-%Y")
    books.to_csv(out / "books.csv", index=False, lineterminator="\n")
    if xlsx:
        books.to_excel(out / "books.xlsx", index=False)
    with open(out / "truth.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ds.truth[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(ds.truth)
    with open(out / "mapping.json", "w", encoding="utf-8", newline="\n") as f:
        json.dump(BOOKS_MAPPING, f, indent=1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic books + GSTR-2B with answers")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--invoices", type=int, default=400)
    ap.add_argument("--suppliers", type=int, default=40)
    ap.add_argument("--period", default="2025-04", help="YYYY-MM")
    ap.add_argument("--items-format", action="store_true", help="pre Oct-2024 2B shape")
    ap.add_argument("--xlsx", action="store_true", help="also write books.xlsx")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    ds = generate(a.seed, a.invoices, a.suppliers, a.period, flat=not a.items_format)
    write(ds, a.out, a.xlsx)
    counts = pd.Series([t["error"] for t in ds.truth]).value_counts().to_dict()
    print(f"wrote {len(ds.books)} books rows, {len(ds.truth)} truth rows to {a.out}: {counts}")


if __name__ == "__main__":
    main()
