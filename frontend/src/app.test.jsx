import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App.jsx';
import { setToken } from './api.js';
import { money } from './format.js';
import { guessMapping } from './mapping.js';

const CLIENT = { id: 'c1', name: 'Acme Traders', gstin: '29ABCDE1234F1Z5', tolerance: '1.00', column_mapping: null };

// routes: [method, path regex, response | (request) => response]; response = {status, body}
function mockApi(routes) {
  const calls = [];
  vi.stubGlobal('fetch', vi.fn(async (url, opts = {}) => {
    const method = opts.method || 'GET';
    const call = { method, url, body: opts.body, headers: opts.headers || {} };
    calls.push(call);
    const route = routes.find(([m, re]) => m === method && re.test(url));
    if (!route) return new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 });
    const r = typeof route[2] === 'function' ? route[2](call) : route[2];
    return new Response(JSON.stringify(r.body ?? null), {
      status: r.status || 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }));
  return calls;
}

function renderAt(path, { token = 'tok' } = {}) {
  setToken(token);
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <App />
    </MemoryRouter>,
  );
}

const inv = (over) => ({
  id: 'i', supplier_gstin: '29AAAAA0000A1Z5', supplier_name: 'Shree Steel', invoice_no: 'INV-1',
  invoice_date: '2025-04-03', taxable: 100000, igst: 0, cgst: 9000, sgst: 9000, cess: 0,
  itc_available: true, ...over,
});

describe('formatting and mapping', () => {
  it('formats rupees the Indian way', () => {
    expect(money(123456)).toBe('₹1,23,456.00');
    expect(money('1234567.5')).toBe('₹12,34,567.50');
  });

  it('guesses the generator headers and common variants', () => {
    const headers = ['Date', 'Particulars', 'GSTIN/UIN', 'Bill No', 'Taxable Value', 'IGST', 'CGST', 'SGST', 'Cess'];
    expect(guessMapping(headers)).toEqual({
      invoice_date: 'Date', supplier_name: 'Particulars', supplier_gstin: 'GSTIN/UIN', invoice_no: 'Bill No',
      taxable: 'Taxable Value', igst: 'IGST', cgst: 'CGST', sgst: 'SGST', cess: 'Cess',
    });
    const other = guessMapping(['Supplier GSTIN', 'Supplier Name', 'Invoice Number', 'Invoice Date',
      'Taxable Amount', 'Integrated Tax (IGST)', 'Central Tax', 'State/UT Tax']);
    expect(other).toMatchObject({ supplier_gstin: 'Supplier GSTIN', invoice_no: 'Invoice Number',
      invoice_date: 'Invoice Date', taxable: 'Taxable Amount', igst: 'Integrated Tax (IGST)', cgst: 'Central Tax' });
    expect(other.cess).toBeUndefined();
  });
});

