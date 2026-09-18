import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  UploadCloud,
  ShieldCheck,
  History,
  FolderGit2,
  User,
  ShieldHalf,
  X,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/validate', label: 'New Validation', icon: UploadCloud },
  { to: '/history', label: 'History', icon: History },
  { to: '/projects', label: 'Projects', icon: FolderGit2 },
  { to: '/profile', label: 'Profile', icon: User },
];

/** Fixed sidebar on desktop, overlay drawer on mobile. */
export default function Sidebar({ open, onClose }) {
  const links = (
    <nav className="flex flex-1 flex-col gap-1 px-3 py-4" aria-label="Primary">
      {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition ${
              isActive
                ? 'bg-signal/10 text-signal'
                : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'
            }`
          }
        >
          <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
          {label}
        </NavLink>
      ))}

      <div className="my-4 border-t border-white/5" />
      <div className="rounded-md border border-white/5 bg-white/[0.02] px-3 py-3">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
          <ShieldHalf className="h-4 w-4 text-signal/80" aria-hidden="true" />
          Assurance Engine
        </div>
        <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">
          Multi-agent pipeline with telemetry-aware drift detection and evidence-grounded
          consensus.
        </p>
      </div>
    </nav>
  );

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-white/5 bg-night-900/70 backdrop-blur lg:flex">
        <div className="flex items-center gap-2.5 border-b border-white/5 px-5 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md border border-signal/30 bg-signal/10">
            <ShieldHalf className="h-4 w-4 text-signal" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight text-slate-100">IaC Assurance</p>
            <p className="text-[11px] leading-tight text-slate-500">Smart Manufacturing Cloud</p>
          </div>
        </div>
        {links}
        <div className="border-t border-white/5 px-5 py-3 text-[11px] text-slate-600">
          Terraform · CloudFormation
        </div>
      </aside>

      {/* Mobile drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-black/70" onClick={onClose} aria-hidden="true" />
          <aside className="relative flex h-full w-72 flex-col border-r border-white/10 bg-night-900">
            <div className="flex items-center justify-between border-b border-white/5 px-5 py-4">
              <span className="text-sm font-semibold text-slate-100">IaC Assurance</span>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close navigation"
                className="rounded p-1 text-slate-400 hover:bg-white/5 hover:text-slate-200"
              >
                <X className="h-5 w-5" aria-hidden="true" />
              </button>
            </div>
            {links}
          </aside>
        </div>
      )}
    </>
  );
}
