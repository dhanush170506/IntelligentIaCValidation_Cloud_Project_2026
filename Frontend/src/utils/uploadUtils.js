/** Upload helpers shared by the FileUploader and validation flow. */

export const SUPPORTED_EXTENSIONS = ['.tf', '.yaml', '.yml', '.json'];

export function detectFormat(filename) {
  const lower = String(filename || '').toLowerCase();
  if (lower.endsWith('.tf')) return 'terraform';
  if (lower.endsWith('.yaml') || lower.endsWith('.yml')) return 'cloudformation';
  if (lower.endsWith('.json')) return 'cloudformation';
  return 'unknown';
}

export function isSupportedFile(file) {
  if (!file || typeof file.name !== 'string') return false;
  const lower = file.name.toLowerCase();
  return SUPPORTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

export function formatBytesSafe(bytes) {
  if (!Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}
