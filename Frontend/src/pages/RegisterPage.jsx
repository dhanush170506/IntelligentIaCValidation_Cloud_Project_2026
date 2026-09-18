import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth.jsx';
import { User, Mail, Lock, UserPlus } from 'lucide-react';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function passwordProblem(pw) {
  if (!pw) return 'Password is required.';
  if (pw.length < 8) return 'Password must be at least 8 characters.';
  if (!/[A-Za-z]/.test(pw) || !/[0-9]/.test(pw)) return 'Password must include letters and numbers.';
  return null;
}

/** Account creation page (same demo-mode auth abstraction as login). */
export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({ name: '', email: '', password: '', confirm: '' });
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
    if (!form.name.trim()) errors.name = 'Name is required.';
    if (!form.email.trim()) errors.email = 'Email is required.';
    else if (!EMAIL_RE.test(form.email.trim())) errors.email = 'Enter a valid email address.';
    const pwProblem = passwordProblem(form.password);
    if (pwProblem) errors.password = pwProblem;
    if (form.confirm !== form.password) errors.confirm = 'Passwords do not match.';
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
      // Password is validated client-side (complexity + confirmation) but
      // deliberately not sent or stored: the demo auth layer keeps no secrets.
      await register({ name: form.name.trim(), email: form.email.trim() });
      navigate('/', { replace: true });
    } catch (err) {
      setFormError(err?.message || 'Account creation failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const field = (id, label, input) => (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-slate-300">
        {label}
      </label>
      {input}
      {fieldErrors[id] && <p className="mt-1 text-xs text-rose-400">{fieldErrors[id]}</p>}
    </div>
  );

  return (
    <div className="card p-6">
      <h2 className="text-lg font-semibold text-slate-100">Create account</h2>
      <p className="mt-1 text-sm text-slate-400">Register to use the assurance console.</p>

      {formError && (
        <div role="alert" className="mt-4 rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {formError}
        </div>
      )}

      <form onSubmit={onSubmit} noValidate className="mt-4 space-y-4">
        {field(
          'reg-name',
          'Name',
          <div className="relative">
            <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              id="reg-name"
              type="text"
              autoComplete="name"
              value={form.name}
              onChange={setField('name')}
              className="input pl-9"
              placeholder="Jane Engineer"
              aria-invalid={Boolean(fieldErrors.name)}
            />
          </div>
        )}

        {field(
          'reg-email',
          'Email',
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              id="reg-email"
              type="email"
              autoComplete="email"
              value={form.email}
              onChange={setField('email')}
              className="input pl-9"
              placeholder="you@company.com"
              aria-invalid={Boolean(fieldErrors.email)}
            />
          </div>
        )}

        {field(
          'reg-password',
          'Password',
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              id="reg-password"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={setField('password')}
              className="input pl-9"
              placeholder="Min. 8 chars, letters + numbers"
              aria-invalid={Boolean(fieldErrors.password)}
            />
          </div>
        )}

        {field(
          'reg-confirm',
          'Confirm Password',
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden="true" />
            <input
              id="reg-confirm"
              type="password"
              autoComplete="new-password"
              value={form.confirm}
              onChange={setField('confirm')}
              className="input pl-9"
              placeholder="Repeat password"
              aria-invalid={Boolean(fieldErrors.confirm)}
            />
          </div>
        )}

        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-night-950/30 border-t-night-950" aria-hidden="true" />
              Creating account…
            </>
          ) : (
            <>
              <UserPlus className="h-4 w-4" aria-hidden="true" />
              Create Account
            </>
          )}
        </button>
      </form>

      <p className="mt-4 text-center text-sm text-slate-400">
        Already registered?{' '}
        <Link to="/login" className="font-medium text-signal hover:underline">
          Sign In
        </Link>
      </p>
    </div>
  );
}
