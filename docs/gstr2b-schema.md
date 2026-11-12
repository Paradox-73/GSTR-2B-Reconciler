# GSTR-2B JSON: B2B section schema

Researched 2026-11-13. GSTN, the company that runs the GST portal, does not publish its API schema pages without a login (`https://developer.gst.gov.in/apiportal/taxpayer/gstr2b` returned 404). Facts below therefore come from:

- **[GSTN-SAMPLE]** GSTN's own sample payload for the "GSTR-2B Get All Details" API, mirrored by Vayana, a GSP (GST Suvidha Provider, a licensed reseller of GSTN APIs): https://docs.enriched-api.vayana.com/routes/basic/gstn/apis/returns/Gstr-Download-Lite-Api/gstr-2b/ . The same payload (same GSTIN `01AABCE2207R1Z5`, invoice `S008400`, same IRN) is the test fixture in India Compliance, so it is the official GSTN sample.
- **[IC]** India Compliance, the open-source GST app for ERPNext, which downloads and parses live GSTR-2B data. Pinned to commit `ca5ef60`:
  - field map: https://github.com/resilient-tech/india-compliance/blob/ca5ef60c65472e981ef38476b796c511c2ac03c8/india_compliance/gst_returns/fields/gstr2.py
  - B2B parser and code tables: https://github.com/resilient-tech/india-compliance/blob/ca5ef60c65472e981ef38476b796c511c2ac03c8/india_compliance/gst_india/utils/gstr_2/sections/b2b.py
  - invoice type codes, GSTIN regexes: https://github.com/resilient-tech/india-compliance/blob/ca5ef60c65472e981ef38476b796c511c2ac03c8/india_compliance/gst_india/constants/__init__.py
  - GSTIN check digit: https://github.com/resilient-tech/india-compliance/blob/ca5ef60c65472e981ef38476b796c511c2ac03c8/india_compliance/gst_india/utils/__init__.py (function `validate_gstin_check_digit`)
  - fixtures before and after the Oct-2024 change: `india_compliance/gst_india/data/test_gstr_2b_v3_0.json` and `test_gstr_2b_v4_0.json` in the same commit
- **[REAL-FILE]** A GSTR-2B JSON file for January 2022 from a real taxpayer, committed to a reconciliation project: https://github.com/vkWeb/gstr-reconciliation/blob/main/samples/2b.json . All 4 GSTINs in it pass the checksum below, which supports that it is a real portal download. The repo's author added one key, `status`, to each invoice; GSTN does not send it.
- **[GSTN-RN]** GSTN release note, 30-Aug-2024: https://developer.gst.gov.in/pages/apiportal/data/ReleaseNotes/CR25787_Rel_Notes_G2B.pdf
- **[GSTN-FAQ]** GST portal FAQ on GSTR-2B: https://tutorial.gst.gov.in/userguide/returns/FAQ_gstr2b.htm
- **[TALLY]** Tally Solutions article on the Oct-2024 change: https://tallysolutions.com/gst/important-changes-to-gstr-2b-api-by-gstn-from-october-2024/

## 1. Top-level structure

The file downloaded from the portal (Returns Dashboard, GSTR-2B, Download JSON) is:

```
{
  "chksum": "<hex string>",
  "data": {
    "gstin":   "<recipient GSTIN>",
    "rtnprd":  "MMYYYY",
    "version": "1.0",
    "gendt":   "DD-MM-YYYY",
    "itcsumm": { ... },
    "cpsumm":  { ... },
    "docdata": { "b2b": [ ... ], "b2ba": [...], "cdnr": [...], ... },
    "docRejdata": { ... },
    "cpSummRej":  { ... }
  }
}
```

