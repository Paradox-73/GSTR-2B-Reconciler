// Order matches DESIGN.md 8.7
export const CATEGORIES = [
  { key: 'matched', label: 'Matched' },
  { key: 'probable_match', label: 'Probable match' },
  { key: 'needs_review', label: 'Needs review' },
  { key: 'mismatch', label: 'Mismatch' },
  { key: 'missing_in_2b', label: 'Missing in 2B' },
  { key: 'missing_in_books', label: 'Missing in books' },
  { key: 'itc_not_available', label: 'ITC not available' },
];

export const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.key, c.label]));

export const REVIEWABLE = new Set(['probable_match', 'needs_review', 'mismatch']);

export const REASONS = {
  VALUE_DIFF: 'Taxable value differs',
  TAX_DIFF: 'Tax amount differs',
  TAX_HEAD_DIFF: 'IGST vs CGST+SGST split differs',
  DATE_DIFF: 'Invoice date differs',
  INV_NO_FORMAT: 'Invoice number written differently',
  GSTIN_TYPO: 'Supplier GSTIN looks mistyped',
  MISSING_IN_2B: "Supplier hasn't filed",
  MISSING_IN_BOOKS: 'Not recorded in the purchase register',
  ITC_INELIGIBLE: 'Input tax credit not available',
};

export const DECISION_LABEL = { accept: 'Accepted', reject: 'Rejected', link: 'Linked' };

export const STATUS_LABEL = {
  queued: 'Queued',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
};