describe('auth', () => {
  it('logs in, keeps the token in sessionStorage and shows clients', async () => {
    const calls = mockApi([
      ['POST', /\/api\/v1\/auth\/login$/, { body: { access_token: 'abc', token_type: 'bearer' } }],
      ['GET', /\/api\/v1\/clients$/, { body: [CLIENT] }],
    ]);
    renderAt('/', { token: null });
    await userEvent.type(screen.getByLabelText('Email'), 'ca@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'pw');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('link', { name: 'Acme Traders' })).toBeInTheDocument();
    expect(sessionStorage.getItem('gstr2b_token')).toBe('abc');
    expect(calls[1].headers.Authorization).toBe('Bearer abc');
  });

  it('goes back to the login form on a 401', async () => {
    mockApi([['GET', /\/clients$/, { status: 401, body: { detail: 'invalid or expired token' } }]]);
    renderAt('/');
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
    expect(sessionStorage.getItem('gstr2b_token')).toBeNull();
  });

  it('shows the build version in the header', () => {
    mockApi([['GET', /\/clients$/, { body: [] }]]);
    renderAt('/');
    expect(screen.getByTestId('app-version')).toHaveTextContent(/\S/);
  });
});

describe('clients', () => {
  it('shows the API GSTIN error next to the field', async () => {
    mockApi([
      ['GET', /\/clients$/, { body: [] }],
      ['POST', /\/clients$/, { status: 422, body: { detail: [{ loc: ['body', 'gstin'], msg: 'Value error, not a valid GSTIN (format or check character is wrong)', type: 'value_error' }] } }],
    ]);
    renderAt('/');
    await userEvent.type(screen.getByLabelText('Name'), 'Bad Co');
    await userEvent.type(screen.getByLabelText('GSTIN'), '29abc');
    await userEvent.click(screen.getByRole('button', { name: 'Add client' }));
    expect(await screen.findByText('not a valid GSTIN (format or check character is wrong)')).toBeInTheDocument();
    expect(screen.getByLabelText('GSTIN')).toHaveValue('29ABC');
    expect(screen.getByLabelText('GSTIN')).toHaveAccessibleDescription(/not a valid GSTIN/);
  });
});

describe('client page uploads', () => {
  const HEADERS = ['Date', 'Particulars', 'GSTIN/UIN', 'Bill No', 'Taxable Value', 'IGST', 'CGST', 'SGST'];
  const booksUpload = { id: 'u1', kind: 'books', period: '2025-04', original_name: 'register.xlsx', invoice_count: 58, uploaded_at: '2025-05-02T09:30:00' };

  async function uploadBooks() {
    fireEvent.change(await screen.findByLabelText('Return period'), { target: { value: '2025-04' } });
    await userEvent.upload(screen.getByLabelText('Purchase register file'), new File(['x'], 'register.xlsx'));
    const books = screen.getByRole('heading', { name: 'Purchase register' }).closest('section');
    await userEvent.click(within(books).getByRole('button', { name: 'Upload for Apr 2025' }));
  }

  it('shows the latest upload of each kind for the period and refetches when the period changes', async () => {
    const calls = mockApi([
      ['GET', /\/clients\/c1$/, { body: CLIENT }],
      ['GET', /\/clients\/c1\/runs$/, { body: [] }],
      ['GET', /\/clients\/c1\/uploads\?period=2025-04$/, { body: [
        booksUpload,
        { id: 'u0', kind: 'books', period: '2025-04', original_name: 'old.xlsx', invoice_count: 50, uploaded_at: '2025-05-01T09:00:00' },
        { id: 'g1', kind: 'gstr2b', period: '2025-04', original_name: '2b.json', invoice_count: 41, uploaded_at: '2025-05-01T08:00:00' },
      ] }],
      ['GET', /\/clients\/c1\/uploads\?period=2025-03$/, { body: [] }],
    ]);
    renderAt('/clients/c1');
    expect(await screen.findByRole('heading', { name: 'Acme Traders' })).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith('/api/v1/clients'))).toBe(false);

    fireEvent.change(screen.getByLabelText('Return period'), { target: { value: '2025-04' } });
    expect(await screen.findByTestId('books-result')).toHaveTextContent(/58 invoices read from register\.xlsx for Apr 2025 · uploaded \S/);
    expect(screen.getByTestId('gstr2b-result')).toHaveTextContent('41 invoices read from 2b.json');

    fireEvent.change(screen.getByLabelText('Return period'), { target: { value: '2025-03' } });
    await waitFor(() => expect(screen.queryByTestId('books-result')).not.toBeInTheDocument());
    expect(screen.queryByTestId('gstr2b-result')).not.toBeInTheDocument();
  });

  it('asks for a column mapping on 409, saves it and retries the upload', async () => {
    let booksUploads = 0;
    const calls = mockApi([
      ['GET', /\/clients\/c1$/, { body: CLIENT }],
      ['GET', /\/clients\/c1\/runs$/, { body: [] }],
      ['GET', /\/clients\/c1\/uploads\?/, () => ({ body: booksUploads > 1 ? [booksUpload] : [] })],
      ['POST', /\/clients\/c1\/uploads$/, () => {
        booksUploads += 1;
        return booksUploads === 1
          ? { status: 409, body: { detail: { message: 'save a column mapping for this client first', columns: HEADERS } } }
          : { status: 201, body: { id: 'u1', kind: 'books', period: '2025-04', invoice_count: 58, sha256: 'x' } };
      }],
      ['PUT', /\/clients\/c1\/mapping$/, (c) => ({ body: { ...CLIENT, column_mapping: JSON.parse(c.body).mapping } })],
    ]);
    renderAt('/clients/c1');
    await uploadBooks();

    const form = await screen.findByRole('form', { name: 'Column mapping' });
    expect(within(form).getByText('save a column mapping for this client first')).toBeInTheDocument();
    expect(within(form).getByLabelText('Invoice number')).toHaveValue('Bill No');
    expect(within(form).getByLabelText('Supplier GSTIN')).toHaveValue('GSTIN/UIN');
    await userEvent.click(within(form).getByRole('button', { name: 'Save mapping and upload' }));

    expect(await screen.findByTestId('books-result')).toHaveTextContent('58 invoices read from register.xlsx');
    const put = calls.find((c) => c.method === 'PUT');
    expect(JSON.parse(put.body).mapping).toEqual({
      invoice_date: 'Date', supplier_name: 'Particulars', supplier_gstin: 'GSTIN/UIN', invoice_no: 'Bill No',
      taxable: 'Taxable Value', igst: 'IGST', cgst: 'CGST', sgst: 'SGST',
    });
    const uploads = calls.filter((c) => c.method === 'POST' && c.url.endsWith('/uploads'));
    expect(uploads).toHaveLength(2);
    expect(uploads[1].body.get('period')).toBe('2025-04');
    expect(uploads[1].body.get('kind')).toBe('books');
  });

  it('reopens the mapping form when the saved mapping no longer fits, keeping saved choices that still exist', async () => {
    const saved = {
      supplier_gstin: 'Party GSTIN', supplier_name: 'Particulars', invoice_no: 'Voucher No', invoice_date: 'Date',
      taxable: 'Taxable Value', igst: 'IGST', cgst: 'CGST', sgst: 'SGST',
    };
    const message = "this file's columns don't match the saved mapping (missing: Voucher No)";
    let booksUploads = 0;
    const calls = mockApi([
      ['GET', /\/clients\/c1$/, { body: { ...CLIENT, column_mapping: saved } }],
      ['GET', /\/clients\/c1\/runs$/, { body: [] }],
      ['GET', /\/clients\/c1\/uploads\?/, { body: [] }],
      ['POST', /\/clients\/c1\/uploads$/, () => {
        booksUploads += 1;
        return booksUploads === 1
          ? { status: 409, body: { detail: { message, columns: ['Party GSTIN', ...HEADERS] } } }
          : { status: 201, body: { id: 'u1', kind: 'books', period: '2025-04', invoice_count: 58, sha256: 'x' } };
      }],
      ['PUT', /\/clients\/c1\/mapping$/, (c) => ({ body: { ...CLIENT, column_mapping: JSON.parse(c.body).mapping } })],
    ]);
    renderAt('/clients/c1');
    await uploadBooks();

    const form = await screen.findByRole('form', { name: 'Column mapping' });
    expect(within(form).getByText(message)).toBeInTheDocument();
    // The guess would be GSTIN/UIN; the saved header is still in the file, so it wins
    expect(within(form).getByLabelText('Supplier GSTIN')).toHaveValue('Party GSTIN');
    // The saved header is gone from the file, so the guess fills it
    expect(within(form).getByLabelText('Invoice number')).toHaveValue('Bill No');
    await userEvent.click(within(form).getByRole('button', { name: 'Save mapping and upload' }));

    await waitFor(() => expect(screen.queryByRole('form', { name: 'Column mapping' })).not.toBeInTheDocument());
    expect(JSON.parse(calls.find((c) => c.method === 'PUT').body).mapping).toEqual({ ...saved, invoice_no: 'Bill No' });
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST' && c.url.endsWith('/uploads'))).toHaveLength(2));
  });
});

