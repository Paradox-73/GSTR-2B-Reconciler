// Filing-week spike: many reconciliations at once, to push matcher workers onto the HPA (1 -> 5).
//   python -m datagen --seed 77 --invoices 2000 --out tests/load/data
//   k6 run -e BASE_URL=http://<app> -e EMAIL=... -e PASSWORD=... tests/load/spike.js
// Watch: kubectl -n gstr2b get hpa worker -w
import http from 'k6/http';
import { sleep } from 'k6';
import { Trend } from 'k6/metrics';
import { api, login, ok } from './common.js';

const twoB = open('./data/gstr2b.json');
const books = open('./data/books.csv');
const mapping = open('./data/mapping.json');
const runSeconds = new Trend('run_seconds');

export const options = {
  scenarios: {
    filing_week: {
      executor: 'ramping-vus',
      stages: [
        { duration: '1m', target: Number(__ENV.PEAK || 10) },
        { duration: __ENV.HOLD || '4m', target: Number(__ENV.PEAK || 10) },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    checks: ['rate>0.99'],
    run_seconds: ['p(95)<30'],  // NFR1: 2000 invoices in under 30s, even under load
  },
};

export function setup() {
  const auth = login();
  const gstin = JSON.parse(twoB).data.gstin;
  const rtn = JSON.parse(twoB).data.rtnprd; // MMYYYY
  const period = `${rtn.slice(2)}-${rtn.slice(0, 2)}`;
  const c = api('POST', '/clients', JSON.stringify({ name: `load-${Date.now()}`, gstin }), auth);
  ok(c, 'create client', 201);
  const cid = c.json('id');
  ok(api('PUT', `/clients/${cid}/mapping`, JSON.stringify({ mapping: JSON.parse(mapping) }), auth),
    'mapping');
  for (const [kind, name, body, type] of [['gstr2b', 'gstr2b.json', twoB, 'application/json'],
                                          ['books', 'books.csv', books, 'text/csv']]) {
    const r = api('POST', `/clients/${cid}/uploads`,
      { kind, period, file: http.file(body, name, type) }, auth);
    ok(r, `upload ${kind}`, 201);
  }
  return { auth, cid, period };
}

export default function ({ auth, cid, period }) {
  const started = Date.now();
  const r = api('POST', `/clients/${cid}/runs`, JSON.stringify({ period }), auth);
  if (!ok(r, 'start run', 202)) return;
  const id = r.json('id');
  for (let i = 0; i < 120; i++) {
    sleep(1);
    const s = api('GET', `/runs/${id}`, null, auth, { tags: { name: 'GET /runs/{id}' } });
    const status = s.json('status');
    if (status === 'done' || status === 'failed') {
      ok({ status: status === 'done' ? 200 : 500 }, 'run done');
      runSeconds.add((Date.now() - started) / 1000);
      return;
    }
  }
  ok({ status: 504 }, 'run done');
}
