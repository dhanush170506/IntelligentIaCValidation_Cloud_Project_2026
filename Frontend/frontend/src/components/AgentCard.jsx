import StatusBadge from './StatusBadge.jsx';
import { agentLabel } from '../utils/severity.js';
import { formatPercent } from '../utils/format.js';
import { Bot } from 'lucide-react';

/** One validation agent's structured result. Only pipeline-returned fields are shown. */
export default function AgentCard({ agent }) {
  const meta = agent.metadata ?? {};
  const metaEntries = Object.entries(meta).filter(([, v]) => v != null);

  return (
    <article className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-white/[0.04]">
            <Bot className="h-4 w-4 text-signal" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100">{agentLabel(agent.agentType)}</h3>
            {agent.agentType && (
              <p className="font-mono text-[11px] text-slate-500">{agent.agentType}</p>
            )}
          </div>
        </div>
        <StatusBadge status={agent.status} />
      </div>

      <div className="mt-3 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className="h-full rounded-full bg-signal/70"
            style={{ width: `${agent.confidence != null ? Math.round(agent.confidence * 100) : 0}%` }}
          />
        </div>
        <span className="font-mono text-xs text-slate-400">{formatPercent(agent.confidence)}</span>
      </div>

      {agent.message && (
        <p className="mt-3 text-sm leading-relaxed text-slate-300">{agent.message}</p>
      )}

      {agent.findings.length > 0 && (
        <div className="mt-3 border-t border-white/5 pt-3">
          <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Findings ({agent.findings.length})
          </p>
          <ul className="space-y-1.5">
            {agent.findings.map((f) => (
              <li key={f.id} className="text-xs leading-relaxed text-slate-400">
                <span className="font-mono text-slate-500">{f.severity ?? '—'}</span>{' '}
                {f.message ?? '—'}
              </li>
            ))}
          </ul>
        </div>
      )}

      {metaEntries.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 border-t border-white/5 pt-3 font-mono text-[11px] text-slate-500">
          {metaEntries.map(([k, v]) => (
            <span key={k}>{k}: {String(v)}</span>
          ))}
        </div>
      )}
    </article>
  );
}
