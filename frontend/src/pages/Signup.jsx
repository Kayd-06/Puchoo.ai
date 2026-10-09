import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell, { Field, inputClass } from '../components/auth/AuthShell';
import PasswordField, { passwordIsValid } from '../components/auth/PasswordField';
import { PillButton, focusRing } from '../components/landing/ui';
import { useAuth } from '../context/AuthContext';

const empty = {
  full_name: '',
  email: '',
  password: '',
  confirm_password: '',
  workspace_type: 'personal',
  workspace_name: '',
  invite_code: '',
};

export default function Signup() {
  const navigate = useNavigate();
  const { requestSignup } = useAuth();
  const [values, setValues] = useState(empty);
  const [errors, setErrors] = useState({});
  const [toast, setToast] = useState('');
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(''), 5200);
    return () => clearTimeout(timer);
  }, [toast]);

  function update(key, value) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  function validate() {
    const next = {};
    if (!values.full_name.trim()) next.full_name = 'Enter your full name.';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim()))
      next.email = 'Enter a valid email address.';
    if (!passwordIsValid(values.password)) {
      next.password = 'Password must be at least 10 characters and include a letter and a number.';
    }
    if (values.password !== values.confirm_password)
      next.confirm_password = 'Passwords do not match.';
    if (values.workspace_type !== 'personal' && !values.invite_code.trim() && !values.workspace_name.trim()) {
      next.workspace_name = 'Enter a workspace name when creating a new shared workspace.';
    }
    return next;
  }

  async function onSubmit(event) {
    event.preventDefault();
    const next = validate();
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true);
    setToast('');
    try {
      const challenge = await requestSignup({
        full_name: values.full_name.trim(),
        email: values.email.trim().toLowerCase(),
        password: values.password,
        confirm_password: values.confirm_password,
        workspace_type: values.workspace_type,
        workspace_name: values.workspace_type === 'personal' ? null : values.workspace_name.trim() || null,
        invite_code: values.invite_code.trim() || null,
      });
      navigate('/login', {
        replace: true,
        state: { email: challenge.email, verificationPending: true },
      });
    } catch (error) {
      setToast(error.message || 'Unable to create an account with those details.');
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <title>Get started · Puchoo.si</title>
      <AuthShell
        title="Create your workspace"
        subtitle="Choose how your data should be owned and who can safely work with it."
        dense
        footer={
          <>
            Already have an account?{' '}
            <Link
              to="/login"
              className={`text-[#111827] underline-offset-4 hover:underline ${focusRing} rounded-full`}
            >
              Log in
            </Link>
          </>
        }
      >
        <form className="auth-signup-form" onSubmit={onSubmit} noValidate>
          <Field id="full_name" label="Full name" error={errors.full_name}>
            <input
              id="full_name"
              name="full_name"
              autoComplete="name"
              value={values.full_name}
              onChange={(event) => update('full_name', event.target.value)}
              aria-invalid={Boolean(errors.full_name)}
              aria-describedby={errors.full_name ? 'full_name-error' : undefined}
              className={inputClass(Boolean(errors.full_name))}
            />
          </Field>
          <Field id="email" label="Email" error={errors.email}>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              value={values.email}
              onChange={(event) => update('email', event.target.value)}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={errors.email ? 'email-error' : undefined}
              className={inputClass(Boolean(errors.email))}
            />
          </Field>
          <PasswordField
            id="password"
            label="Password"
            autoComplete="new-password"
            value={values.password}
            error={errors.password}
            onChange={(event) => update('password', event.target.value)}
          />
          <PasswordField
            id="confirm_password"
            label="Confirm password"
            autoComplete="new-password"
            value={values.confirm_password}
            error={errors.confirm_password}
            onChange={(event) => update('confirm_password', event.target.value)}
          />
          <fieldset className="auth-form-wide">
            <legend className="mb-2 text-sm font-medium text-[#111827]">How will you use Puchoo.si?</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {[
                ['personal', 'Personal', 'Only you can access your private workspace.'],
                ['business', 'Business', 'Invite people as Admin, Editor, or Viewer.'],
                ['institution', 'Institution', 'Admin, editor, and viewer access for your team.'],
              ].map(([value, label, detail]) => (
                <label
                  key={value}
                  className={`flex min-h-28 flex-col items-start gap-2 rounded-2xl border px-3 py-3 text-sm ${values.workspace_type === value ? 'border-[#111827] bg-[#eef3fc]' : 'border-black/10'} ${focusRing}`}
                >
                  <span className="flex items-center gap-2 font-medium"><input type="radio" name="workspace_type" value={value} checked={values.workspace_type === value} onChange={() => update('workspace_type', value)} />{label}</span>
                  <span className="text-xs leading-relaxed text-[#64748b]">{detail}</span>
                </label>
              ))}
            </div>
          </fieldset>
          {values.workspace_type !== 'personal' ? (
            <Field id="workspace_name" label={values.workspace_type === 'business' ? 'Business name' : 'Institution name'} error={errors.workspace_name}>
              <input
                id="workspace_name"
                name="workspace_name"
                value={values.workspace_name}
                onChange={(event) => update('workspace_name', event.target.value)}
                aria-invalid={Boolean(errors.workspace_name)}
                aria-describedby={errors.workspace_name ? 'workspace_name-error' : undefined}
                className={inputClass(Boolean(errors.workspace_name))}
              />
            </Field>
          ) : null}
          {values.workspace_type !== 'personal' ? <Field id="invite_code" label="Join with a workspace code instead (optional)">
            <input id="invite_code" value={values.invite_code} onChange={(event) => update('invite_code', event.target.value)} placeholder="PUCHOO-…" className={inputClass(false)} />
            <p className="mt-2 text-xs leading-relaxed text-[#64748b]">A code links you to the owner’s tenant after your email and OTP are verified. It never exposes another workspace in the picker.</p>
          </Field>
          : null}
          <PillButton type="submit" variant="dark" disabled={pending} className="auth-form-wide w-full">
            {pending ? 'Creating account…' : 'Get started'}
          </PillButton>
        </form>
      </AuthShell>
      {toast ? (
        <div
          role="alert"
          className="fixed right-4 bottom-4 z-50 max-w-sm rounded-2xl bg-[#111827] px-4 py-3 text-sm text-white"
        >
          {toast}
        </div>
      ) : null}
    </>
  );
}
