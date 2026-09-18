import { Outlet, Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';
import { ShieldCheck } from 'lucide-react';

/** Centered layout for unauthenticated routes. */
export default function AuthLayout() {
  const { session, isBootstrapping } = useAuth();

  if (isBootstrapping) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-night-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-signal/30 border-t-signal" />
      </div>
    );
  }
  if (session) return <Navigate to="/" replace />;

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-night-950 px-4 py-10">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(56,189,248,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(56,189,248,0.06) 1px, transparent 1px)',
          backgroundSize: '36px 36px',
        }}
      />
      <div className="relative w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-2 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-signal/30 bg-signal/10">
            <ShieldCheck className="h-6 w-6 text-signal" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-100">
            IaC Assurance Console
          </h1>
          <p className="text-sm text-slate-400">
            Telemetry-aware, multi-agent infrastructure assurance
          </p>
        </div>
        <Outlet />
      </div>
      <p className="absolute bottom-4 text-center text-xs text-slate-600">
        Terraform · AWS CloudFormation · research prototype
      </p>
    </div>
  );
}
