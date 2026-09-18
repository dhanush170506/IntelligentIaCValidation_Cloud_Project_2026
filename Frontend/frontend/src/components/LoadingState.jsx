/** Centered loading block with spinner. */
export default function LoadingState({ label = 'Loading…', className = '' }) {
  return (
    <div className={`flex flex-col items-center justify-center gap-3 py-14 ${className}`} role="status">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-signal/30 border-t-signal" />
      <p className="text-sm text-slate-400">{label}</p>
    </div>
  );
}
