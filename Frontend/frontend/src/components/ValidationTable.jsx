import { Link } from 'react-router-dom';
import { Eye } from 'lucide-react';
import StatusBadge from './StatusBadge.jsx';
import { formatScore, formatPercent, formatDateTime } from '../utils/format.js';

const FORMAT_LABELS = {
  terraform: 'Terraform',
  cloudformation: 'CloudFormation',
  unknown: 'Unknown',
};

/** Shared table for dashboard "recent validations" and history page. */
export default function ValidationTable({ rows, emptyAction = null }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="py-10 text-center text-sm text-slate-500">No validation reports yet.</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="table-base">
        <thead className="border-b border-white/10">
          <tr>
            <th className="th">Project / File</th>
            <th className="th">Format</th>
            <th className="th">Status</th>
            <th className="th">Security</th>
            <th className="th">Drift</th>
            <th className="th">Confidence</th>
            <th className="th">Date</th>
            <th className="th text-right">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {rows.map((row) => (
            <tr key={row.reportId ?? row.filename} className="transition hover:bg-white/[0.03]">
              <td className="td">
                <span className="font-mono text-sm text-slate-200">{row.filename}</span>
              </td>
              <td className="td text-slate-400">{FORMAT_LABELS[row.fileType] ?? row.fileType}</td>
              <td className="td"><StatusBadge status={row.status} /></td>
              <td className="td font-mono text-slate-300">{formatScore(row.securityScore)}</td>
              <td className="td font-mono text-slate-300">{formatScore(row.driftScore)}</td>
              <td className="td font-mono text-slate-300">{formatPercent(row.confidence)}</td>
              <td className="td whitespace-nowrap text-slate-400">{formatDateTime(row.createdAt)}</td>
              <td className="td text-right">
                {row.reportId && (
                  <Link
                    to={`/validation/${row.reportId}`}
                    className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-signal transition hover:bg-signal/10"
                  >
                    <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                    View Report
                  </Link>
                )}
              </td>
            </tr>
          ))}
          {emptyAction}
        </tbody>
      </table>
    </div>
  );
}
