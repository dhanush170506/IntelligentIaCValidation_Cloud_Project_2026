import { useMemo, useState } from 'react';
import { useParams, Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard as OverviewIcon,
  ShieldCheck,
  GitBranch,
  Bot,
  FileSearch,
  Network,
  Wrench,
  Lightbulb,
} from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import ScoreCard from '../components/ScoreCard.jsx';
import FindingsTable from '../components/FindingsTable.jsx';
import FindingCard from '../components/FindingCard.jsx';
import AgentCard from '../components/AgentCard.jsx';
import EvidencePanel from '../components/EvidencePanel.jsx';
import DriftPanel from '../components/DriftPanel.jsx';
import BlastRadiusPanel from '../components/BlastRadiusPanel.jsx';
import RemediationPanel from '../components/RemediationPanel.jsx';
import RecommendationPanel from '../components/RecommendationPanel.jsx';
import OverviewSidebar from '../components/report/OverviewSidebar.jsx';
import LoadingState from '../components/LoadingState.jsx';
import ErrorState from '../components/ErrorState.jsx';
import { getReport } from '../services/validationService.js';
import { useAsync } from '../hooks/useAsync.js';
import { mapValidation, mapStoredReport, asArray } from '../utils/reportMapper.js';
import { SEVERITY_ORDER } from '../utils/severity.js';
import { formatDateTime } from '../utils/format.js';
import { formatFileType } from '../utils/formatFileType.js';

