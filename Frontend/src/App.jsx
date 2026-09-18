import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import AppLayout from './layouts/AppLayout.jsx';
import AuthLayout from './layouts/AuthLayout.jsx';
import DashboardPage from './pages/DashboardPage.jsx';
import ValidatePage from './pages/ValidatePage.jsx';
import ValidationReportPage from './pages/ValidationReportPage.jsx';
import HistoryPage from './pages/HistoryPage.jsx';
import DatasetEvaluationPage from './pages/DatasetEvaluationPage.jsx';
import ProjectsPage from './pages/ProjectsPage.jsx';
import ProfilePage from './pages/ProfilePage.jsx';
import LoginPage from './pages/LoginPage.jsx';
import RegisterPage from './pages/RegisterPage.jsx';
import NotFoundPage from './pages/NotFoundPage.jsx';
import { useAuth } from './hooks/useAuth.jsx';
import ErrorState from './components/ErrorState.jsx';

function ProtectedRoute({ children }) {
  const { session, isBootstrapping, isRealBackendAuth } = useAuth();
  const location = useLocation();

  if (isBootstrapping) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-night-950">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-signal/30 border-t-signal" />
      </div>
    );
  }
  if (!session) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return (
    <>
      {!isRealBackendAuth && (
        <div className="border-b border-amber-500/20 bg-amber-500/[0.07] px-4 py-1.5 text-center text-xs text-amber-300/90">
          Demo mode: authentication is a local stand-in — the backend does not provide auth yet,
          so all data APIs are open. Real authentication connects in{' '}
          <code className="font-mono">services/authService.js</code>.
        </div>
      )}
      {children}
    </>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<AuthLayout />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/validate" element={<ValidatePage />} />
        <Route path="/validation/:id" element={<ValidationReportPage />} />
        <Route path="/dataset-evaluation" element={<DatasetEvaluationPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>

      <Route
        path="*"
        element={
          <ErrorState
            title="404 — Page not found"
            message="The requested page does not exist in this console."
            showRetry={false}
          />
        }
      />
    </Routes>
  );
}