| Key | Meaning | Source |
|---|---|---|
| `chksum` | checksum string, sibling of `data` at the root | [REAL-FILE], [IC] v3/v4 fixtures |
| `data` | yes, everything sits inside `data` | [REAL-FILE], [GSTN-SAMPLE], [IC] |
| `data.gstin` | your own (recipient) GSTIN | [GSTN-SAMPLE], [REAL-FILE] |
| `data.rtnprd` | return period, `MMYYYY`, e.g. `"012022"` | [GSTN-SAMPLE], [REAL-FILE] |
| `data.version` | `"1.0"` in every sample, including the post-2024 fixture | [GSTN-SAMPLE], [REAL-FILE], [IC] v4 fixture |
| `data.gendt` | generation date, `DD-MM-YYYY`, e.g. `"14-02-2022"` | [GSTN-SAMPLE], [REAL-FILE] |
| `data.itcsumm` | ITC summary (`itcavl` → `nonrevsup` → `b2b` → `igst/cgst/sgst/cess` etc.) | [GSTN-SAMPLE], [REAL-FILE] |
| `data.cpsumm` | counterparty (supplier-wise) summary | [GSTN-SAMPLE], [IC] fixtures |
| `data.docdata` | document lists, one array per section | [GSTN-SAMPLE], [REAL-FILE] |
| `data.docRejdata`, `data.cpSummRej` | documents the taxpayer rejected on IMS (Invoice Management System, the portal screen from Oct 2024 where a buyer accepts/rejects supplier invoices). Only in the post-Oct-2024 fixture | [IC] v4 fixture, [IC] `RawField2b.DOC_REJECTED` |

`docdata` section keys seen: `b2b, b2ba, cdnr, cdnra, isd, isda, impg, impgsez` (old fixture) plus `ecom, ecoma, itcrev` (post-Oct-2024 fixture) [IC]. A section with no documents is **absent**, not an empty list: the real file has only `b2b` [REAL-FILE].

**Watch out:** the GSP API response is wrapped one level deeper: `{"status": "1", "data": {"chksum": ..., "data": {...}}, ...}` [GSTN-SAMPLE]. That is the API envelope, not the portal file. A parser that accepts both can do `root = j["data"]; if "data" in root and "gstin" not in root: root = root["data"]`.

## 2. B2B supplier object (`data.docdata.b2b[]`)

| Key | Meaning / format | Source |
|---|---|---|
| `ctin` | supplier GSTIN | [GSTN-SAMPLE], [IC], [REAL-FILE] |
| `trdnm` | supplier trade name | same |
| `supfildt` | date supplier filed GSTR-1/IFF, `DD-MM-YYYY` | same |
| `supprd` | supplier's return period, `MMYYYY` (can be an older month than `rtnprd`, e.g. `"092021"` inside a Jan-2022 file) | same |
| `inv` | array of invoice objects | same |

## 3. Invoice object (`b2b[].inv[]`)

| Key | Type | Meaning / format | Source |
|---|---|---|---|
| `inum` | string | invoice number, as typed by supplier (e.g. `"AEL/1289/2021-22"`) | [GSTN-SAMPLE], [REAL-FILE] |
| `typ` | string | invoice type code, see §4 | [GSTN-SAMPLE], [IC] |
| `dt` | string | invoice date `DD-MM-YYYY`. Note: GSTR-2A uses `idt`, GSTR-2B uses `dt` | [IC] `RawField2b.DOC_DATE = "dt"` vs `RawField2a.DOC_DATE = "idt"` |
| `val` | number | total invoice value | [GSTN-SAMPLE], [REAL-FILE] |
| `pos` | string | place of supply, 2-digit state code with leading zero (`"06"`) | [GSTN-SAMPLE], [REAL-FILE] |
| `rev` | string | reverse charge, `"Y"` / `"N"` | [IC] `Y_N_TO_CHECK`, [GSTN-SAMPLE] |
| `itcavl` | string | ITC available: `"Y"`, `"N"`, `"T"` (Temporary) | [IC] `ITC_AVAILABILITY = {**YES_NO, "T": "Temporary"}` |
| `rsn` | string | reason ITC unavailable: `"P"`, `"C"`, or `""` | [IC] `ITC_REASONS`, [REAL-FILE] |
| `diffprcnt` | number | applicable % of tax rate: `1` or `0.65`; may be absent, meaning `1` | [IC] `DIFF_PERCENT = {1: 1, 0.65: 0.65, None: 1}` |
| `srctyp` | string | source of the document, `"e-Invoice"` in the GSTN sample | [GSTN-SAMPLE] |
| `irn` | string | e-invoice IRN (64 chars) | [GSTN-SAMPLE] |
| `irngendate` | string | IRN generation date `DD-MM-YYYY` | [GSTN-SAMPLE] |
| `items` | array | rate-wise lines, **old format only**, see §5 | [GSTN-SAMPLE], [REAL-FILE] |
| `txval`, `igst`, `cgst`, `sgst`, `cess` | number | invoice-level totals, **new format only**, see §5 | [IC] v4 fixture |

