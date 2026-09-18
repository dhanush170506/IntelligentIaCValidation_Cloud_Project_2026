import { AlertTriangle, RefreshCw } from 'lucide-react';

const KIND_MESSAGES = {
  network: 'Unable to reach the backend service. It may be offline or unreachable from this network.',
  timeout: 'The request timed out. The service may be under load — please retry.',
  http: 'The backend service returned an error.',
  parse: 'The backend service returned a malformed response.',
  'invalid-response': 'The backend service returned an unexpected response.',
  config: 'The frontend is misconfigured: the API base URL is missing.',
};

/** Error block with kind-aware messaging and an optional retry action. */
export default function ErrorState({ error, title = 'Something went wrong', onRetry, showRetry = true, className = '' }) {
  const kindMessage = error?.kind ? KIND_MESSAGES[error.kind] : null;
  const detail =
    error?.detail && typeof error.detail === 'string' ? error.detail : null;

  return (
    <div
      role="alert"
      className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-rose-500/25 bg-rose-500/[0.06] py-12 text-center ${className}`}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-rose-500/30 bg-rose-500/10">
        <AlertTriangle className="h-6 w-6 text-rose-300" aria-hidden="true" />
      </div>
      <div className="px-6">
        <p className="text-sm font-semibold text-rose-200">{title}</p>
        <p className="mt-1 max-w-md text-sm text-rose-200/80">
          {kindMessage || error?.message || 'An unexpected error occurred.'}
        </p>
        {detail && (
          <p className="mx-auto mt-2 max-w-md break-words font-mono text-xs text-rose-200/60">
            {detail}
          </p>
        )}
      </div>
      {showRetry && onRetry && (
        <button type="button" onClick={onRetry} className="btn-ghost">
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}
