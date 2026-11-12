import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { invDate, money, totalTax } from '../format.js';

export default function LinkPicker({ runId, result, onClose, onPick }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('');
  const books = result.books;

  useEffect(() => {
    // shortcut: loads the first 500 (API maximum); add paging if a period ever has more unmatched 2B rows
    api(`/runs/${runId}/results?category=missing_in_books&page=1&page_size=500`).then(
      (d) => setItems(d.items.filter((r) => r.gstr2b)),
      (err) => setError(err.message),
    );
  }, [runId]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const q = filter.trim().toLowerCase();
  const shown = (items || [])
    .filter((r) => {
      const g = r.gstr2b;
      return !q || [g.supplier_gstin, g.supplier_name, g.invoice_no].some((v) => String(v).toLowerCase().includes(q));
    })
    // Same supplier first: that is almost always the invoice the CA is looking for
    .sort((a, b) => Number(b.gstr2b.supplier_gstin === books.supplier_gstin)
      - Number(a.gstr2b.supplier_gstin === books.supplier_gstin));

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog card" role="dialog" aria-modal="true" aria-labelledby="link-title">
        <div className="dialog-head">
          <h2 id="link-title">Link to a GSTR-2B invoice</h2>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
        </div>
        <p className="muted">
          Books invoice <span className="mono">{books.invoice_no}</span> from {books.supplier_name}{' '}
          (<span className="mono">{books.supplier_gstin}</span>), {invDate(books.invoice_date)},
          taxable {money(books.taxable)}. Pick the 2B invoice it corresponds to. Only invoices that
          are missing in books for this run are listed.
        </p>
        <input type="search" placeholder="Filter by GSTIN, supplier or invoice no" value={filter}
          onChange={(e) => setFilter(e.target.value)} aria-label="Filter 2B invoices" autoFocus />
        {error && <p className="error" role="alert">{error}</p>}
        {!items && !error && <p className="muted">Loading…</p>}
        {items && shown.length === 0 && <p className="muted">No unmatched 2B invoices{q ? ' match this filter' : ''}.</p>}
        {shown.length > 0 && (
          <div className="table-scroll dialog-body">
            <table className="table">
              <thead>
                <tr>
                  <th>Supplier</th>
                  <th>GSTIN</th>
                  <th>Invoice no</th>
                  <th>Date</th>
                  <th className="num">Taxable</th>
                  <th className="num">Total tax</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => {
                  const g = r.gstr2b;
                  return (
                    <tr key={r.id} className={g.supplier_gstin === books.supplier_gstin ? 'same-supplier' : ''}>
                      <td>{g.supplier_name}</td>
                      <td className="mono">{g.supplier_gstin}</td>
                      <td className="mono">{g.invoice_no}</td>
                      <td className="nowrap">{invDate(g.invoice_date)}</td>
                      <td className="num">{money(g.taxable)}</td>
                      <td className="num">{money(totalTax(g))}</td>
                      <td>
                        <button type="button" className="btn btn-xs btn-primary" onClick={() => onPick(g.id)}>
                          Link
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
