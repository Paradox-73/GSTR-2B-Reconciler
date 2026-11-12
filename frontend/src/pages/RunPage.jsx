import { useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { api, downloadExport } from '../api.js';
import { dateTime, num, period as periodLabel } from '../format.js';
import { CATEGORIES, STATUS_LABEL } from '../labels.js';
import ResultsTable from '../components/ResultsTable.jsx';
import VendorNotes from '../components/VendorNotes.jsx';

const POLL_MS = 1500;

export default function RunPage() {
  const { runId } = useParams();
  const [run, setRun] = useState(null);
  const [clientName, setClientName] = useState('');
  const [error, setError] = useState('');
  const [params, setParams] = useSearchParams();
  const category = params.get('category') || '';
  const page = Number(params.get('page')) || 1;

  useEffect(() => {
    let timer;
    let stopped = false;
    async function poll() {
      try {
        const r = await api(`/runs/${runId}`);
        if (stopped) return;
        setRun(r);
        if (r.status === 'queued' || r.status === 'running') timer = setTimeout(poll, POLL_MS);
      } catch (err) {
        if (!stopped) setError(err.message);
      }
    }
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [runId]);

  const clientId = run && run.client_id;
  useEffect(() => {
    if (!clientId) return;
    api(`/clients/${clientId}`).then((c) => setClientName(c.name), () => {});
  }, [clientId]);

  function show(next) {
    const p = {};
    if (next.category) p.category = next.category;
    if (next.page > 1) p.page = String(next.page);
    setParams(p, { replace: true });
  }

  if (error) return <p className="error" role="alert">{error} · <Link to="/">Back to clients</Link></p>;
  if (!run) return <p className="muted">Loading…</p>;

  const counts = (run.summary && run.summary.counts) || {};
  const total = Object.values(counts).reduce((s, n) => s + n, 0);

  return (
    <>
      <nav className="crumbs">
        <Link to="/">Clients</Link> / <Link to={`/clients/${run.client_id}`}>{clientName || 'Client'}</Link> / Run
      </nav>
      <div className="page-head">
        <div>
          <h1>Reconciliation · {periodLabel(run.period)}</h1>
          <div className="meta">
            <span className={`status status-${run.status}`}>{STATUS_LABEL[run.status] || run.status}</span>
            <span>Model <strong className="mono" data-testid="model-version">{run.model_version || '—'}</strong></span>
            {run.summary && (
              <span>{num(run.summary.books)} invoices in books · {num(run.summary.gstr2b)} in 2B</span>
            )}
            <span>Created {dateTime(run.created_at)}</span>
            {run.finished_at && <span>Finished {dateTime(run.finished_at)}</span>}
          </div>
        </div>
        {run.status === 'done' && <ExportButton run={run} />}
      </div>

      {(run.status === 'queued' || run.status === 'running') && (
        <div className="card progress" role="status">
          <div className="progress-bar"><span /></div>
          <p>
            {run.status === 'queued'
              ? 'Queued. Waiting for a worker to pick up this run…'
              : 'Matching invoices. This page updates on its own.'}
          </p>
        </div>
      )}

      {run.status === 'failed' && (
        <div className="card error-card" role="alert">
          The run failed{run.error ? ` (${run.error})` : ''}. Check the uploaded files and start a new run.
        </div>
      )}

      {run.status === 'done' && (
        <>
          <div className="tiles" role="group" aria-label="Filter by category">
            <button type="button" aria-pressed={!category}
              className={`tile tile-all${!category ? ' active' : ''}`} onClick={() => show({})}>
              <span className="tile-count">{num(total)}</span>
              <span className="tile-label">All results</span>
            </button>
            {CATEGORIES.map((c) => (
              <button key={c.key} type="button" aria-pressed={category === c.key}
                className={`tile tile-${c.key}${category === c.key ? ' active' : ''}`}
                onClick={() => show({ category: c.key })}>
                <span className="tile-count">{num(counts[c.key])}</span>
                <span className="tile-label">{c.label}</span>
              </button>
            ))}
          </div>

          <ResultsTable runId={runId} category={category} page={page}
            onPage={(p) => show({ category, page: p })} />

          <VendorNotes runId={runId} />
        </>
      )}
    </>
  );
}

function ExportButton({ run }) {
  const [state, setState] = useState({});

  async function go() {
    setState({ busy: true });
    try {
      await downloadExport(run.id, `gstr2b-reconciliation-${run.period}.xlsx`);
      setState({});
    } catch (err) {
      setState({ error: err.status === 404 ? "Excel export isn't available on this server yet." : err.message });
    }
  }

  return (
    <div className="export">
      <button type="button" className="btn btn-primary" onClick={go} disabled={state.busy}>
        {state.busy ? 'Preparing…' : 'Export to Excel'}
      </button>
      {state.error && <small className="error" role="alert">{state.error}</small>}
    </div>
  );
}
