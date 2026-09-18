import { SEVERITY_STYLES, normalizeSeverity } from '../utils/severity.js';

/** Severity pill: CRITICAL / HIGH / MEDIUM / LOW / INFO (falls back to Info). */
export default function SeverityBadge({ severity, className = '' }) {
  const key = normalizeSeverity(severity);
  const style = SEVERITY_STYLES[key];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wide ${style.bg} ${style.border} ${style.text} ${className}`}
    >
      {style.label}
    </span>
  );
}
