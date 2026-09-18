import { useCallback, useEffect, useState } from 'react';

const KEY = 'iac-assurance-theme';

/** Dark-first theme toggle. Preference is a local UI setting; the backend has
 * no settings API, so nothing is falsely persisted server-side. */
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'dark';
    return window.localStorage.getItem(KEY) || 'dark';
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    window.localStorage.setItem(KEY, theme);
  }, [theme]);

  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);
  return { theme, setTheme, toggle };
}
