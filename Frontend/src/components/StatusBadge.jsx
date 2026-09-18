import { STATUS_STYLES, normalizeStatus } from '../utils/severity.js';

/**
 * Status pill for PASS / FAIL / REVIEW_REQUIRED / COMPLETED / BLOCKED ...
 * Unknown statuses (e.g. ERROR from a failed pipeline call) render as plain
 * mono text — never dressed up as a known state.
 */
export default function StatusBadge({ status, className = '' }) {
  if (!status) {
    return <span className={`text-xs text-slate-500 ${className}`}>—</span>;
  }
  const key = normalizeStatus(status);
  const style = STATUS_STYLES[key];
  if (!style) {
    return (
      <span
        className={`inline-flex items-center rounded-full bg-slate-500/10 px-2.5 py-0.5 font-mono text-xs text-slate-300 ${className}`}
      >
        {String(status)}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${style.bg} ${style.border} ${style.text} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
      {style.label}
    </span>
  );
}