function TabButton({ active, onClick, icon: Icon, children, count }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition ${
        active
          ? 'border-signal text-signal'
          : 'border-transparent text-slate-400 hover:border-white/20 hover:text-slate-200'
      }`}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
      {children}
      {count != null && (
        <span className="rounded bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * Full technical report page.
 *
 * Data comes from either:
 *  - the full pipeline payload passed via router state right after POST /validate, or
 *  - the stored report from GET /reports/{id} (summary + findings + recommendations).
 * Extended tabs (agents, evidence, drift, blast radius, remediation) render only
 * when the payload actually contains that data.
 */
export default function ValidationReportPage() {
  const { id } = useParams();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState('overview');

  const fullValidation = location.state?.fullValidation ?? null;
  const { data: stored, error, loading, refetch } = useAsync(() => getReport(id));

  const model = useMemo(() => {
    if (fullValidation?.validation) {
      const vm = mapValidation(fullValidation.validation);
      // POST /validate returns filename/file_type only on the top-level
      // envelope; the inner validation object carries none of it.
      if (vm) {
        vm.filename = fullValidation.filename ?? vm.filename;
        vm.fileType = fullValidation.file_type ?? vm.fileType;
        vm.createdAt = fullValidation.created_at ?? vm.createdAt;
      }
      return vm;
    }
    if (stored) return mapStoredReport(stored);
    return null;
  }, [fullValidation, stored]);

  if (loading && !stored && !fullValidation) {
    return (
      <>
        <PageHeader title="Validation Report" />
        <LoadingState label="Loading report…" />
      </>
    );
  }

  if (error) {
    return (
      <>
        <PageHeader title="Validation Report" />
        <ErrorState error={error} title="Report could not be loaded" onRetry={refetch} />
      </>
    );
  }

  if (!model) {
    return (
      <>
        <PageHeader title="Validation Report" />
        <ErrorState
          title="Report not found"
          error={{ kind: 'http', message: 'No report exists for this identifier.' }}
          showRetry={false}
        />
      </>
    );
  }

  const v = {
    ...model,
    status: model.status ?? stored?.status ?? null,
    createdAt: model.createdAt ?? stored?.createdAt ?? null,
    reportId: model.reportId ?? stored?.reportId ?? id,
  };

  const findings = asArray(v.findings);
  const grouped = SEVERITY_ORDER.map((severity) => ({
    severity,
    items: findings.filter((f) => (f.severity ?? 'INFO') === severity),
  })).filter((g) => g.items.length > 0);

  const tabs = [
    { id: 'overview', label: 'Overview', icon: OverviewIcon },
    { id: 'security', label: 'Security', icon: ShieldCheck, count: findings.length },
    { id: 'drift', label: 'Drift', icon: GitBranch, count: v.drift?.length, hasData: Array.isArray(v.drift) && v.drift.length > 0 },
    { id: 'agents', label: 'Agents', icon: Bot, count: v.agents?.length, hasData: Array.isArray(v.agents) && v.agents.length > 0 },
    { id: 'evidence', label: 'Evidence', icon: FileSearch, count: v.evidence?.length, hasData: Array.isArray(v.evidence) && v.evidence.length > 0 },
    { id: 'blast', label: 'Blast Radius', icon: Network, count: v.blastRadius?.length, hasData: Array.isArray(v.blastRadius) && v.blastRadius.length > 0 },
    { id: 'remediation', label: 'Remediation', icon: Wrench, count: v.remediation?.length, hasData: Array.isArray(v.remediation) && v.remediation.length > 0 },
    { id: 'recommendations', label: 'Recommendations', icon: Lightbulb, count: v.recommendations?.length, hasData: Array.isArray(v.recommendations) && v.recommendations.length > 0 },
  ].filter((t) => t.hasData === undefined || t.hasData === true);

  const effectiveTab = tabs.some((t) => t.id === activeTab) ? activeTab : 'overview';

  return (
    <>
      <PageHeader
        title={v.filename}
        description={`${formatFileType(v.fileType)} · validated ${formatDateTime(v.createdAt)} · ID ${v.reportId ?? id}`}
        actions={
          <>
            <StatusBadge status={v.status} className="!px-3 !py-1 !text-sm" />
            <Link to="/history" className="btn-ghost">History</Link>
          </>
        }
      />

      {v.status === 'ERROR' && (
        <div className="mb-6">
          <ErrorState
            title="Validation could not be completed"
            error={{
              kind: 'http',
              message:
                v.error ??
                v.errorDetail ??
                'The assurance pipeline could not process this file. The backend has stored the failed attempt in history.',
            }}
            showRetry={false}
          />
        </div>
      )}

      {!v.hasExtendedData && (
        <div className="mb-6 rounded-md border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-slate-500">
          Showing the stored report. Agent, evidence, drift and blast-radius detail appears here when a
          validation is run from the{' '}
          <Link to="/validate" className="text-signal hover:underline">New Validation</Link> page.
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <ScoreCard label="Security Score" value={v.securityScore} hint="higher is better" />
        <ScoreCard label="Drift Score" value={v.driftScore} hint="lower is better" />
        <ScoreCard label="Confidence" percent={v.confidence} hint="pipeline confidence" />
        <ScoreCard
          label="Deployment Readiness"
          value={v.assurance?.readinessScore ?? null}
          hint={v.assurance?.readinessScore != null ? 'higher is better' : 'available after a fresh validation'}
        />
        <div className="card flex items-center justify-center p-4">
          <div className="text-center">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Overall Status</p>
            <div className="mt-2"><StatusBadge status={v.status} className="!px-3 !py-1 !text-sm" /></div>
            {v.assurance?.readinessComponents && (
              <p className="mt-2 font-mono text-[10px] leading-relaxed text-slate-600">
                findings penalty: {String(v.assurance.readinessComponents.findings_penalty ?? '—')}
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="mt-6 border-b border-white/10">
        <div role="tablist" aria-label="Report sections" className="flex overflow-x-auto">
          {tabs.map((t) => (
            <TabButton
              key={t.id}
              active={effectiveTab === t.id}
              onClick={() => setActiveTab(t.id)}
              icon={t.icon}
              count={t.count}
            >
              {t.label}
            </TabButton>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {effectiveTab === 'overview' && (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <section className="card">
                <h2 className="border-b border-white/5 px-4 py-3 text-sm font-semibold text-slate-200">
                  Findings ({findings.length})
                </h2>
                <FindingsTable findings={findings} />
              </section>

              {v.assurance?.limitations && v.assurance.limitations.length > 0 && (
                <section className="card p-4">
                  <h2 className="text-sm font-semibold text-slate-200">Pipeline limitations</h2>
                  <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-slate-400">
                    {v.assurance.limitations.map((lim, i) => (
                      <li key={i}>· {lim}</li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
            <OverviewSidebar assurance={v.assurance} uir={v.uir} />
          </div>
        )}

        {effectiveTab === 'security' && (
          <div className="space-y-4">
            {grouped.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-slate-500">No findings available.</p>
            ) : (
              grouped.map(({ severity, items }) => (
                <section key={severity} className="space-y-2">
                  <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    {severity} ({items.length})
                  </h2>
                  {items.map((f) => (
                    <FindingCard key={f.id} finding={f} />
                  ))}
                </section>
              ))
            )}
          </div>
        )}

        {effectiveTab === 'drift' && <DriftPanel drift={v.drift} />}
        {effectiveTab === 'agents' && (
          <div className="grid gap-3 md:grid-cols-2">
            {v.agents.map((a) => (
              <AgentCard key={a.id} agent={a} />
            ))}
          </div>
        )}
        {effectiveTab === 'evidence' && <EvidencePanel evidence={v.evidence} />}
        {effectiveTab === 'blast' && <BlastRadiusPanel blastRadius={v.blastRadius} />}
        {effectiveTab === 'remediation' && <RemediationPanel remediation={v.remediation} />}
        {effectiveTab === 'recommendations' && <RecommendationPanel recommendations={v.recommendations} />}
      </div>
    </>
  );
}
