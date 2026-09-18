/** Formatting helpers shared across pages and components. */

export function formatScore(value, { fallback = '—' } = {}) {
  if (value == null || Number.isNaN(Number(value))) return fallback;
  return String(Math.round(Number(value)));
}

/**
 * Format a confidence/ratio value as a percentage string.
 * The ML contract expresses confidence as a 0..1 float; use
 * { fraction: false } for values already on a 0..100 scale.
 */
export function formatPercent(value, { fraction = true, fallback = '—' } = {}) {
  const n = Number(value);
  if (value == null || Number.isNaN(n)) return fallback;
  return `${Math.round(n * (fraction ? 100 : 1))}%`;
}

export function formatDateTime(value) {
  if (!value) return '—';
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return String(value);
  }
}

export function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
