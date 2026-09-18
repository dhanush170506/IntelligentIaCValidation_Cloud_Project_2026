import { SEVERITY_ORDER } from '../../utils/severity.js';

/**
 * Sidebar sections for the report Overview tab.
 * Every value comes from the payload; sections render only when the
 * corresponding data exists in the validation response.
 */
export default function OverviewSidebar({ assurance, uir }) {
  const breakdown = assurance?.securityBreakdown ?? null;
  const nodes = uir?.nodes ?? [];
  const edges = uir?.edges ?? [];

  return (
    <div className="space-y-4">
      {breakdown && (
        <section className="card p-4">
          <h2 className="text-sm font-semibold text-slate-200">Security breakdown</h2>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {SEVERITY_ORDER.map((sev) => (
              <div key={sev} className="rounded-md border border-white/5 bg-white/[0.02] px-3 py-2">
                <p className="font-mono text-[11px] text-slate-500">{sev.toLowerCase()}</p>
                <p className="font-mono text-lg font-semibold text-slate-200">{breakdown[sev] ?? 0}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {uir && (
        <section className="card p-4">
          <h2 className="text-sm font-semibold text-slate-200">Resource graph (UIR)</h2>
          <p className="mt-1 text-xs text-slate-500">
            {uir.resourceCount} resources · {uir.dependencyCount} dependencies ·{' '}
            {uir.provider ?? 'unknown provider'}
          </p>

          {nodes.length > 0 && (
            <div className="mt-3 space-y-1.5">
              {nodes.map((n) => (
                <div
                  key={n.id}
                  className="flex items-center justify-between rounded-md border border-white/5 bg-white/[0.02] px-3 py-1.5"
                >
                  <span className="truncate font-mono text-xs text-slate-300">{n.id}</span>
                  <span className="ml-2 shrink-0 font-mono text-[11px] text-slate-500">{n.type ?? ''}</span>
                </div>
              ))}
            </div>
          )}

          {edges.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-slate-400">
                Dependencies ({edges.length})
              </summary>
              <ul className="mt-2 space-y-1">
                {edges.map((e) => (
                  <li key={e.id} className="font-mono text-[11px] text-slate-500">
                    {e.from ?? '—'} → {e.to ?? '—'}
                    {e.kind ? ` (${e.kind})` : ''}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      )}
    </div>
  );
}
