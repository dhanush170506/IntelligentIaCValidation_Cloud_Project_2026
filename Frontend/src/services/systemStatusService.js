import { api } from './api';

/**
 * System health checks.
 *
 * Backend and database expose real health endpoints on the FastAPI backend.
 * The ML assurance engine is deliberately NOT probed from the browser: it is
 * reached server-side (Frontend → Backend → ML) and its API emits no CORS
 * headers, so no browser check could distinguish "online" from "blocked".
 * The UI reports it as an indirect component instead of guessing.
 */

/** GET /health on the FastAPI backend → { success, message, service, version }. */
export async function getBackendHealth() {
  const data = await api.get('/health', { timeoutMs: 8000 });
  return {
    online: data?.success === true,
    detail: data?.message || (data?.success ? 'running' : 'unexpected payload'),
    version: data?.version ?? null,
  };
}

/** GET /health/database on the FastAPI backend → MongoDB connectivity. */
export async function getDatabaseHealth() {
  const data = await api.get('/health/database', { timeoutMs: 8000 });
  return {
    online: data?.success === true,
    detail: data?.message || data?.status || (data?.success ? 'connected' : 'unavailable'),
  };
}
