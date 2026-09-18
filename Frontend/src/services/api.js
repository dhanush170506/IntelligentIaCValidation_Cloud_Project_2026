/**
 * Central API client.
 *
 * Every backend/ML request in the app goes through here so that the base URL,
 * timeout, header handling and error normalization are defined in one place.
 *
 * Error taxonomy (ApiError.kind):
 *   'network'          – could not reach the service at all
 *   'timeout'          – request exceeded the allowed time
 *   'http'             – service responded with a non-2xx status
 *   'parse'            – service responded but the body was not valid JSON
 *   'invalid-response' – valid JSON but not the shape the app expects
 */

const DEFAULT_TIMEOUT_MS = 120000; // validations can run a full pipeline

function resolveBaseURL() {
  // Env var first; otherwise the documented local backend. (Falling back to
  // window.location.origin would be wrong in dev: Vite serves the SPA on
  // :5173 while the API runs on :8000.)
  const raw =
    import.meta.env?.VITE_API_BASE_URL ??
    'http://localhost:8000';
  return String(raw || '').replace(/\/+$/, '');
}

export const API_BASE_URL = resolveBaseURL();

export class ApiError extends Error {
  constructor(kind, message, { status = null, detail = null, cause = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = status;
    this.detail = detail;
    this.cause = cause;
  }
}

/** Map a low-level failure to a stable, user-presentable error. */
export function normalizeError(error) {
  if (error instanceof ApiError) return error;
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new ApiError('timeout', 'The request timed out. Please try again.', { cause: error });
  }
  if (error instanceof TypeError) {
    // fetch() raises TypeError for DNS/connection/CORS-style failures
    return new ApiError('network', 'Unable to reach the service. It may be offline.', {
      cause: error,
    });
  }
  return new ApiError('unknown', error?.message || 'An unexpected error occurred.', {
    cause: error,
  });
}

async function request(path, { method = 'GET', body, headers, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  if (!API_BASE_URL) {
    throw new ApiError(
      'config',
      'API base URL is not configured. Set VITE_API_BASE_URL in frontend/.env.',
    );
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { ...(body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...headers },
      body: body instanceof FormData ? body : body != null ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    throw normalizeError(err);
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    // Try to surface a helpful detail from FastAPI-style error bodies.
    let detail = null;
    try {
      const data = await response.json();
      detail = data?.detail ?? data?.message ?? null;
    } catch {
      /* body was not JSON – that's fine */
    }
    throw new ApiError('http', `Request failed with status ${response.status}.`, {
      status: response.status,
      detail,
    });
  }

  try {
    return await response.json();
  } catch (err) {
    throw new ApiError('parse', 'The service returned a malformed response.', { cause: err });
  }
}

export const api = {
  get: (path, options) => request(path, { ...options, method: 'GET' }),
  post: (path, body, options) => request(path, { ...options, method: 'POST', body }),
  postForm: (path, formData, options) =>
    request(path, { ...options, method: 'POST', body: formData }),
};
