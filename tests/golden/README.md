# Golden set

Fixed-seed output of the generator. CI runs the matcher on it and compares against `truth.csv`.

Regenerate (only when you change `datagen/` on purpose, and say why in the PR):

```bash
python -m datagen --seed 42 --invoices 400 --out tests/golden
```

`truth.csv` has one row per real-world invoice: which books row (`B<n>`) and 2B invoice (`G<n>`) it
became, the planted error, and the category + reason codes the engine should give it.
