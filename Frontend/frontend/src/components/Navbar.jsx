import { Menu, Search, Sun, Moon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useTheme } from '../hooks/useTheme.js';

/** Top navigation bar with menu toggle, history search entry and theme toggle. */
export default function Navbar({ onMenuClick }) {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();

  const submitSearch = (e) => {
    e.preventDefault();
    const value = new FormData(e.currentTarget).get('q');
    navigate(`/history${value ? `?q=${encodeURIComponent(String(value))}` : ''}`);
  };

  return (
    <header className="sticky top-0 z-20 border-b border-white/5 bg-night-950/85 backdrop-blur">
      <div className="flex h-14 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="Toggle navigation menu"
          className="rounded-md border border-white/10 p-2 text-slate-300 hover:bg-white/5 lg:hidden"
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </button>

        <form onSubmit={submitSearch} role="search" className="relative hidden sm:block">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
          <input
            type="search"
            name="q"
            placeholder="Search validations…"
            aria-label="Search validation history"
            className="input w-64 pl-8"
          />
        </form>

        <div className="flex-1" />

        <button
          type="button"
          onClick={toggle}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          className="rounded-md border border-white/10 p-2 text-slate-300 transition hover:bg-white/5"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
        </button>
      </div>
    </header>
  );
}
