import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { invDate, money, num, totalTax } from '../format.js';
import { CATEGORY_LABEL, DECISION_LABEL, REASONS, REVIEWABLE } from '../labels.js';
import LinkPicker from './LinkPicker.jsx';

const PAGE_SIZE = 50;
const CENT = 0.005;

// Which fields differ between the two sides; only meaningful when both exist
export function differences(b, g) {
  if (!b || !g) return {};
  const amt = (x) => Number(x || 0);
  const heads = ['igst', 'cgst', 'sgst', 'cess'];
  return {
    gstin: b.supplier_gstin !== g.supplier_gstin,
    invoice_no: b.invoice_no !== g.invoice_no,
    date: String(b.invoice_date) !== String(g.invoice_date),
    taxable: Math.abs(amt(b.taxable) - amt(g.taxable)) >= CENT,
    tax: heads.some((k) => Math.abs(amt(b[k]) - amt(g[k])) >= CENT),
  };
}

function taxSplit(inv) {
  return `IGST ${money(inv.igst)} · CGST ${money(inv.cgst)} · SGST ${money(inv.sgst)} · Cess ${money(inv.cess)}`;
}

function SideCells({ inv, diff }) {
  if (!inv) {
    return <td colSpan={5} className="side-empty">Not present</td>;
  }
  const cls = (on, base = '') => `${base}${on ? ' diff' : ''}`.trim();
  return (
    <>
      <td className={cls(diff.gstin, 'mono')}>{inv.supplier_gstin}</td>
      <td className={cls(diff.invoice_no, 'mono')}>{inv.invoice_no}</td>
      <td className={cls(diff.date, 'nowrap')}>{invDate(inv.invoice_date)}</td>
      <td className={cls(diff.taxable, 'num')}>{money(inv.taxable)}</td>
      <td className={cls(diff.tax, 'num')} title={taxSplit(inv)}>{money(totalTax(inv))}</td>
    </>
  );
}

export default function ResultsTable({ runId, category, page, onPage }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [linking, setLinking] = useState(null);
  const [busyId, setBusyId] = useState(null);

  useEffect(() => {
    let stale = false;
    setData(null);
    setError('');
    const q = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (category) q.set('category', category);
    api(`/runs/${runId}/results?${q}`).then(
      (d) => !stale && setData(d),
      (err) => !stale && setError(err.message),
    );
    return () => {
      stale = true;
    };
  }, [runId, category, page]);

  function recorded(resultId, decision) {
    setData((d) => ({
      ...d,
      items: d.items.map((it) => (it.id === resultId ? { ...it, decision } : it)),
    }));
  }

  async function decide(result, decision, linkedInvoiceId) {
    setBusyId(result.id);
    setError('');
    try {
      const json = { decision };
      if (linkedInvoiceId) json.linked_invoice_id = linkedInvoiceId;
      await api(`/results/${result.id}/decision`, { method: 'POST', json });
      recorded(result.id, {
        decision,
        decided_at: new Date().toISOString(),
        linked_invoice_id: linkedInvoiceId || null,
      });
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setBusyId(null);
    }
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const first = data && data.total ? (page - 1) * PAGE_SIZE + 1 : 0;
  const last = data ? Math.min(page * PAGE_SIZE, data.total) : 0;

  return (
    <section className="results">
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p className="muted">Loading results…</p>}
      {data && data.total === 0 && (
        <div className="card empty">No results in {category ? CATEGORY_LABEL[category] : 'this run'}.</div>
      )}
      {data && data.total > 0 && (
        <div className="card flush">
          <div className="table-scroll">
            <table className="table results-table">
              <thead>
                <tr className="group-row">
                  <th colSpan={category ? 1 : 2} />
                  <th colSpan={5} className="group">Purchase register</th>
                  <th colSpan={5} className="group">GSTR-2B</th>
                  <th colSpan={3} />
                </tr>
                <tr>
                  {!category && <th>Category</th>}
                  <th>Supplier</th>
                  <th>GSTIN</th>
                  <th>Invoice no</th>
                  <th>Date</th>
                  <th className="num">Taxable</th>
                  <th className="num">Total tax</th>
                  <th>GSTIN</th>
                  <th>Invoice no</th>
                  <th>Date</th>
                  <th className="num">Taxable</th>
                  <th className="num">Total tax</th>
                  <th>Reasons</th>
                  <th className="num">Score</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => {
                  const diff = differences(r.books, r.gstr2b);
                  const supplier = (r.books || r.gstr2b || {}).supplier_name;
                  return (
                    <tr key={r.id} data-testid="result-row">
                      {!category && (
                        <td><span className={`cat cat-${r.category}`}>{CATEGORY_LABEL[r.category] || r.category}</span></td>
                      )}
                      <td className="supplier" title={supplier}>{supplier || '—'}</td>
                      <SideCells inv={r.books} diff={diff} />
                      <SideCells inv={r.gstr2b} diff={diff} />
                      <td>
                        <div className="chips">
                          {(r.reason_codes || []).map((code) => (
                            <span key={code} className="chip" title={REASONS[code] || code}>{code}</span>
                          ))}
                        </div>
                      </td>
                      <td className="num">{r.score === null || r.score === undefined ? '—' : Number(r.score).toFixed(2)}</td>
                      <td className="review">
                        <ReviewCell result={r} busy={busyId === r.id} onDecide={decide}
                          onLink={() => setLinking(r)} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span className="muted">
              Showing {num(first)}–{num(last)} of {num(data.total)}
            </span>
            <button type="button" className="btn btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
              Previous
            </button>
            <span>Page {page} of {pages}</span>
            <button type="button" className="btn btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
              Next
            </button>
          </div>
        </div>
      )}

      {linking && (
        <LinkPicker
          runId={runId}
          result={linking}
          onClose={() => setLinking(null)}
          onPick={async (invoiceId) => {
            if (await decide(linking, 'link', invoiceId)) setLinking(null);
          }}
        />
      )}
    </section>
  );
}

function ReviewCell({ result, busy, onDecide, onLink }) {
  const current = result.decision && result.decision.decision;
  const badge = current && (
    <span className={`decision decision-${current}`}>{DECISION_LABEL[current] || current}</span>
  );

  if (REVIEWABLE.has(result.category)) {
    return (
      <div className="review-actions">
        {badge}
        <button type="button" className="btn btn-xs btn-accept" aria-pressed={current === 'accept'}
          disabled={busy || current === 'accept'} onClick={() => onDecide(result, 'accept')}>
          Accept
        </button>
        <button type="button" className="btn btn-xs btn-reject" aria-pressed={current === 'reject'}
          disabled={busy || current === 'reject'} onClick={() => onDecide(result, 'reject')}>
          Reject
        </button>
      </div>
    );
  }
  if (result.category === 'missing_in_2b') {
    return (
      <div className="review-actions">
        {badge}
        <button type="button" className="btn btn-xs" disabled={busy} onClick={onLink}>
          {current === 'link' ? 'Change link' : 'Link to 2B invoice'}
        </button>
      </div>
    );
  }
  return badge || null;
}