describe('run page', () => {
  const RUN = {
    id: 'r1', client_id: 'c1', period: '2025-04', status: 'done', model_version: 'exact-v1',
    summary: { counts: { matched: 40, mismatch: 1, missing_in_2b: 1 }, books: 42, gstr2b: 41 },
    error: null, created_at: '2025-05-01T10:00:00', started_at: null, finished_at: '2025-05-01T10:00:02',
  };
  const mismatch = {
    id: 'm1', category: 'mismatch', reason_codes: ['VALUE_DIFF', 'TAX_DIFF'], score: null,
    books: inv({ id: 'b1' }), gstr2b: inv({ id: 'g1', taxable: 90000, cgst: 8100, sgst: 8100 }), decision: null,
  };
  const missing = {
    id: 'm2', category: 'missing_in_2b', reason_codes: ['MISSING_IN_2B'], score: null,
    books: inv({ id: 'b2', invoice_no: 'INV-9' }), gstr2b: null, decision: null,
  };
  const orphan = {
    id: 'm3', category: 'missing_in_books', reason_codes: ['MISSING_IN_BOOKS'], score: null,
    books: null, gstr2b: inv({ id: 'g9', invoice_no: 'INV/9' }), decision: null,
  };

  it('polls until done, then shows tiles, results, and records a decision', async () => {
    let polls = 0;
    const calls = mockApi([
      ['GET', /\/runs\/r1$/, () => {
        polls += 1;
        return { body: polls === 1 ? { ...RUN, status: 'running', summary: null, model_version: null } : RUN };
      }],
      ['GET', /\/runs\/r1\/results\?/, { body: { total: 2, page: 1, page_size: 50, items: [mismatch, missing] } }],
      ['POST', /\/results\/m1\/decision$/, { status: 201, body: { id: 'd1', decision: 'accept' } }],
    ]);
    renderAt('/runs/r1');
    expect(await screen.findByRole('status')).toHaveTextContent(/Matching invoices/);
    await waitFor(() => expect(screen.getByTestId('model-version')).toHaveTextContent('exact-v1'), { timeout: 4000 });

    expect(screen.getByRole('button', { name: /40\s*Matched/ })).toBeInTheDocument();
    const rows = await screen.findAllByTestId('result-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText('₹90,000.00')).toHaveClass('diff');
    expect(within(rows[0]).getByText('VALUE_DIFF')).toHaveAttribute('title', 'Taxable value differs');

    await userEvent.click(within(rows[0]).getByRole('button', { name: 'Accept' }));
    expect(await within(rows[0]).findByText('Accepted')).toBeInTheDocument();
    const post = calls.find((c) => c.method === 'POST');
    expect(JSON.parse(post.body)).toEqual({ decision: 'accept' });

    // Endpoints that don't exist yet degrade to a message
    expect(await screen.findByText("Vendor notes aren't available on this server yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Export to Excel' }));
    expect(await screen.findByText("Excel export isn't available on this server yet.")).toBeInTheDocument();
  }, 10000);

  it('links a missing-in-2B row to a 2B invoice from the same run', async () => {
    const calls = mockApi([
      ['GET', /\/runs\/r1$/, { body: RUN }],
      ['GET', /category=missing_in_2b/, { body: { total: 1, page: 1, page_size: 50, items: [missing] } }],
      ['GET', /category=missing_in_books/, { body: { total: 1, page: 1, page_size: 500, items: [orphan] } }],
      ['POST', /\/results\/m2\/decision$/, { status: 201, body: { id: 'd2', decision: 'link' } }],
      ['GET', /vendor-notes$/, { body: [{ supplier_gstin: '29AAAAA0000A1Z5', supplier_name: 'Shree Steel', body: 'Please file INV-9' }] }],
      ['GET', /\/clients\/c1$/, { body: CLIENT }],
    ]);
    renderAt('/runs/r1?category=missing_in_2b');
    expect(await screen.findByText('Please file INV-9')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Acme Traders' })).toHaveAttribute('href', '/clients/c1');
    await userEvent.click(await screen.findByRole('button', { name: 'Link to 2B invoice' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Link' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText('Linked')).toBeInTheDocument();
    const post = calls.find((c) => c.method === 'POST');
    expect(JSON.parse(post.body)).toEqual({ decision: 'link', linked_invoice_id: 'g9' });
  });
});
