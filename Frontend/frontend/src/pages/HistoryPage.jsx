import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Search, UploadCloud } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import ValidationTable from '../components/ValidationTable.jsx';
import LoadingState from '../components/LoadingState.jsx';
import ErrorState from '../components/ErrorState.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { getHistory } from '../services/historyService.js';
import { mapReportSummary } from '../utils/reportMapper.js';

const STATUS_OPTIONS = ['PASS', 'FAIL', 'REVIEW_REQUIRED'];
const FORMAT_OPTIONS = ['terraform', 'cloudformation'];

export default function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data, error, loading, refetch } = useAsync(getHistory);

  const [query, setQuery] = useState(searchParams.get('q') ?? '');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [formatFilter, setFormatFilter] = useState('ALL');

  const rows = useMemo(() => (data?.reports ?? []).map(mapReportSummary), [data]);

  const filtered = rows.filter((r) => {
    if (query && !r.filename.toLowerCase().includes(query.toLowerCase())) return false;
    if (statusFilter !== 'ALL' && r.status !== statusFilter) return false;
    if (formatFilter !== 'ALL' && r.fileType !== formatFilter) return false;
    return true;
  });

  const setQueryParams = (value) => {
    setQuery(value);
    const next = new URLSearchParams(searchParams);
    if (value) next.set('q', value);
    else next.delete('q');
    setSearchParams(next, { replace: true });
  };

  return (
    <>
      <PageHeader
        title="Validation History"
        description="Every assurance run stored by the backend, newest first."
      />

      <section className="card" aria-label="Validation history">
        <div className="flex flex-col gap-3 border-b border-white/5 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1 sm:max-w-xs">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQueryParams(e.target.value)}
              placeholder="Search by filename…"
              aria-label="Search history by filename"
              className="input pl-8"
            />
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-400">
            Status
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="input w-auto py-1.5 text-xs"
              aria-label="Filter by status"
            >
              <option value="ALL">All</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{s.replace('_', ' ')}</option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-2 text-xs text-slate-400">
            Format
            <select
              value={formatFilter}
              onChange={(e) => setFormatFilter(e.target.value)}
              className="input w-auto py-1.5 text-xs"
              aria-label="Filter by IaC format"
            >
              <option value="ALL">All</option>
              {FORMAT_OPTIONS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
          </label>

          <span className="ml-auto text-xs text-slate-500" aria-live="polite">
            {filtered.length} of {rows.length} reports
          </span>
        </div>

        {loading && !data && <LoadingState label="Loading history…" />}
        {error && <ErrorState error={error} title="History unavailable" onRetry={refetch} />}

        {!loading && !error && rows.length === 0 && (
          <EmptyState
            title="No validation reports yet."
            message="Run your first assurance validation to populate the history."
            action={<Link to="/validate" className="btn-ghost"><UploadCloud className="h-4 w-4" aria-hidden="true" />New Validation</Link>}
          />
        )}

        {!loading && !error && rows.length > 0 && filtered.length === 0 && (
          <EmptyState
            title="No matches"
            message="No reports match the current search and filters."
          />
        )}

        {!loading && !error && filtered.length > 0 && (
          <div className="p-2">
            <ValidationTable rows={filtered} />
          </div>
        )}
      </section>
    </>
  );
}
