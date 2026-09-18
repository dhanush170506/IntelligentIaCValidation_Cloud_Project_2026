import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Circle, Loader2, ShieldQuestion } from 'lucide-react';
import PageHeader from '../components/PageHeader.jsx';
import FileUploader from '../components/FileUploader.jsx';
import ErrorState from '../components/ErrorState.jsx';
import { validateFile, isValidIaCFile } from '../services/validationService.js';

/**
 * New validation page.
 *
 * The backend runs the whole pipeline synchronously inside POST /validate and
 * does not expose per-stage progress, so the UI shows one honest "validation
 * in progress" state (plus real upload progress) instead of fake stage steps.
 */
export default function ValidatePage() {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [phase, setPhase] = useState('idle'); // idle | uploading | waiting
  const [uploadPercent, setUploadPercent] = useState(0);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  // Abort any in-flight upload when the page unmounts.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const startValidation = async () => {
    if (!file || phase !== 'idle') return;

    const localError = isValidIaCFile(file);
    if (localError) {
      setError({ kind: 'invalid-file', message: localError });
      return;
    }

    setError(null);
    setPhase('uploading');
    setUploadPercent(0);

    const controller = new AbortController();
    controllerRef.current = controller;

    try {
      const payload = await validateFile(file, {
        signal: controller.signal,
        onUploadProgress: (fraction) => {
          setUploadPercent(Math.round(fraction * 100));
          // Upload complete → the pipeline is now running server-side.
          if (fraction >= 1) setPhase('waiting');
        },
      });

      navigate(`/validation/${payload.report_id}`, {
        state: { fullValidation: payload },
      });
    } catch (err) {
      if (controller.signal.aborted) return; // page unmounted / user cancelled
      setPhase('idle');
      setUploadPercent(0);
      setError(err);
    }
  };

  const inFlight = phase === 'uploading' || phase === 'waiting';
  const busyCopy = phase === 'uploading' ? 'Uploading IaC file…' : 'Validation in progress…';

  return (
    <>
      <PageHeader
        title="New Validation"
        description="Upload a Terraform or AWS CloudFormation file. The backend forwards it to the ML assurance pipeline and stores the resulting report."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <section className="card p-4" aria-label="Upload IaC file">
            <h2 className="mb-3 text-sm font-semibold text-slate-200">IaC file</h2>
            <FileUploader file={file} onChange={(f) => { setFile(f); setError(null); }} disabled={inFlight} />
          </section>

          {error && (
            <ErrorState
              error={error}
              title={
                error.kind === 'http'
                  ? 'Validation could not be completed'
                  : error.kind === 'timeout'
                  ? 'Validation request timed out'
                  : error.kind === 'invalid-response'
                  ? 'Unexpected backend response'
                  : error.kind === 'invalid-file'
                  ? 'File cannot be validated'
                  : 'Upload failed'
              }
              showRetry={false}
            />
          )}

          {inFlight && (
            <section className="card p-6" aria-live="polite" aria-label="Validation progress">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-signal" aria-hidden="true" />
                <p className="text-sm font-medium text-slate-200">{busyCopy}</p>
              </div>

              {phase === 'uploading' ? (
                <div className="mt-4">
                  <div
                    className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]"
                    role="progressbar"
                    aria-valuenow={uploadPercent}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Upload progress"
                  >
                    <div
                      className="h-full rounded-full bg-signal/80 transition-[width] duration-200"
                      style={{ width: `${uploadPercent}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-slate-500">
                    Uploading {file?.name} — {uploadPercent}%
                  </p>
                </div>
              ) : (
                <p className="mt-3 text-xs leading-relaxed text-slate-500">
                  The file is uploaded. The assurance pipeline (parsing, agents, drift, consensus)
                  is running on the server; the backend does not expose per-stage progress, so
                  intermediate steps are not shown. This typically takes a few seconds.
                </p>
              )}
            </section>
          )}
        </div>

        <aside className="space-y-4">
          <section className="card p-4" aria-label="Run validation">
            <h2 className="text-sm font-semibold text-slate-200">Run validation</h2>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">
              The file is sent to the FastAPI backend, which stores the upload, forwards the
              content to the ML assurance engine, and persists the resulting report.
            </p>
            <button
              type="button"
              onClick={startValidation}
              disabled={!file || inFlight}
              className="btn-primary mt-4 w-full"
            >
              {inFlight ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  Validating…
                </>
              ) : (
                <>
                  Validate <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </>
              )}
            </button>
          </section>

          <section className="card p-4" aria-label="Pipeline information">
            <h2 className="text-sm font-semibold text-slate-200">What the pipeline checks</h2>
            <ul className="mt-3 space-y-2 text-xs leading-relaxed text-slate-400">
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/70" aria-hidden="true" />Syntax &amp; structure (UIR graph)</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/70" aria-hidden="true" />Security (static analysis)</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/70" aria-hidden="true" />Deployment readiness</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/70" aria-hidden="true" />Runtime telemetry &amp; drift</li>
              <li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/70" aria-hidden="true" />Consensus &amp; blast radius</li>
              <li className="flex gap-2"><Circle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600" aria-hidden="true" />Evidence-grounded remediation</li>
            </ul>
            <p className="mt-3 border-t border-white/5 pt-3 text-[11px] leading-relaxed text-slate-500">
              <ShieldQuestion className="mr-1 inline h-3.5 w-3.5" aria-hidden="true" />
              Assurance only: proposals are advisory; infrastructure is never modified.
            </p>
          </section>
        </aside>
      </div>
    </>
  );
}
