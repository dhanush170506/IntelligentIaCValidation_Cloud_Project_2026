/**
 * Authentication abstraction.
 *
 * IMPORTANT: the current backend (FastAPI on :8000) exposes NO authentication
 * endpoints — verified via /openapi.json (routes: /validate, /reports/{id},
 * /history, /dashboard, /health, /health/database). This module is the single,
 * clearly-isolated seam where real authentication will be connected later:
 *
 *   1. Implement `login` / `register` against the real API.
 *   2. Attach the issued token in `api.js` (headers) via an auth token store.
 *
 * Until then this is a NON-SECURE, explicitly-labelled local session only:
 * - it grants no real protection and gates nothing on the server;
 * - the backend serves all data to anyone who can reach it.
 *
 * No passwords are stored anywhere — a local profile record is created for the
 * session, and credentials are discarded immediately. Registration is not a
 * real account system and does not pretend to be one.
 */

const STORAGE_KEY = 'iac-assurance-session';

function safeParse(json, fallback) {
  try {
    return JSON.parse(json) ?? fallback;
  } catch {
    return fallback;
  }
}

function readSession() {
  if (typeof window === 'undefined') return null;
  return safeParse(window.localStorage.getItem(STORAGE_KEY), null);
}

function writeSession(session) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export async function getSession() {
  return readSession();
}

/**
 * "Sign in": accepts any credentials without storing or verifying them.
 * This is honest demo behaviour — there is no backend to verify against.
 */
export async function login({ email }) {
  const session = {
    user: { id: `local-${Date.now()}`, name: email.split('@')[0] || 'Demo User', email },
    issuedAt: Date.now(),
  };
  writeSession(session);
  return session;
}

/** "Register": creates the local profile only; passwords are never persisted. */
export async function register({ name, email }) {
  const session = {
    user: { id: `local-${Date.now()}`, name: name.trim(), email },
    issuedAt: Date.now(),
  };
  writeSession(session);
  return session;
}

export async function logout() {
  window.localStorage.removeItem(STORAGE_KEY);
}

export const AUTH_IS_REAL_BACKEND = false;