Item object (`inv[].items[]`, old format): `num`, `rt`, `txval`, `igst`, `cgst`, `sgst`, `cess` [GSTN-SAMPLE], [IC] `RawField2b`.
- `num` is not a 1..n line index. The real file has `num: 501` with `rt: 5` and `num: 1801` with `rt: 18` [REAL-FILE]. Do not rely on it.
- `rt` is a percent number (`5`, `18`), not a fraction [GSTN-SAMPLE], [REAL-FILE].
- **Zero tax heads can be missing.** In the real file, intra-state items have `cgst`, `sgst`, `cess` but **no `igst` key** [REAL-FILE]. Default every amount to 0.

`srctyp`, `irn`, `irngendate` were absent from every invoice in the Jan-2022 real file (non-e-invoice documents) [REAL-FILE]. Treat all three as optional.

## 4. Value conventions

- **Dates**: `DD-MM-YYYY` for `dt`, `supfildt`, `gendt`, `irngendate` [GSTN-SAMPLE], [REAL-FILE]; India Compliance parses them all with `day_first=True` [IC `gstr_2b.py`, `sections/b2b.py`].
- **Periods**: `MMYYYY` with no separator for `rtnprd`, `supprd` [GSTN-SAMPLE], [REAL-FILE].
- **`rev`**: `Y` / `N` [IC].
- **`itcavl`**: `Y` / `N` / `T` [IC]. The portal FAQ confirms Yes/No and the "No" cases but does not mention "T" [GSTN-FAQ]. `T` = **UNCONFIRMED** against a GSTN document.
- **`rsn`**: [IC] `ITC_REASONS`:
  - `P` = "POS and supplier state are same but recipient state is different" (matches [GSTN-FAQ] ITC Eligibility FAQ 2 item ii)
  - `C` = "Return filed post annual cut-off" (matches [GSTN-FAQ] item i, time-barred ITC under section 16(4) of the CGST Act)
  - `""` when ITC is available [REAL-FILE]
- **`typ`** (invoice type), [IC] `GST_CATEGORY_MAP`:
  - `R` Regular
  - `SEZWP` SEZ with payment of tax
  - `SEZWOP` SEZ without payment of tax
  - `DE` Deemed export
  - `CBW` Intra-state supplies attracting IGST
  - In `cdnr` notes, `typ` is the note type (`C`/`D`) and supply type moves to `suptyp` [IC `RawField2b` comment].
- **`pos`**: 2-character string with leading zero (`"06"`, `"22"`, `"33"`) [GSTN-SAMPLE], [REAL-FILE]; India Compliance maps it through its state-number table [IC].
- **`diffprcnt`**: `1` or `0.65` [IC]. 0.65 = 65% of the normal rate, a concession under notification 8/2020-IGST. That legal reference is **UNCONFIRMED** in sources read here.
- **`srctyp`** values other than `"e-Invoice"`: **UNCONFIRMED**.

## 5. Format versions: old (items) vs new (flat), and 2024+ changes

