import SeverityBadge from './SeverityBadge.jsx';
import { asArray } from '../utils/reportMapper.js';

/** Structured evidence records supporting pipeline claims. */
export default function EvidencePanel({ evidence }) {
  const items = asArray(evidence);
  if (items.length === 0) {
    return <p className="px-4 py-8 text-center text-sm text-slate-500">No evidence records available.</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <thead className="border-b border-white/10">
          <tr>
            <th className="th">Evidence ID</th>
            <th className="th">Source</th>
            <th className="th">Resource</th>
            <th className="th">Severity</th>
            <th className="th">Evidence</th>
            <th className="th">Confidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {items.map((e) => (
            <tr key={e.id} className="align-top transition hover:bg-white/[0.03]">
              <td className="td max-w-[220px] break-all font-mono text-[11px] text-slate-400">{e.evidenceId ?? '—'}</td>
              <td className="td whitespace-nowrap font-mono text-xs text-signal/80">{e.source ?? '—'}</td>
              <td className="td font-mono text-xs text-slate-300">{e.resource ?? '—'}</td>
              <td className="td"><SeverityBadge severity={e.severity} /></td>
              <td className="td max-w-md text-sm text-slate-200">{e.message ?? '—'}</td>
              <td className="td font-mono text-xs text-slate-400">
                {e.confidence != null ? `${Math.round(e.confidence * 100)}%` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
