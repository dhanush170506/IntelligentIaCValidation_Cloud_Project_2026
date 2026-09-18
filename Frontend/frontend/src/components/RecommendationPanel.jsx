import SeverityBadge from './SeverityBadge.jsx';
import {
  RECOMMENDATION_CATEGORIES,
  RECOMMENDATION_CATEGORY_LABELS,
  normalizeRecommendationCategory,
} from '../utils/severity.js';
import { formatPercent } from '../utils/format.js';
import { Lightbulb } from 'lucide-react';

/** Recommendations grouped by category, rendered exactly as the pipeline returned them. */
export default function RecommendationPanel({ recommendations }) {
  const groups = new Map(
    RECOMMENDATION_CATEGORIES.concat('OTHER').map((c) => [c, []])
  );
  for (const rec of recommendations ?? []) {
    groups.get(normalizeRecommendationCategory(rec.category)).push(rec);
  }

  const nonEmpty = [...groups.entries()].filter(([, items]) => items.length > 0);
  if (nonEmpty.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-slate-500">No recommendations available.</p>;
  }

  return (
    <div className="space-y-5">
      {nonEmpty.map(([category, items]) => (
        <section key={category}>
          <div className="mb-2 flex items-center gap-2">
            <Lightbulb className="h-4 w-4 text-amber-300/80" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-slate-200">
              {RECOMMENDATION_CATEGORY_LABELS[category]}
            </h3>
            <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-slate-500">
              {items.length}
            </span>
          </div>
          <div className="space-y-2.5">
            {items.map((rec) => (
              <article key={rec.id} className="card p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityBadge severity={rec.priority ?? rec.severity} />
                  <h4 className="text-sm font-semibold text-slate-100">
                    {rec.title ?? rec.description ?? 'Recommendation'}
                  </h4>
                  {rec.decision && (
                    <span className="rounded border border-white/10 bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] uppercase text-slate-400">
                      {rec.decision}
                    </span>
                  )}
                  {rec.resource && (
                    <span className="ml-auto truncate font-mono text-[11px] text-signal/80">{rec.resource}</span>
                  )}
                </div>

                {rec.action && <p className="mt-2 text-sm text-slate-300">{rec.action}</p>}

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
                  {rec.evidenceGrounded && (
                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300/90">
                      evidence-grounded
                    </span>
                  )}
                  {rec.confidence != null && (
                    <span className="font-mono">confidence: {formatPercent(rec.confidence)}</span>
                  )}
                  {rec.blastRadiusScore != null && (
                    <span className="font-mono">blast radius: {rec.blastRadiusScore.toFixed(2)}</span>
                  )}
                  {rec.sourceModules.length > 0 && (
                    <span className="font-mono">modules: {rec.sourceModules.join(', ')}</span>
                  )}
                  {rec.problem && rec.problem !== rec.title && (
                    <span>problem: {rec.problem}</span>
                  )}
                </div>
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
