/** Compact metric tile used on the dashboard. Value comes straight from the backend. */
export default function StatCard({ label, value, hint, icon: Icon, tone = 'default' }) {
  const tones = {
    default: 'text-slate-100',
    good: 'text-emerald-300',
    warn: 'text-amber-300',
    bad: 'text-rose-300',
    info: 'text-signal',
  };
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-slate-500" aria-hidden="true" />}
      </div>
      <p className={`mt-2 font-mono text-2xl font-semibold ${tones[tone] ?? tones.default}`}>
        {value ?? '—'}
      </p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </div>
  );
}
