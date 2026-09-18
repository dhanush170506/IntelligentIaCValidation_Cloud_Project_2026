import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';
import { Mail, Lock, LogIn } from 'lucide-react';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Sign-in page. Uses the isolated auth abstraction (demo stand-in until the
 * backend ships a real auth API — the note under the form says so). */
export default function LoginPage() {
  const { login, isRealBackendAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState({ email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [loading, setLoading] = useState(false);

  const setField = (key) => (e) => {
    setForm((f) => ({ ...f, [key]: e.target.value }));
    setFieldErrors((fe) => ({ ...fe, [key]: undefined }));
    setFormError(null);
  };

  const validate = () => {
    const errors = {};
    if (!form.email.trim()) errors.email = 'Email is required.';
    else if (!EMAIL_RE.test(form.email.trim())) errors.email = 'Enter a valid email address.';
    if (!form.password) errors.password = 'Password is required.';
    return errors;
  };

  const onSubmit = async (e) => {
    e.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setLoading(true);
    setFormError(null);
    try {
      await login({ email: form.email.trim(), password: form.password });
      const from = location.state?.from && location.state.from !== '/login' ? location.state.from : '/';
      navigate(from, { replace: true });
    } catch (err) {
      setFormError(err?.message || 'Sign-in failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-slate-100">Sign in</h2>
      <p className="mt-1 text-sm text-slate-400">Access the assurance console.</p>

      {formError && (
        <div role="alert" className="mt-4 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {formError}
        </div>
      )}

      <form onSubmit={onSubmit} noValidate className="mt-4 space-y-4">
        <div>
          <label htmlFor="login-email" className="mb-1.5 block text-sm font-medium text-slate-300">
            Email
          </label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              id="login-email"
              name="email"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={setField('email')}
              className="input pl-9"
              placeholder="you@company.com"
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? 'login-email-error' : undefined}
            />
          </div>
          {fieldErrors.email && (
            <p id="login-email-error" className="mt-1 text-xs text-rose-400">{fieldErrors.email}</p>
          )}
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label htmlFor="login-password" className="block text-sm font-medium text-slate-300">
              Password
            </label>
            <button
              type="button"
              className="text-xs text-slate-500 transition hover:text-signal"
              onClick={() => setFormError('Password recovery is not available yet: the backend does not provide an account service.')}
            >
              Forgot password?
            </button>
          </div>
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              value={form.password}
              onChange={setField('password')}
              className="input pl-9"
              placeholder="••••••••"
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? 'login-password-error' : undefined}
            />
          </div>
          {fieldErrors.password && (
            <p id="login-password-error" className="mt-1 text-xs text-rose-400">{fieldErrors.password}</p>
          )}
        </div>

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-night-950/30 border-t-night-950" aria-hidden="true" />
              Signing in…
            </>
          ) : (
            <>
              <LogIn className="h-4 w-4" aria-hidden="true" />
              Sign In
            </>
          )}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-slate-400">
        No account?{' '}
        <Link to="/register" className="font-medium text-signal hover:underline">
          Create Account
        </Link>
      </p>

      {!isRealBackendAuth && (
        <p className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/[0.06] px-3 py-2 text-[11px] leading-relaxed text-amber-300/80">
          Demo authentication: accounts are stored locally in this browser only. The backend does
          not provide authentication yet — do not reuse a real password here.
        </p>
      )}
    </div>
  );
}
