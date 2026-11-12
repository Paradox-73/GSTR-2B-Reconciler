import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fieldErrors } from '../api.js';

export default function Clients() {
  const [clients, setClients] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [name, setName] = useState('');
  const [gstin, setGstin] = useState('');
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api('/clients').then(setClients, (err) => setLoadError(err.message));
  }, []);

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    try {
      const c = await api('/clients', { method: 'POST', json: { name, gstin } });
      setClients((list) => [...(list || []), c].sort((a, b) => a.name.localeCompare(b.name)));
      setName('');
      setGstin('');
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors(Object.keys(fields).length ? fields : { form: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-2">
      <section>
        <div className="page-head">
          <h1>Clients</h1>
          {clients && <span className="muted">{clients.length} total</span>}
        </div>
        {loadError && <p className="error" role="alert">{loadError}</p>}
        {!clients && !loadError && <p className="muted">Loading…</p>}
        {clients && clients.length === 0 && (
          <div className="card empty">No clients yet. Add the first one with its GSTIN.</div>
        )}
        {clients && clients.length > 0 && (
          <div className="card flush">
            <table className="table">
              <thead>
                <tr>
                  <th>Client</th>
                  <th>GSTIN</th>
                  <th>Column mapping</th>
                </tr>
              </thead>
              <tbody>
                {clients.map((c) => (
                  <tr key={c.id}>
                    <td><Link to={`/clients/${c.id}`}>{c.name}</Link></td>
                    <td className="mono">{c.gstin}</td>
                    <td>{c.column_mapping ? 'Saved' : <span className="muted">Not set</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <aside>
        <form className="card" onSubmit={create} noValidate>
          <h2>Add client</h2>
          <label className="field">
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={200}
              aria-invalid={Boolean(errors.name)} aria-describedby="name-error" />
          </label>
          {errors.name && <small id="name-error" className="error field-error">{errors.name}</small>}
          <label className="field">
            <span>GSTIN</span>
            <input className="mono" value={gstin} maxLength={15} placeholder="e.g. 29ABCDE1234F1Z5"
              onChange={(e) => setGstin(e.target.value.toUpperCase())} required
              aria-invalid={Boolean(errors.gstin)} aria-describedby="gstin-error" />
          </label>
          {errors.gstin && <small id="gstin-error" className="error field-error" role="alert">{errors.gstin}</small>}
          {errors.form && <p className="error" role="alert">{errors.form}</p>}
          <button type="submit" className="btn btn-primary" disabled={busy || !name || !gstin}>
            {busy ? 'Saving…' : 'Add client'}
          </button>
        </form>
      </aside>
    </div>
  );
}
