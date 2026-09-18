/** Radial score card used in report headers and overview tab. */
export default function ScoreCard({ label, value, max = 100, percent = null, hint, tone = 'auto' }) {
  // `percent` (0..1) overrides value/max (e.g. confidence is already 0..1).
  const effective = percent != null ? percent * max : Number(value);
  const clamped = Number.isFinite(effective) ? Math.max(0, Math.min(max, effective)) : null;
  const ratio = clamped == null ? 0 : clamped / max;

  const autoTone =
    tone !== 'auto'
      ? tone
      : ratio >= 0.75
      ? 'good'
      : ratio >= 0.4
      ? 'warn'
      : 'bad';

  const colors = {
    good: { stroke: '#34d399', text: 'text-emerald-300' },
    warn: { stroke: '#fbbf24', text: 'text-amber-300' },
    bad: { stroke: '#fb7185', text: 'text-rose-300' },
    neutral: { stroke: '#38bdf8', text: 'text-signal' },
  };
  const color = colors[autoTone] ?? colors.neutral;

  const radius = 26;
  const circumference = 2 * Math.PI * radius;

  return (
    <div className="card flex items-center gap-4 p-4">
      <svg viewBox="0 0 64 64" className="h-16 w-16 shrink-0" role="img" aria-label={`${label}: ${clamped == null ? 'unavailable' : Math.round(clamped)}`}>
        <circle cx="32" cy="32" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" />
        <circle
          cx="32"
          cy="32"
          r={radius}
          fill="none"
          stroke={color.stroke}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - ratio)}
          transform="rotate(-90 32 32)"
          style={{ transition: 'stroke-dashoffset 600ms ease' }}
        />
        <text x="32" y="36" textAnchor="middle" className="fill-slate-100 font-mono text-[13px] font-semibold">
          {clamped == null ? '—' : Math.round(clamped)}
        </text>
      </svg>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wider text-slate-400">{label}</p>
        <p className={`mt-0.5 font-mono text-lg font-semibold ${color.text}`}>
          {percent != null ? `${Math.round(percent * 100)}%` : `${clamped == null ? '—' : Math.round(clamped)}/${max}`}
        </p>
        {hint && <p className="mt-0.5 text-xs text-slate-500">{hint}</p>}
      </div>
    </div>
  );
}
