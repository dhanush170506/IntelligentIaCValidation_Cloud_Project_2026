import SeverityBadge from './SeverityBadge.jsx';

/** Detailed finding card used in the security tab (severity-grouped). */
export default function FindingCard({ finding }) {
  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={finding.severity} />
        {finding.category && (
          <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-[11px] text-slate-400">
            {finding.category}
          </span>
        )}
        {finding.resource && (
          <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-[11px] text-signal/80">
            {finding.resource}
          </span>
        )}
      </div>
      <p className="mt-2.5 text-sm leading-relaxed text-slate-200">{finding.message ?? '—'}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
        {finding.ruleId && <span className="font-mono">rule: {finding.ruleId}</span>}
        {finding.confidence != null && (
          <span className="font-mono">confidence: {Math.round(finding.confidence * 100)}%</span>
        )}
        {finding.evidenceIds.length > 0 && (
          <span className="font-mono">evidence: {finding.evidenceIds.join(', ')}</span>
        )}
      </div>
    </article>
  );
}
