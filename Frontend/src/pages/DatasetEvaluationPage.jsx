import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Database, Play, RefreshCcw, Shield, AlertTriangle, BarChart3 } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import LoadingState from '../components/LoadingState.jsx';
import ErrorState from '../components/ErrorState.jsx';
import EmptyState from '../components/EmptyState.jsx';
import { getDatasetEvaluations, startDatasetEvaluation } from '../services/datasetEvaluationService.js';

const DEFAULT_SAMPLE_COUNT = 20;

function formatMetric(value, digits = 2) {
  if (value == null || Number.isNaN(Number(value))) return 'n/a';
  return Number(value).toFixed(digits);
}

export default function DatasetEvaluationPage() {
  const [datasets, setDatasets] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState('terragoat-master');
  const [sampleCount, setSampleCount] = useState(DEFAULT_SAMPLE_COUNT);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [activeRunId, setActiveRunId] = useState(null);
  const [runDetail, setRunDetail] = useState(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await getDatasetEvaluations();
      const datasetList = Array.isArray(payload.available_datasets) ? payload.available_datasets : [];
      setDatasets(datasetList);
      setRuns(Array.isArray(payload.runs) ? payload.runs : []);
      if (datasetList.length > 0 && !datasetList.some((item) => item.name === selectedDataset)) {
        setSelectedDataset(datasetList[0].name);
      }
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!activeRunId) return;
    const interval = setInterval(async () => {
      try {
        const payload = await getDatasetEvaluations();
        const currentRun = (payload.runs || []).find((run) => run.run_id === activeRunId);
        if (currentRun) {
          setRunDetail(currentRun);
          if (currentRun.status === 'completed' || currentRun.status === 'failed') {
            clearInterval(interval);
            refresh();
          }
        }
      } catch {
        // keep polling silently until a later successful refresh
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [activeRunId]);

  const selectedDatasetInfo = useMemo(
    () => datasets.find((item) => item.name === selectedDataset) || null,
    [datasets, selectedDataset]
  );

  async function handleStartEvaluation() {
    setSubmitting(true);
    setError(null);
    try {
      const response = await startDatasetEvaluation({ dataset_name: selectedDataset, sample_count: Number(sampleCount) || DEFAULT_SAMPLE_COUNT });
      if (response?.run_id) {
        setActiveRunId(response.run_id);
        await refresh();
      }
    } catch (err) {
      setError(err);
    } finally {
      setSubmitting(false);
    }
  }

  const summary = runDetail?.aggregate_metrics || {};

  return (
    <>
      <PageHeader
        title="Dataset Evaluation"
        description="Run the repository dataset through the same assurance pipeline used for single-file validation."
        actions={
          <button type="button" onClick={refresh} className="btn-ghost">
            <RefreshCcw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
        }
      />

      {error && <ErrorState error={error} title="Dataset evaluation unavailable" onRetry={refresh} className="mb-6" />}
      {loading && !datasets.length && <LoadingState label="Loading dataset catalog…" />}

      <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="card p-5">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Database className="h-4 w-4 text-signal" aria-hidden="true" />
            Available datasets
          </div>

          <div className="space-y-3">
            {datasets.length === 0 ? (
              <EmptyState title="No repository datasets detected" message="The dataset folder is empty or not yet populated." />
            ) : (
              datasets.map((dataset) => (
                <button
                  key={dataset.name}
                  type="button"
                  onClick={() => setSelectedDataset(dataset.name)}
                  className={`w-full rounded-md border px-3 py-3 text-left transition ${
                    selectedDataset === dataset.name
                      ? 'border-signal/50 bg-signal/10'
                      : 'border-white/5 bg-white/[0.02] hover:bg-white/[0.04]'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-slate-100">{dataset.name}</div>
                      <div className="text-xs text-slate-500">{dataset.count ?? 0} candidate samples</div>
                    </div>
                    <span className="rounded border border-white/10 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-400">
                      {selectedDataset === dataset.name ? 'Selected' : 'Dataset'}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>

          {selectedDatasetInfo && (
            <div className="mt-5 rounded-md border border-white/5 bg-white/[0.02] p-3">
              <label className="mb-2 block text-xs uppercase tracking-[0.16em] text-slate-500">Sample count</label>
              <input
                type="number"
                min="1"
                max="500"
                value={sampleCount}
                onChange={(event) => setSampleCount(event.target.value)}
                className="w-full rounded-md border border-white/10 bg-night-950 px-3 py-2 text-sm text-slate-100 outline-none ring-0"
              />
              <button
                type="button"
                onClick={handleStartEvaluation}
                disabled={submitting}
                className="btn-primary mt-4 inline-flex w-full items-center justify-center gap-2"
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                {submitting ? 'Starting…' : 'Start evaluation'}
              </button>
            </div>
          )}
        </section>

        <section className="card p-5">
          <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-slate-200">
            <BarChart3 className="h-4 w-4 text-signal" aria-hidden="true" />
            Latest run status
          </div>

          {runs.length === 0 ? (
            <EmptyState title="No evaluation runs yet" message="Start a run to process the repository dataset through the ML assurance pipeline." />
          ) : (
            <div className="space-y-3">
              {runs.slice(0, 4).map((run) => (
                <div key={run.run_id} className="rounded-md border border-white/5 bg-white/[0.02] p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-slate-100">{run.dataset_name}</div>
                      <div className="text-[11px] text-slate-500">{run.run_id}</div>
                    </div>
                    <span className="rounded border border-signal/30 bg-signal/10 px-2 py-1 text-[10px] uppercase tracking-wide text-signal">
                      {run.status}
                    </span>
                  </div>
                  <div className="mt-2 text-xs text-slate-400">
                    Samples: {run.samples_processed ?? 0} / {run.samples_requested ?? 0}
                  </div>
                </div>
              ))}
            </div>
          )}

          {summary && Object.keys(summary).length > 0 && (
            <div className="mt-5 space-y-3 border-t border-white/5 pt-4 text-sm">
              <div className="flex items-center justify-between"><span className="text-slate-400">Samples processed</span><strong>{summary.total_samples ?? 0}</strong></div>
              <div className="flex items-center justify-between"><span className="text-slate-400">Avg. security</span><strong>{formatMetric(summary.average_security_score)}</strong></div>
              <div className="flex items-center justify-between"><span className="text-slate-400">Avg. confidence</span><strong>{formatMetric(summary.average_confidence, 4)}</strong></div>
              <div className="flex items-center justify-between"><span className="text-slate-400">Drift detections</span><strong>{summary.drift_detections ?? 0}</strong></div>
            </div>
          )}
        </section>
      </div>

      {runs.length > 0 && (
        <section className="card mt-6 p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold text-slate-200">Evaluation history</h2>
            <Link to="/history" className="text-xs font-medium text-signal hover:underline">View validation history</Link>
          </div>

          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th className="th">Dataset</th>
                  <th className="th">Run ID</th>
                  <th className="th">Status</th>
                  <th className="th">Processed</th>
                  <th className="th">Security</th>
                  <th className="th">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id} className="hover:bg-white/[0.02]">
                    <td className="td">{run.dataset_name}</td>
                    <td className="td font-mono text-[11px] text-slate-300">{run.run_id}</td>
                    <td className="td">
                      <span className="rounded border border-white/10 px-2 py-1 text-[10px] uppercase tracking-wide text-slate-300">
                        {run.status}
                      </span>
                    </td>
                    <td className="td">{run.samples_processed ?? 0}</td>
                    <td className="td">{formatMetric(run.aggregate_metrics?.average_security_score)}</td>
                    <td className="td">{formatMetric(run.aggregate_metrics?.average_confidence, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
