import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import * as authService from '../services/authService.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(undefined); // undefined = booting

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const existing = await authService.getSession();
      if (!cancelled) setSession(existing);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({
      session,
      user: session?.user ?? null,
      isBootstrapping: session === undefined,
      login: async (credentials) => {
        const next = await authService.login(credentials);
        setSession(next);
        return next;
      },
      register: async (details) => {
        const next = await authService.register(details);
        setSession(next);
        return next;
      },
      logout: () => {
        authService.logout();
        setSession(null);
      },
      isRealBackendAuth: authService.AUTH_IS_REAL_BACKEND,
    }),
    [session]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
