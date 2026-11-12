import { useEffect, useState } from 'react';
import { api } from '../api.js';

// navigator.clipboard only exists on https or localhost; the demo cluster may be plain http
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand('copy');
  area.remove();
  if (!ok) throw new Error('copy blocked');
}

export default function VendorNotes({ runId }) {
  const [notes, setNotes] = useState(null);
  const [message, setMessage] = useState('');
  const [copied, setCopied] = useState(null);

  useEffect(() => {
    api(`/runs/${runId}/vendor-notes`).then(setNotes, (err) => {
      setMessage(err.status === 404 ? "Vendor notes aren't available on this server yet." : err.message);
    });
  }, [runId]);

  async function copy(note, i) {
    try {
      await copyText(note.body);
      setCopied(i);
    } catch {
      setCopied(null);
      setMessage('This browser blocked copying. Select the note text and copy it by hand.');
    }
  }

  return (
    <section className="notes">
      <div className="page-head">
        <h2>Vendor follow-up notes</h2>
        {notes && <span className="muted">{notes.length} suppliers</span>}
      </div>
      {message && <p className="muted" role="status">{message}</p>}
      {!notes && !message && <p className="muted">Loading…</p>}
      {notes && notes.length === 0 && (
        <div className="card empty">No supplier needs a follow-up for this run.</div>
      )}
      {notes && notes.length > 0 && (
        <div className="notes-list">
          {notes.map((n, i) => (
            <article key={`${n.supplier_gstin}-${i}`} className="card note">
              <div className="note-head">
                <div>
                  <strong>{n.supplier_name}</strong>
                  <div className="mono muted">{n.supplier_gstin}</div>
                </div>
                <button type="button" className="btn btn-sm" onClick={() => copy(n, i)}>
                  {copied === i ? 'Copied' : 'Copy'}
                </button>
              </div>
              <pre className="note-body">{n.body}</pre>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
