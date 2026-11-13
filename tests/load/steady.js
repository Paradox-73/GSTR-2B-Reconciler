// Steady traffic to run while a rollout happens (DESIGN.md 13.6). Pass = zero failed requests.
//   k6 run -e BASE_URL=http://<app> -e EMAIL=... -e PASSWORD=... tests/load/steady.js
// Start it, then trigger the deploy (push a commit or `kubectl rollout restart deploy/api`).
import http from 'k6/http';
import { BASE, api, login, ok } from './common.js';

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 20), timeUnit: '1s',
      duration: __ENV.DURATION || '3m',
      preAllocatedVUs: 20, maxVUs: 60,
    },
  },
  thresholds: {
    http_req_failed: ['rate==0'],        // the zero-downtime claim
    http_req_duration: ['p(95)<1000'],
  },
};

export function setup() {
  return { auth: login() };
}

export default function ({ auth }) {
  ok(http.get(`${BASE}/`), 'ui');
  ok(api('GET', '/clients', null, auth), 'clients');
}
