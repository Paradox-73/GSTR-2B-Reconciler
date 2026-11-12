import http from 'k6/http';
import { check, fail } from 'k6';

export const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const API = `${BASE}/api/v1`;

export function login() {
  const r = http.post(`${API}/auth/login`,
    JSON.stringify({ email: __ENV.EMAIL, password: __ENV.PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } });
  if (r.status !== 200) fail(`login failed: ${r.status} ${r.body}`);
  return { Authorization: `Bearer ${r.json('access_token')}` };
}

export function api(method, path, body, auth, params = {}) {
  const headers = { ...auth, ...(params.headers || {}) };
  if (body && typeof body === 'string') headers['Content-Type'] = 'application/json';
  return http.request(method, `${API}${path}`, body || null, { ...params, headers });
}

export function ok(r, name, status = 200) {
  return check(r, { [`${name} ${status}`]: (x) => x.status === status });
}
