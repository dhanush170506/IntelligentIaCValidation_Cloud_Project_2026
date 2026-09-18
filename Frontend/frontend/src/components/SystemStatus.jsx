import { useEffect, useState } from 'react';
import { Server, Database, Cpu, RefreshCw } from 'lucide-react';
import { getBackendHealth, getDatabaseHealth } from '../services/systemStatusService.js';

function StatusDot({ state }) {
  // state: true = online, false = offline, null = unknown
  const color =
    state === true ? 'bg-emerald-400' : state === false ? 'bg-rose-400' : 'bg-slate-500';
  return (
    <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${color}`} aria-hidden="true" />
  );
}

function StatusRow({ icon: Icon, label, state, detail }) {
  const stateLabel = state === true ? 'Online' : state === false ? 'Offline' : 'Unknown';
  return (
    <div className="flex items-start gap-3 py-2">
      <Icon className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StatusDot state={state} />
          <span className="text-sm font-medium text-slate-200">{label}</span>
          <span
            className={`ml-auto font-mono text-[11px] ${
              state === true ? 'text-emerald-300/80' : state === false ? 'text-rose-300/80' : 'text-slate-500'
            }`}
          >
            {stateLabel}
          </span>
        </div>
        {detail && <p className="mt-0.5 truncate text-[11px] text-slate-500">{detail}</p>}
      </div>
    </div>
  );
}

/** Live health probes for the three system components. */
export default function SystemStatus() {
  const [status, setStatus] = useState({
    backend: { state: null, detail: 'checking…' },
    database: { state: null, detail: 'checking…' },
    ml: { state: null, detail: 'checking…' },
  });
  const [checking, setChecking] = useState(false);

  const checkAll = async () => {
    setChecking(true);
    // Backend first; database is only meaningful if the backend answers.
    const backend = await getBackendHealth().catch(() => ({ online: false, detail: 'unreachable' }));
    setStatus((s) => ({ ...s, backend: { state: backend.online, detail: backend.detail } }));

    const database = backend.online
      ? await getDatabaseHealth().catch(() => ({ online: false, detail: 'unreachable' }))
      : { online: null, detail: 'unknown while backend is unreachable' };
    setStatus((s) => ({ ...s, database: { state: database.online, detail: database.detail } }));

    // The ML engine has no browser-accessible health endpoint (no CORS by
    // design — it is called server-side by the backend), so its state is
    // reported as unknown rather than assumed healthy or down.
    setStatus((s) => ({
      ...s,
      ml: {
        state: null,
        detail: 'no browser health check — invoked server-side by the backend',
      },
    }));
    setChecking(false);
  };

  useEffect(() => {
    checkAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <section className="card p-4" aria-label="System status">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">System status</h2>
        <button
          type="button"
          onClick={checkAll}
          disabled={checking}
          className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs text-slate-400 transition hover:bg-white/5 hover:text-slate-200 disabled:opacity-50"
          aria-label="Re-run system health checks"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${checking ? 'animate-spin' : ''}`} aria-hidden="true" />
          Refresh
        </button>
      </div>
      <div className="divide-y divide-white/5">
        <StatusRow icon={Server} label="Backend API (FastAPI :8000)" state={status.backend.state} detail={status.backend.detail} />
        <StatusRow icon={Database} label="Database (MongoDB)" state={status.database.state} detail={status.database.detail} />
        <StatusRow icon={Cpu} label="ML assurance engine" state={status.ml.state} detail={status.ml.detail} />
      </div>
    </section>
  );
}
