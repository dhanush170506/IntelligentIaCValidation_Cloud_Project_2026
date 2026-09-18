import { Inbox } from 'lucide-react';

/** Empty-state block. Used whenever the backend has no data — never fabricated numbers. */
export default function EmptyState({ icon: Icon = Inbox, title, message, action, className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-2 py-14 text-center ${className}`}>
      <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03]">
        <Icon className="h-6 w-6 text-slate-500" aria-hidden="true" />
      </div>
      <p className="mt-2 text-sm font-medium text-slate-300">{title}</p>
      {message && <p className="max-w-md text-sm text-slate-500">{message}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
