import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { dateTime, num, period as periodLabel, previousMonth } from '../format.js';
import { STATUS_LABEL } from '../labels.js';
import MappingForm from '../components/MappingForm.jsx';

const UPLOADS = [
  { kind: 'gstr2b', title: 'GSTR-2B', hint: 'JSON downloaded from the GST portal', accept: '.json,application/json' },
  { kind: 'books', title: 'Purchase register', hint: 'Excel (.xlsx) or CSV export from Tally / Excel', accept: '.xlsx,.xls,.csv' },
];

export default function ClientPage() {
  const { clientId } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [runs, setRuns] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [period, setPeriod] = useState(previousMonth());
  const [files, setFiles] = useState({});
  const [uploads, setUploads] = useState({});
  const [mappingColumns, setMappingColumns] = useState(null);
  const [mappingState, setMappingState] = useState({});
  const [runState, setRunState] = useState({});

  useEffect(() => {
    // There is no GET /clients/{id}; the list is small, so pick it out of that
    api('/clients').then((list) => {
      const c = list.find((x) => x.id === clientId);
      if (c) setClient(c);
      else setLoadError('Client not found');
    }, (err) => setLoadError(err.message));
    api(`/clients/${clientId}/runs`).then(setRuns, () => setRuns([]));
  }, [clientId]);

  const setUpload = (kind, state) => setUploads((u) => ({ ...u, [kind]: state }));

  async function upload(kind) {
    const file = files[kind];
    if (!file) return;
    setUpload(kind, { busy: true });
    const form = new FormData();
    form.append('kind', kind);
    form.append('period', period);
    form.append('file', file);
    try {
      const res = await api(`/clients/${clientId}/uploads`, { method: 'POST', form });
      setUpload(kind, { result: { ...res, name: file.name } });
    } catch (err) {
      if (kind === 'books' && err.status === 409 && err.detail && err.detail.columns) {
        setMappingColumns(err.detail.columns);
        setUpload(kind, {});
      } else {
        setUpload(kind, { error: err.message });
      }
    }
  }

  async function saveMapping(mapping) {
    setMappingState({ saving: true });
    try {
      const updated = await api(`/clients/${clientId}/mapping`, { method: 'PUT', json: { mapping } });
      setClient(updated);
      setMappingColumns(null);
      setMappingState({});
      await upload('books');
    } catch (err) {
      setMappingState({ error: err.message });
    }
  }

  async function startRun() {
    setRunState({ busy: true });
    try {
      const run = await api(`/clients/${clientId}/runs`, { method: 'POST', json: { period } });
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setRunState({ error: err.message });
    }
  }

  if (loadError) return <p className="error" role="alert">{loadError} · <Link to="/">Back to clients</Link></p>;
  if (!client) return <p className="muted">Loading…</p>;

  return (
    <>
      <nav className="crumbs"><Link to="/">Clients</Link> / {client.name}</nav>
      <div className="page-head">
        <div>
          <h1>{client.name}</h1>
          <span className="mono muted">{client.gstin}</span>
        </div>
        <label className="field inline">
          <span>Return period</span>
          <input type="month" value={period} required
            onChange={(e) => e.target.value && setPeriod(e.target.value)} aria-label="Return period" />
        </label>
      </div>

      <div className="grid-uploads">
        {UPLOADS.map(({ kind, title, hint, accept }) => {
          const u = uploads[kind] || {};
          return (
            <section key={kind} className="card upload">
              <h2>{title}</h2>
              <p className="muted">{hint}</p>
              <div className="row">
                <input type="file" accept={accept} aria-label={`${title} file`}
                  onChange={(e) => setFiles({ ...files, [kind]: e.target.files[0] })} />
                <button type="button" className="btn" disabled={!files[kind] || u.busy}
                  onClick={() => upload(kind)}>
                  {u.busy ? 'Uploading…' : `Upload for ${periodLabel(period)}`}
                </button>
              </div>
              {u.error && <p className="error" role="alert">{u.error}</p>}
              {u.result && (
                <p className="ok" data-testid={`${kind}-result`}>
                  <strong>{num(u.result.invoice_count)} invoices</strong> read from {u.result.name} for{' '}
                  {periodLabel(u.result.period)}
                </p>
              )}
            </section>
          );
        })}
      </div>

      {mappingColumns && (
        <MappingForm
          columns={mappingColumns}
          onSave={saveMapping}
          onCancel={() => setMappingColumns(null)}
          saving={mappingState.saving}
          error={mappingState.error}
        />
      )}

      <section className="card run-start">
        <div>
          <h2>Reconcile {periodLabel(period)}</h2>
          <p className="muted">Uses the latest GSTR-2B and purchase register uploaded for this period.</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={startRun} disabled={runState.busy}>
          {runState.busy ? 'Starting…' : 'Start reconciliation'}
        </button>
        {runState.error && <p className="error" role="alert">{runState.error}</p>}
      </section>

      <section>
        <h2>Past runs</h2>
        {!runs && <p className="muted">Loading…</p>}
        {runs && runs.length === 0 && <div className="card empty">No runs yet for this client.</div>}
        {runs && runs.length > 0 && (
          <div className="card flush">
            <table className="table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Status</th>
                  <th className="num">Matched</th>
                  <th className="num">Invoices (books / 2B)</th>
                  <th>Model version</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{periodLabel(r.period)}</td>
                    <td><span className={`status status-${r.status}`}>{STATUS_LABEL[r.status] || r.status}</span></td>
                    <td className="num">{r.summary ? num(r.summary.counts?.matched) : '—'}</td>
                    <td className="num">{r.summary ? `${num(r.summary.books)} / ${num(r.summary.gstr2b)}` : '—'}</td>
                    <td className="mono">{r.model_version || '—'}</td>
                    <td>{dateTime(r.created_at)}</td>
                    <td><Link to={`/runs/${r.id}`}>Open</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
