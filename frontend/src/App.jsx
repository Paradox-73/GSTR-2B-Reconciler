import { useEffect, useState } from 'react';
import { Link, Route, Routes } from 'react-router-dom';
import { getToken, setAuthLostHandler, setToken } from './api.js';
import Login from './pages/Login.jsx';
import Clients from './pages/Clients.jsx';
import ClientPage from './pages/ClientPage.jsx';
import RunPage from './pages/RunPage.jsx';

export const APP_VERSION = import.meta.env.VITE_APP_VERSION || 'dev';

export default function App() {
  const [authed, setAuthed] = useState(Boolean(getToken()));

  useEffect(() => {
    setAuthLostHandler(() => setAuthed(false));
  }, []);

  function signOut() {
    setToken(null);
    setAuthed(false);
  }

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">2B</span>
          GSTR-2B Reconciler
        </Link>
        <div className="topbar-right">
          <span className="version" title="Build running in this browser">
            build <strong data-testid="app-version">{APP_VERSION}</strong>
          </span>
          {authed && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={signOut}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <main className="content">
        {authed ? (
          <Routes>
            <Route path="/" element={<Clients />} />
            <Route path="/clients/:clientId" element={<ClientPage />} />
            <Route path="/runs/:runId" element={<RunPage />} />
            <Route path="*" element={<p className="muted">Page not found. <Link to="/">Back to clients</Link></p>} />
          </Routes>
        ) : (
          // Any URL shows the login form; after signing in the same URL renders
          <Login onLogin={() => setAuthed(true)} />
        )}
      </main>

      <footer className="footer">
        GSTR-2B Reconciler · version {APP_VERSION}
      </footer>
    </div>
  );
}
