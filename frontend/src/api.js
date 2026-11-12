const TOKEN_KEY = 'gstr2b_token';

let token = sessionStorage.getItem(TOKEN_KEY);
let onAuthLost = () => {};

export function getToken() {
  return token;
}

export function setToken(value) {
  token = value;
  if (value) sessionStorage.setItem(TOKEN_KEY, value);
  else sessionStorage.removeItem(TOKEN_KEY);
}

export function setAuthLostHandler(fn) {
  onAuthLost = fn;
}

export class ApiError extends Error {
  constructor(status, detail) {
    super(errorText(detail));
    this.status = status;
    this.detail = detail;
  }
}

// FastAPI sends detail as a string, a {message, ...} object, or a list of pydantic errors
export function errorText(detail) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => String(d.msg || '').replace(/^Value error, /, '')).join('; ');
  }
  if (detail && detail.message) return detail.message;
  return 'Request failed';
}

// Pydantic 422s carry loc like ["body", "gstin"]; this maps them to {gstin: "message"}
export function fieldErrors(err) {
  const out = {};
  if (err instanceof ApiError && Array.isArray(err.detail)) {
    for (const d of err.detail) {
      const field = d.loc && d.loc[d.loc.length - 1];
      if (field) out[field] = String(d.msg || '').replace(/^Value error, /, '');
    }
  }
  return out;
}

export async function api(path, { method = 'GET', json, form, raw = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body;
  if (form) body = form;
  else if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  let res;
  try {
    res = await fetch(`/api/v1${path}`, { method, headers, body });
  } catch {
    throw new ApiError(0, 'Cannot reach the server');
  }

  if (res.status === 401 && path !== '/auth/login') {
    setToken(null);
    onAuthLost();
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // non-JSON error body (e.g. a proxy page); keep the status text
    }
    throw new ApiError(res.status, detail);
  }
  return raw ? res : res.json();
}

export async function login(email, password) {
  const { access_token } = await api('/auth/login', { method: 'POST', json: { email, password } });
  setToken(access_token);
}

export async function downloadExport(runId, fallbackName) {
  const res = await api(`/runs/${runId}/export`, { raw: true });
  const blob = await res.blob();
  const disposition = res.headers.get('content-disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = match ? match[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoking in the same tick can cancel the download in some browsers
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
