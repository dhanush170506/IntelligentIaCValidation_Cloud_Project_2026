import SeverityBadge from './SeverityBadge.jsx';
import { asArray } from '../utils/reportMapper.js';

/** Findings list rendered as a table. Data is rendered exactly as returned by the ML pipeline. */
export default function FindingsTable({ findings, emptyMessage = 'No findings available.' }) {
  const items = asArray(findings);
  if (items.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-slate-500">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <thead className="border-b border-white/10">
          <tr>
            <th className="th">Severity</th>
            <th className="th">Category</th>
            <th className="th">Resource</th>
            <th className="th">Message</th>
            <th className="th">Confidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {items.map((f) => (
            <tr key={f.id} className="align-top transition hover:bg-white/[0.03]">
              <td className="td"><SeverityBadge severity={f.severity} /></td>
              <td className="td font-mono text-xs text-slate-400">{f.category ?? '—'}</td>
              <td className="td font-mono text-xs text-slate-300">{f.resource ?? '—'}</td>
              <td className="td max-w-md">
                <p className="text-sm text-slate-200">{f.message ?? '—'}</p>
                {f.ruleId && (
                  <p className="mt-0.5 font-mono text-[11px] text-slate-500">rule: {f.ruleId}</p>
                )}
                {f.evidenceIds.length > 0 && (
                  <p className="mt-1 font-mono text-[11px] text-slate-600">
                    evidence: {f.evidenceIds.join(', ')}
                  </p>
                )}
              </td>
              <td className="td font-mono text-xs text-slate-400">
                {f.confidence != null ? `${Math.round(f.confidence * 100)}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
