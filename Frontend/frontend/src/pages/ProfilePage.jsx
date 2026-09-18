import { useNavigate } from 'react-router-dom';
import { LogOut, Moon, Sun, Info } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import { useAuth } from '../hooks/useAuth.jsx';
import { useTheme } from '../hooks/useTheme.js';

export default function ProfilePage() {
  const { user, session, logout, isRealBackendAuth } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <>
      <PageHeader title="Profile & Settings" description="Account information and appearance preferences." />

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card p-5" aria-label="Account information">
          <h2 className="text-sm font-semibold text-slate-200">Account</h2>
          <dl className="mt-4 space-y-3">
            <div className="flex items-center justify-between gap-4 border-b border-white/5 pb-2.5">
              <dt className="text-sm text-slate-400">Name</dt>
              <dd className="text-sm font-medium text-slate-200">{user?.name ?? '—'}</dd>
            </div>
            <div className="flex items-center justify-between gap-4 border-b border-white/5 pb-2.5">
              <dt className="text-sm text-slate-400">Email</dt>
              <dd className="text-sm font-medium text-slate-200">{user?.email ?? '—'}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-sm text-slate-400">Session started</dt>
              <dd className="font-mono text-xs text-slate-400">
                {session?.issuedAt
                  ? new Date(session.issuedAt).toLocaleString()
                  : '—'}
              </dd>
            </div>
          </dl>

          <button type="button" onClick={handleLogout} className="btn-ghost mt-5 w-full border-rose-500/30 text-rose-300 hover:bg-rose-500/10">
            <LogOut className="h-4 w-4" aria-hidden="true" />
            Log out
          </button>
        </section>

        <div className="space-y-6">
          <section className="card p-5" aria-label="Appearance settings">
            <h2 className="text-sm font-semibold text-slate-200">Appearance</h2>
            <div className="mt-3 flex gap-2">
              {['dark', 'light'].map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTheme(t)}
                  aria-pressed={theme === t}
                  className={`btn-ghost flex-1 ${theme === t ? 'border-signal/50 text-signal' : ''}`}
                >
                  {t === 'dark' ? <Moon className="h-4 w-4" aria-hidden="true" /> : <Sun className="h-4 w-4" aria-hidden="true" />}
                  {t === 'dark' ? 'Dark' : 'Light'}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11px] text-slate-500">
              Stored in this browser only; the backend has no settings API.
            </p>
          </section>

          <section className="card p-5" aria-label="Authentication notice">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Info className="h-4 w-4 text-slate-500" aria-hidden="true" />
              About authentication
            </h2>
            <p className="mt-2 text-xs leading-relaxed text-slate-400">
              {isRealBackendAuth
                ? 'Authentication is provided by the backend.'
                : 'The backend does not provide authentication yet. Your session is a local, non-secure stand-in (browser storage) and the assurance APIs are unauthenticated. Connect real auth in services/authService.js.'}
            </p>
          </section>
        </div>
      </div>
    </>
  );
}