- 30-Aug-2024 GSTN release note: in "GSTR2B - Get All Details", "item wise details are removed from the summary data. Hence, response payload and schema are updated." It also adds on-demand 2B generation APIs, tied to IMS [GSTN-RN].
- Tally: the new API version (v4) applies from 1-Oct-2024, downloads switch on 14-Nov-2024, first affected period is the October 2024 GSTR-2B; API v3.0 support ends; periods up to September 2024 can still come in the old format [TALLY].
- India Compliance commit of 18-Nov-2024, "fix: Items Table Removed from Invoice Data (#2723)", links the same GSTN release note. Their v4 fixture invoice has `txval`, `igst`, `cgst`, `sgst`, `cess` directly on the invoice and no `items` key. Their parser takes totals from `items` when present, else from the invoice [IC `gstr.py` `get_transaction`].
- `data.version` stays `"1.0"` in both fixtures [IC]. **It cannot be used to tell the formats apart.** Detect by presence of `items`.
- New `docdata` sections in the new format: `ecom`, `ecoma` (supplies through e-commerce operators), `itcrev`; new top-level `docRejdata`, `cpSummRej` [IC v4 fixture].
- A later GSTN release moved "Get All Details" to version 4.1 for GSTR-7 invoice-level changes (seen only in a search-result snippet of a taxpro-gsp Google Group post, https://groups.google.com/g/taxpro-gsp/c/6a0Ejnlwvko). **UNCONFIRMED**; it should not touch B2B.
- Large returns: the API reports a file count `fc` and the client downloads files 1..fc and merges them, concatenating the `docdata` arrays, with `itcsumm` only in the first file [IC `gstr_2/__init__.py`, `TestMultiFileRawMerge`]. Whether the **portal download button** also splits into several JSON files: **UNCONFIRMED**.
- **UNCONFIRMED**: that the portal-downloaded JSON (as opposed to the GSP API) also dropped `items` from Oct-2024. GSTN release note and Tally both speak only about the API. A parser should accept both shapes.
- Third-party converter blogs (e.g. https://gst-converter.pages.dev/blog/fix-invalid-json-format-gstr2b) claim some files use `docsumm` instead of `docdata`, or uppercase `B2B`. No primary source or real file seen here does this: **UNCONFIRMED**. The `iamt/camt/samt/csamt` and `itms/itm_det` keys they mention belong to GSTR-2A, not 2B [IC `RawField2a`].

## 6. GSTIN format and check character

Structure, 15 characters [IC regex `NORMAL`, whose comment cites https://developer.gst.gov.in/apiportal/taxpayer/returns]:

| Pos | Content | Regex |
|---|---|---|
| 1-2 | state code, digits | `[0-9]{2}` |
| 3-12 | PAN (5 letters, 4 digits, 1 letter) | `[A-Z]{5}[0-9]{4}[A-Z]` |
| 13 | entity number for the same PAN in the same state, `1-9` then `A-Z` | `[1-9A-Z]` |
| 14 | `Z` for normal taxpayers; regex also allows `1-9`, `A`, `B`, `D-J` | `[Z1-9ABD-J]` |
| 15 | check character | `[0-9A-Z]` |

Other GSTIN-shaped IDs (TDS `...D.`, TCS `...C.`, UIN, NRI, OIDAR `99..OS.`) have their own regexes in [IC constants].

**Check character algorithm** (Luhn mod 36), from [IC] `validate_gstin_check_digit`:

```
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"   # value = index, 0..35
total = 0
for i, ch in enumerate(gstin[:14]):              # first 14 chars
    factor  = 1 if i % 2 == 0 else 2             # 1,2,1,2,... from the left
    p       = factor * CHARS.index(ch)
    total  += p // 36 + p % 36                   # add the base-36 "digits" of p
check = CHARS[(36 - total % 36) % 36]
valid = gstin[14] == check
```

Worked example, `27AAPFU0939F1ZV`:

| # | char | value | factor | product | quotient + remainder | running total |
|---|---|---|---|---|---|---|
| 1 | 2 | 2 | 1 | 2 | 0+2 = 2 | 2 |
| 2 | 7 | 7 | 2 | 14 | 0+14 = 14 | 16 |
| 3 | A | 10 | 1 | 10 | 10 | 26 |
| 4 | A | 10 | 2 | 20 | 20 | 46 |
| 5 | P | 25 | 1 | 25 | 25 | 71 |
| 6 | F | 15 | 2 | 30 | 30 | 101 |
| 7 | U | 30 | 1 | 30 | 30 | 131 |
| 8 | 0 | 0 | 2 | 0 | 0 | 131 |
| 9 | 9 | 9 | 1 | 9 | 9 | 140 |
| 10 | 3 | 3 | 2 | 6 | 6 | 146 |
| 11 | 9 | 9 | 1 | 9 | 9 | 155 |
| 12 | F | 15 | 2 | 30 | 30 | 185 |
| 13 | 1 | 1 | 1 | 1 | 1 | 186 |
| 14 | Z | 35 | 2 | 70 | 1+34 = 35 | 221 |

221 mod 36 = 5; (36 − 5) mod 36 = 31; `CHARS[31]` = `V`. Matches the 15th character.

Checked by running the algorithm (Python, this session):
- Passes: the 4 supplier/recipient GSTINs in [REAL-FILE] (`22AEZPA0778G1ZF`, `22ATSPA3620P1ZL`, `22AAKFA7825M1Z8`, `22AAEHV9549P1ZA`) and `27AAPFU0939F1ZV`.
- **Fails: GSTN's own sample GSTIN `01AABCE2207R1Z5`** (computed check char is `V`). Test fixtures copied from GSTN samples will fail a strict checksum; warn rather than reject, or use real-format test GSTINs.
- GSTN does not publish this algorithm on any page found here. The algorithm itself is **UNCONFIRMED against a GSTN document**, but confirmed empirically against real portal data.

## 7. Minimal sample (old, item-level format, periods up to Sep-2024)

GSTINs below are made up; their check characters were computed with the algorithm above. Supplier 1 is intra-state (Maharashtra to Maharashtra, CGST+SGST, `igst` key absent as in the real file). Supplier 2 is inter-state (Gujarat to Maharashtra, IGST), with one reverse-charge invoice.

```json
{
  "chksum": "e5b98ef7514e3c25ca96a088bc9edb9ca071e2fb0a0b517e925e131b87819bef",
  "data": {
    "gstin": "27ABCDE1234F1Z0",
    "rtnprd": "082024",
    "version": "1.0",
    "gendt": "14-09-2024",
    "docdata": {
      "b2b": [
        {
          "ctin": "27PQRSX5678K1ZY",
          "trdnm": "SHREE TRADERS",
          "supfildt": "11-09-2024",
          "supprd": "082024",
          "inv": [
            {
              "inum": "ST/101/24-25",
              "typ": "R",
              "dt": "05-08-2024",
              "val": 11800,
              "pos": "27",
              "rev": "N",
              "itcavl": "Y",
              "rsn": "",
              "diffprcnt": 1,
              "items": [
                { "num": 1801, "rt": 18, "txval": 10000, "cgst": 900, "sgst": 900, "cess": 0 }
              ]
            },
            {
              "inum": "ST/117/24-25",
              "typ": "R",
              "dt": "21-08-2024",
              "val": 5250,
              "pos": "27",
              "rev": "N",
              "itcavl": "Y",
              "rsn": "",
              "diffprcnt": 1,
              "srctyp": "e-Invoice",
              "irn": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
              "irngendate": "21-08-2024",
              "items": [
                { "num": 501, "rt": 5, "txval": 5000, "cgst": 125, "sgst": 125, "cess": 0 }
              ]
            }
          ]
        },
        {
          "ctin": "24LMNOP4321Q1ZA",
          "trdnm": "GUJARAT LOGISTICS LLP",
          "supfildt": "10-09-2024",
          "supprd": "082024",
          "inv": [
            {
              "inum": "GL-2024-0456",
              "typ": "R",
              "dt": "12-08-2024",
              "val": 59000,
              "pos": "27",
              "rev": "Y",
              "itcavl": "Y",
              "rsn": "",
              "diffprcnt": 1,
              "items": [
                { "num": 1, "rt": 18, "txval": 50000, "igst": 9000, "cgst": 0, "sgst": 0, "cess": 0 }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

Same third invoice in the **new format** (Oct-2024 onward, per [IC] v4 fixture): no `items`, totals on the invoice.

```json
{
  "inum": "GL-2024-0456", "typ": "R", "dt": "12-10-2024", "val": 59000, "pos": "27",
  "rev": "Y", "itcavl": "Y", "rsn": "", "diffprcnt": 1,
  "txval": 50000, "igst": 9000, "cgst": 0, "sgst": 0, "cess": 0
}
```

`itcsumm` and `cpsumm` are left out of the sample; a B2B parser does not need them.

## Parser checklist

1. Unwrap `data` (and a second `data` if it came from a GSP API).
2. `docdata.b2b` may be missing; treat as `[]`.
3. Per invoice: if `items` exists, sum its amounts; else read `txval/igst/cgst/sgst/cess` from the invoice.
4. Missing amount keys = 0. Missing `diffprcnt` = 1. Missing `srctyp/irn/irngendate` = none.
5. Parse dates as `DD-MM-YYYY`, periods as `MMYYYY`; keep `pos` as a 2-char string.
6. Do not use `data.version` to pick the format.
