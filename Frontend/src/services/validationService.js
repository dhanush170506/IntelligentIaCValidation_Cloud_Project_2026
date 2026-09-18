import { api, ApiError, API_BASE_URL } from './api';
import { detectFormat, isSupportedFile, SUPPORTED_EXTENSIONS } from '../utils/uploadUtils.js';

export { detectFormat, isSupportedFile, SUPPORTED_EXTENSIONS };

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const VALIDATE_TIMEOUT_MS = 120000; // the pipeline runs synchronously; allow for it

/** Client-side pre-flight checks. Returns an error message or null. */
export function isValidIaCFile(file) {
  if (!file) return 'No file selected.';
  if (!isSupportedFile(file)) {
    return `Unsupported IaC file format. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}`;
  }
  if (file.size === 0) return 'The selected file is empty.';
  if (file.size > MAX_FILE_BYTES) return 'File exceeds the 10 MB limit.';
  return null;
}

function assertValidPayload(payload) {
  if (!payload || payload.success !== true || !payload.report_id || !payload.validation) {
    throw new ApiError(
      'invalid-response',
      'The backend accepted the file but returned an unexpected validation payload.',
      { detail: payload ? 'missing success/report_id/validation' : 'empty body' },
    );
  }
  return payload;
}

/**
 * Upload a real IaC file to the backend and run the assurance pipeline.
 * POST /validate (multipart/form-data, field name: "file").
 *
 * The backend stores the upload, forwards the content to the ML assurance
 * engine, persists a report and returns the full pipeline result.
 *
 * Uses XHR (not fetch) because it is the only way to report real upload
 * progress. The backend exposes no per-stage pipeline progress, so nothing
 * beyond the upload itself may be presented as tracked progress.
 */
export function validateFile(file, { signal, onUploadProgress } = {}) {
  return new Promise((resolve, reject) => {
    const onAbort = () => xhr.abort();
    const cleanup = () => signal?.removeEventListener('abort', onAbort);

    const xhr = new XMLHttpRequest();
    xhr.responseType = 'json';
    xhr.open('POST', `${API_BASE_URL}/validate`);
    xhr.timeout = VALIDATE_TIMEOUT_MS;

    if (onUploadProgress) {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) onUploadProgress(e.loaded / e.total);
      });
      xhr.upload.addEventListener('load', () => onUploadProgress(1));
    }

    // xhr.onload fires when the HTTP response has been received (or status 0
    // on network failure) — the single authoritative completion event.
    xhr.onload = () => {
      cleanup();
      if (xhr.status !== 200) {
        reject(
          new ApiError('http', `Backend rejected the upload (status ${xhr.status}).`, {
            status: xhr.status,
            detail: xhr.response?.detail ?? null,
          }),
        );
        return;
      }
      try {
        resolve(assertValidPayload(xhr.response));
      } catch (err) {
        reject(err);
      }
    };
    xhr.onerror = () => {
      cleanup();
      reject(new ApiError('network', 'Unable to reach the backend service. It may be offline.'));
    };
    xhr.onabort = () => {
      cleanup();
      reject(new ApiError('network', 'Upload cancelled.'));
    };
    xhr.ontimeout = () => {
      cleanup();
      reject(new ApiError('timeout', 'The validation request timed out. Please try again.'));
    };

    const formData = new FormData();
    formData.append('file', file, file.name);
    xhr.send(formData);
  });
}

/** GET /reports/{report_id} – the stored report (summary + findings + recommendations). */
export async function getReport(reportId) {
  const payload = await api.get(`/reports/${encodeURIComponent(reportId)}`);
  if (!payload || !payload.report_id) {
    throw new ApiError('invalid-response', 'The backend returned an unexpected report payload.');
  }
  return payload;
}
