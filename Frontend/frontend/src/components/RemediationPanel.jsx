import StatusBadge from './StatusBadge.jsx';
import { formatPercent } from '../utils/format.js';
import { Wrench, ShieldAlert } from 'lucide-react';

/**
 * Gated remediation proposals. The pipeline is decision-only (dry_run: true,
 * BLOCKED/APPROVED): nothing is applied to infrastructure, and this UI never
 * offers an apply action.
 */
export default function RemediationPanel({ remediation }) {
  if (!remediation || remediation.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-sm text-slate-500">
        No remediation proposals were returned for this validation.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-md border border-sky-500/25 bg-sky-500/[0.06] px-3 py-2.5 text-xs text-sky-200/90">
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          Proposals are advisory and gate-checked (dry-run). This console does not modify
          infrastructure.
        </span>
      </div>

      {remediation.map((r) => (
        <article key={r.id} className="card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Wrench className="h-4 w-4 text-slate-500" aria-hidden="true" />
            <h3 className="font-mono text-sm font-semibold text-slate-100">{r.resource ?? 'unknown resource'}</h3>
            <StatusBadge status={r.decision} className="ml-auto" />
            {r.dryRun && (
              <span className="rounded border border-white/10 bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-slate-400">
                dry-run
              </span>
            )}
          </div>

          {r.proposedChange && Object.keys(r.proposedChange).length > 0 && (
            <details className="mt-3 rounded-md border border-white/10 bg-night-850/60">
              <summary className="cursor-pointer px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                Proposed change
              </summary>
              <pre className="overflow-x-auto border-t border-white/5 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-slate-300">
{JSON.stringify(r.proposedChange, null, 2)}
              </pre>
            </details>
          )}

          {r.rationale.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {r.rationale.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-white/5 pt-2.5 font-mono text-[11px] text-slate-500">
            <span>confidence: {formatPercent(r.confidence)}</span>
            {r.blastRadiusScore != null && <span>blast radius: {r.blastRadiusScore.toFixed(2)}</span>}
            {r.ranking && (
              <span>
                ranking — security {r.ranking.security?.toFixed(2) ?? '—'} · reliability{' '}
                {r.ranking.reliability?.toFixed(2) ?? '—'} · cost {r.ranking.cost?.toFixed(2) ?? '—'} ·
                risk {r.ranking.risk?.toFixed(2) ?? '—'}
              </span>
            )}
            {r.evidenceIds.length > 0 && <span>evidence: {r.evidenceIds.join(', ')}</span>}
          </div>
        </article>
      ))}
    </div>
  );
}
