import { useCallback, useRef, useState } from 'react';
import { UploadCloud, FileCode2, X, FileWarning } from 'lucide-react';
import { detectFormat, isSupportedFile, formatBytesSafe } from '../utils/uploadUtils.js';

const ACCEPT = '.tf,.yaml,.yml,.json';

/** Drag-and-drop + browse file picker restricted to .tf/.yaml/.yml/.json. */
export default function FileUploader({ file, onChange, disabled }) {
  const inputRef = useRef(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState(null);

  const handleFiles = useCallback(
    (files) => {
      const picked = files?.[0];
      if (!picked) return;
      if (!isSupportedFile(picked)) {
        setError('Unsupported IaC file format. Supported: .tf, .yaml, .yml, .json');
        return;
      }
      if (picked.size === 0) {
        setError('The selected file is empty.');
        return;
      }
      setError(null);
      onChange?.(picked);
    },
    [onChange]
  );

  const onDrop = (e) => {
    e.preventDefault();
    setDragActive(false);
    if (disabled) return;
    handleFiles(e.dataTransfer?.files);
  };

  const onBrowse = () => inputRef.current?.click();

  const clear = () => {
    setError(null);
    onChange?.(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div>
      <div
        role="button"
        tabIndex={0}
        aria-label="Upload IaC file: drag and drop or browse"
        onClick={onBrowse}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onBrowse();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={onDrop}
        className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center transition ${
          dragActive
            ? 'border-signal/60 bg-signal/[0.07]'
            : 'border-white/15 bg-white/[0.02] hover:border-white/25 hover:bg-white/[0.04]'
        } ${disabled ? 'pointer-events-none opacity-60' : ''}`}
      >
        <UploadCloud className={`h-8 w-8 ${dragActive ? 'text-signal' : 'text-slate-500'}`} aria-hidden="true" />
        <p className="text-sm font-medium text-slate-200">
          Drag &amp; drop your IaC file here, or <span className="text-signal">browse</span>
        </p>
        <p className="text-xs text-slate-500">Terraform (.tf) · CloudFormation (.yaml, .yml, .json) — up to 10 MB</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {error && (
        <p role="alert" className="mt-3 flex items-center gap-2 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          <FileWarning className="h-4 w-4 shrink-0" aria-hidden="true" />
          {error}
        </p>
      )}

      {file && !error && (
        <div className="mt-3 flex items-center justify-between gap-3 rounded-md border border-white/10 bg-night-850 px-3 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <FileCode2 className="h-5 w-5 shrink-0 text-signal" aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-200">{file.name}</p>
              <p className="text-xs text-slate-500">
                {formatBytesSafe(file.size)} · detected format:{' '}
                <span className="font-mono text-slate-400">{detectFormat(file.name)}</span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={clear}
            aria-label={`Remove ${file.name}`}
            className="rounded p-1.5 text-slate-400 transition hover:bg-white/5 hover:text-rose-300"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      )}
    </div>
  );
}
