// Logical purchase-register columns (matcher/parsers.py REQUIRED_COLUMNS + cess)
export const LOGICAL_COLUMNS = [
  { key: 'supplier_gstin', label: 'Supplier GSTIN', required: true },
  { key: 'supplier_name', label: 'Supplier name', required: true },
  { key: 'invoice_no', label: 'Invoice number', required: true },
  { key: 'invoice_date', label: 'Invoice date', required: true },
  { key: 'taxable', label: 'Taxable value', required: true },
  { key: 'igst', label: 'IGST', required: true },
  { key: 'cgst', label: 'CGST', required: true },
  { key: 'sgst', label: 'SGST / UTGST', required: true },
  { key: 'cess', label: 'Cess', required: false },
];

// Names seen in Tally / Excel exports, already normalised (lowercase, letters and digits only)
const SYNONYMS = {
  supplier_gstin: ['gstinuin', 'gstin', 'suppliergstin', 'partygstin', 'gstno', 'gstnumber', 'ctin'],
  supplier_name: ['suppliername', 'particulars', 'partyname', 'party', 'supplier', 'vendorname', 'vendor', 'tradename', 'name'],
  invoice_no: ['invoiceno', 'invoicenumber', 'billno', 'billnumber', 'invno', 'supplierinvoiceno', 'voucherno', 'docno', 'refno'],
  invoice_date: ['invoicedate', 'billdate', 'invdate', 'date', 'voucherdate', 'docdate'],
  taxable: ['taxablevalue', 'taxableamount', 'taxable', 'assessablevalue', 'txval'],
  igst: ['igst', 'igstamount', 'integratedtax'],
  cgst: ['cgst', 'cgstamount', 'centraltax'],
  sgst: ['sgst', 'sgstamount', 'sgstutgst', 'utgst', 'statetax'],
  cess: ['cess', 'cessamount'],
};

const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');

// Returns {logical: header} for every column it can guess; each header is used at most once
export function guessMapping(headers) {
  const used = new Set();
  const out = {};
  const pick = (key, test) => {
    if (out[key]) return;
    for (const syn of SYNONYMS[key]) {
      const h = headers.find((x) => !used.has(x) && test(norm(x), syn));
      if (h !== undefined) {
        out[key] = h;
        used.add(h);
        return;
      }
    }
  };
  // Exact names first for every column, so a loose match can't steal a header that fits exactly
  for (const { key } of LOGICAL_COLUMNS) pick(key, (n, syn) => n === syn);
  for (const { key } of LOGICAL_COLUMNS) pick(key, (n, syn) => syn.length >= 4 && n.includes(syn));
  return out;
}
