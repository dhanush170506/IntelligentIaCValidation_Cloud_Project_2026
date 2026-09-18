import { formatPercent } from '../utils/format.js';
import { Network, ArrowDown } from 'lucide-react';

/** Blast radius assessments with a simple visual impact meter per resource. */
export default function BlastRadiusPanel({ blastRadius }) {
  if (!blastRadius || blastRadius.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-sm text-slate-500">
        Blast radius information is not available for this validation.
      </p>
    );
  }

  // Deduplicate by resource: the pipeline may emit one assessment per finding
  // on the same resource.
  const seen = new Set();
  const unique = blastRadius.filter((b) => {
    if (seen.has(b.resource)) return false;
    seen.add(b.resource);
    return true;
  });

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Dependency impact if the resource changes or fails, as assessed by the pipeline.
      </p>
      {unique.map((b) => {
        const score = b.blastRadiusScore ?? 0;
        const tone =
          score >= 0.6 ? 'bg-rose-500/70' : score >= 0.3 ? 'bg-amber-500/70' : 'bg-emerald-500/70';
        return (
          <article key={b.id} className="card p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Network className="h-4 w-4 text-slate-500" aria-hidden="true" />
              <h3 className="font-mono text-sm font-semibold text-slate-100">{b.resource ?? 'unknown'}</h3>
              <span className="ml-auto font-mono text-xs text-slate-400">
                score {score != null ? score.toFixed(2) : '—'} · {b.affectedCount} affected
              </span>
            </div>

            {/* Visual impact meter */}
            <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className={`h-full rounded-full ${tone}`}
                style={{ width: `${Math.round((score ?? 0) * 100)}%` }}
              />
            </div>

            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Direct dependents</p>
                {b.directDependents.length > 0 ? (
                  <ul className="mt-1.5 space-y-1">
                    {b.directDependents.map((dep, i) => (
                      <li key={`${dep}-${i}`} className="flex items-center gap-1.5 font-mono text-xs text-slate-300">
                        <ArrowDown className="h-3 w-3 text-slate-600" aria-hidden="true" />
                        {dep}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">None</p>
                )}
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-500">Transitive dependents</p>
                {b.transitiveDependents.length > 0 ? (
                  <ul className="mt-1.5 space-y-1">
                    {b.transitiveDependents.map((dep, i) => (
                      <li key={`${dep}-${i}`} className="flex items-center gap-1.5 font-mono text-xs text-slate-300">
                        <ArrowDown className="h-3 w-3 text-slate-600" aria-hidden="true" />
                        {dep}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-xs text-slate-500">None</p>
                )}
              </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-white/5 pt-2.5 font-mono text-[11px] text-slate-500">
              <span>target criticality: {b.targetCriticality != null ? b.targetCriticality.toFixed(2) : '—'}</span>
              <span>dependent criticality: {b.dependentCriticality != null ? b.dependentCriticality.toFixed(2) : '—'}</span>
              {b.evidenceId && <span>evidence: {b.evidenceId}</span>}
            </div>
          </article>
        );
      })}
    </div>
  );
}
