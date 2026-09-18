// ----------------------------------------------------------------------

export function formatCurrency(
  value: string | number | null | undefined,
  currency = 'EUR'
): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(num)) return String(value);

  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: currency || 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num);
}

export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (Number.isNaN(num)) return String(value);

  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(num);
}

export function formatShortHash(hash: string | null | undefined, len = 8): string {
  if (!hash) return '—';
  if (hash.length <= len * 2) return hash;
  return `${hash.slice(0, len)}…${hash.slice(-len)}`;
}

export function formatDateTime(isoString: string | null | undefined): string {
  if (!isoString) return '—';
  try {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat('de-DE', {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(d);
  } catch {
    return isoString;
  }
}

export function getChangeTypeBadgeColor(
  type: string
): 'default' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' {
  const norm = (type || '').toLowerCase();
  if (norm.includes('add')) return 'success';
  if (norm.includes('replac')) return 'info';
  if (norm.includes('remov')) return 'error';
  if (norm.includes('preserv')) return 'default';
  return 'secondary';
}

export function getStatusBadgeColor(
  status: string
): 'default' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' {
  const norm = (status || '').toLowerCase();
  if (['approved', 'completed', 'active'].includes(norm)) return 'success';
  if (['paused', 'awaiting_review', 'needs_review'].includes(norm)) return 'warning';
  if (['failed', 'rejected', 'error', 'conflict'].includes(norm)) return 'error';
  if (['running', 'processing'].includes(norm)) return 'info';
  if (['stale', 'superseded'].includes(norm)) return 'secondary';
  return 'default';
}
