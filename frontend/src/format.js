const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const count = new Intl.NumberFormat('en-IN');
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// The API sends amounts as numbers or decimal strings
export function money(value) {
  if (value === null || value === undefined || value === '') return '—';
  return inr.format(Number(value));
}

export function num(value) {
  return count.format(value || 0);
}

export function totalTax(inv) {
  if (!inv) return null;
  return ['igst', 'cgst', 'sgst', 'cess'].reduce((s, k) => s + Number(inv[k] || 0), 0);
}

// "2025-04-03" -> "03-04-2025"; split by hand so no timezone can shift the day
export function invDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}-${m}-${y}`;
}

export function period(p) {
  if (!p) return '';
  const [y, m] = p.split('-');
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

export function dateTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

export function previousMonth(today = new Date()) {
  const d = new Date(today.getFullYear(), today.getMonth() - 1, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}
