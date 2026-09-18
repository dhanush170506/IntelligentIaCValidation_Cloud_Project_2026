import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Sidebar from '../components/Sidebar.jsx';
import Navbar from '../components/Navbar.jsx';

/** Authenticated shell: fixed sidebar (collapses under lg) + top navbar. */
export default function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-night-950">
      <Sidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex min-h-screen flex-col lg:pl-64">
        <Navbar onMenuClick={() => setMobileOpen((v) => !v)} />
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-7xl">
            <Outlet />
          </div>
        </main>
        <footer className="border-t border-white/5 px-4 py-3 text-center text-xs text-slate-600 sm:px-6 lg:px-8">
          Telemetry-Aware Multi-Agent IaC Assurance · research prototype
        </footer>
      </div>
    </div>
  );
}
