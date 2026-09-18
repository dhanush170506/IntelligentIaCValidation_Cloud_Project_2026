import SeverityBadge from './SeverityBadge.jsx';
import { formatPercent } from '../utils/format.js';
import { GitBranch, Radio } from 'lucide-react';

/** Per-resource runtime drift assessment with desired/observed state disclosure. */
export default function DriftPanel({ drift }) {
  if (!drift || drift.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-sm text-slate-500">
        Runtime drift information is not available for this validation.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {drift.map((d) => (
        <article key={d.id} className="card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <GitBranch className="h-4 w-4 text-slate-500" aria-hidden="true" />
            <h3 className="font-mono text-sm font-semibold text-slate-100">{d.resource ?? 'unknown resource'}</h3>
            <SeverityBadge severity={d.severity} />
            {d.category && (
              <span className="rounded bg-white/5 px-2 py-0.5 font-mono text-[11px] text-slate-400">
                {d.category}
              </span>
            )}
            <span className="ml-auto font-mono text-xs text-slate-400">
              drift score {d.score ?? '—'} · confidence {formatPercent(d.confidence)}
            </span>
          </div>

          {d.rationale.length > 0 && (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {d.rationale.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}

          {(d.desired || d.observed) && (
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <details className="rounded-md border border-white/10 bg-night-850/60">
                <summary className="cursor-pointer px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Desired state (IaC)
                </summary>
                <pre className="overflow-x-auto border-t border-white/5 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-slate-300">
{JSON.stringify(d.desired?.properties ?? d.desired, null, 2)}
                </pre>
              </details>
              {d.observed ? (
                <details className="rounded-md border border-white/10 bg-night-850/60">
                  <summary className="cursor-pointer px-3 py-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Observed runtime state
                  </summary>
                  <pre className="overflow-x-auto border-t border-white/5 px-3 py-2.5 font-mono text-[11px] leading-relaxed text-slate-300">
{JSON.stringify(d.observed, null, 2)}
                  </pre>
                </details>
              ) : (
                <div className="flex items-center gap-2 rounded-md border border-white/5 bg-white/[0.02] px-3 py-2.5 text-xs text-slate-500">
                  <Radio className="h-3.5 w-3.5" aria-hidden="true" />
                  No runtime observation was returned for this resource.
                </div>
              )}
            </div>
          )}

          {d.factors && Object.keys(d.factors).length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-slate-400">
                Scoring factors
              </summary>
              <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3 lg:grid-cols-4">
                {Object.entries(d.factors).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2 font-mono text-[11px] text-slate-500">
                    <span className="truncate">{k}</span>
                    <span className="text-slate-400">{typeof v === 'number' ? v.toFixed(2) : String(v)}</span>
                  </div>
                ))}
              </div>
            </details>
          )}

          {d.telemetryEvidenceIds.length > 0 && (
            <p className="mt-2 font-mono text-[11px] text-slate-600">
              telemetry: {d.telemetryEvidenceIds.join(', ')}
            </p>
          )}
        </article>
      ))}
    </div>
  );
}
