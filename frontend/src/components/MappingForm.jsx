import { useState } from 'react';
import { guessMapping, LOGICAL_COLUMNS } from '../mapping.js';

export default function MappingForm({ columns, onSave, onCancel, saving, error }) {
  const [guessed] = useState(() => guessMapping(columns));
  const [values, setValues] = useState(guessed);
  const missing = LOGICAL_COLUMNS.filter((c) => c.required && !values[c.key]);

  function submit(e) {
    e.preventDefault();
    // Unmapped optional columns are left out: the parser looks up every header it is given
    const mapping = Object.fromEntries(Object.entries(values).filter(([, v]) => v));
    onSave(mapping);
  }

  return (
    <form className="card mapping" onSubmit={submit} aria-label="Column mapping">
      <h2>Map purchase register columns</h2>
      <p className="muted">
        This client has no column mapping yet. Pick which column in the file holds each field.
        Guesses are pre-filled from the header names; check them before saving. The mapping is
        saved for this client and the upload is retried.
      </p>
      <div className="mapping-grid">
        {LOGICAL_COLUMNS.map((col) => (
          <label key={col.key} className="field">
            <span>
              {col.label}
              {!col.required && <em className="muted"> (optional)</em>}
              {guessed[col.key] && values[col.key] === guessed[col.key] && (
                <em className="tag">guessed</em>
              )}
            </span>
            <select
              value={values[col.key] || ''}
              onChange={(e) => setValues({ ...values, [col.key]: e.target.value })}
              aria-label={col.label}
            >
              <option value="">{col.required ? '— choose a column —' : '— not in this file —'}</option>
              {columns.map((h) => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          </label>
        ))}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit" className="btn btn-primary" disabled={saving || missing.length > 0}>
          {saving ? 'Saving…' : 'Save mapping and upload'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel}>Cancel</button>
        {missing.length > 0 && (
          <span className="muted">Still to map: {missing.map((c) => c.label).join(', ')}</span>
        )}
      </div>
    </form>
  );
}
