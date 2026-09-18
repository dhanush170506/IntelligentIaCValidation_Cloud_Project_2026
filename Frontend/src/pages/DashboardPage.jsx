import { Link } from 'react-router-dom';
import {
  ClipboardList,
  CheckCircle2,
  XCircle,
  Eye,
  ShieldCheck,
  GitBranch,
  Gauge,
  UploadCloud,
} from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import StatCard from '../components/StatCard.jsx';
import ValidationTable from '../components/ValidationTable.jsx';
import SystemStatus from '../components/SystemStatus.jsx';
import LoadingState from '../components/LoadingState.jsx';
import ErrorState from '../components/ErrorState.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { getDashboard } from '../services/dashboardService.js';
import { asArray, mapReportSummary } from '../utils/reportMapper.js';
import { formatPercent } from '../utils/format.js';

const FORMATS = [
  { name: 'Terraform', detail: '.tf — HashiCorp configuration files', ext: '.tf' },
  { name: 'AWS CloudFormation', detail: '.yaml / .yml / .json — stack templates', ext: '.yaml' },
];

export default function DashboardPage() {
  const { data, error, loading, refetch } = useAsync(getDashboard);

  const totals = data ?? {};
  const recent = asArray(totals.recent_validations)
    .map(mapReportSummary)
    .slice(0, 8);
  const hasAny = (totals.total_validations ?? 0) > 0;

  return (
    <>
      <PageHeader
        title="Assurance Dashboard"
        description="Aggregate assurance posture across all validated Terraform and CloudFormation templates."
        actions={
          <Link to="/validate" className="btn-primary">
            <UploadCloud className="h-4 w-4" aria-hidden="true" />
            New Validation
          </Link>
        }
      />

      {error && <ErrorState error={error} title="Dashboard unavailable" onRetry={refetch} className="mb-6" />}

      {loading && !data && <LoadingState label="Loading dashboard…" />}

      {!loading && !error && !data && (
        <EmptyState
          title="No dashboard data"
          message="The backend returned no aggregate statistics."
          action={<Link to="/validate" className="btn-ghost">Run your first validation</Link>}
        />
      )}

      {data && (
        <>
          <section aria-label="Summary metrics" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Total Validations" value={totals.total_validations ?? 0} icon={ClipboardList} />
            <StatCard label="Passed" value={totals.passed ?? 0} icon={CheckCircle2} tone="good" />
            <StatCard label="Failed" value={totals.failed ?? 0} icon={XCircle} tone="bad" />
            <StatCard label="Requires Review" value={totals.review_required ?? 0} icon={Eye} tone="warn" />
          </section>

          <section aria-label="Average scores" className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <StatCard
              label="Security Score"
              value={totals.average_security_score ?? null}
              hint="average across validations"
              icon={ShieldCheck}
              tone={totals.average_security_score == null ? 'default' : totals.average_security_score >= 75 ? 'good' : totals.average_security_score >= 50 ? 'warn' : 'bad'}
            />
            <StatCard
              label="Drift Score"
              value={totals.average_drift_score ?? null}
              hint="average runtime drift (lower is better)"
              icon={GitBranch}
              tone={totals.average_drift_score == null ? 'default' : totals.average_drift_score <= 25 ? 'good' : totals.average_drift_score <= 60 ? 'warn' : 'bad'}
              />
            <StatCard
              label="Confidence"
              value={hasAny ? formatPercent(totals.average_confidence) : 'No data'}
              hint="not aggregated by the backend yet"
              icon={Gauge}
            />
          </section>

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <section className="card" aria-label="Recent validations">
                <div className="flex items-center justify-between border-b border-white/5 px-4 py-3">
                  <h2 className="text-sm font-semibold text-slate-200">Recent validations</h2>
                  <Link to="/history" className="text-xs font-medium text-signal hover:underline">
                    View all
                  </Link>
                </div>
                {recent.length === 0 ? (
                  <EmptyState
                    title="No validation reports yet."
                    message="Upload a Terraform or CloudFormation file to run the assurance pipeline."
                    action={<Link to="/validate" className="btn-ghost">New Validation</Link>}
                  />
                ) : (
                  <div className="p-2">
                    <ValidationTable rows={recent} />
                  </div>
                )}
              </section>
            </div>

            <div className="space-y-6">
              <SystemStatus />
              <section className="card p-4" aria-label="Supported formats">
                <h2 className="text-sm font-semibold text-slate-200">Infrastructure formats</h2>
                <div className="mt-3 space-y-2">
                  {FORMATS.map((f) => (
                    <div key={f.name} className="flex items-center gap-3 rounded-md border border-white/5 bg-white/[0.02] px-3 py-2.5">
                      <span className="rounded border border-signal/25 bg-signal/10 px-2 py-0.5 font-mono text-[11px] text-signal">{f.ext}</span>
                      <div>
                        <p className="text-sm font-medium text-slate-200">{f.name}</p>
                        <p className="text-[11px] text-slate-500">{f.detail}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          </div>
        </>
      )}
    </>
  );
}
