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
  institute_name: '',
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
    if (values.workspace_type === 'institute' && !values.institute_name.trim()) {
      next.institute_name = 'Institute name is required.';
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
        institute_name: values.workspace_type === 'institute' ? values.institute_name.trim() : null,
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
      <title>Get started · Puchoo.ai</title>
      <AuthShell
        title="Create your workspace"
        subtitle="Personal for you, or an institute workspace for your college."
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
        <form className="space-y-5" onSubmit={onSubmit} noValidate>
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
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-[#111827]">Workspace</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {[
                ['personal', 'Personal'],
                ['institute', 'Institute members'],
              ].map(([value, label]) => (
                <label
                  key={value}
                  className={`flex items-center gap-2 rounded-2xl border border-black/10 px-3 py-3 text-sm ${focusRing}`}
                >
                  <input
                    type="radio"
                    name="workspace_type"
                    value={value}
                    checked={values.workspace_type === value}
                    onChange={() => update('workspace_type', value)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          {values.workspace_type === 'institute' ? (
            <Field id="institute_name" label="Institute name" error={errors.institute_name}>
              <input
                id="institute_name"
                name="institute_name"
                value={values.institute_name}
                onChange={(event) => update('institute_name', event.target.value)}
                aria-invalid={Boolean(errors.institute_name)}
                aria-describedby={errors.institute_name ? 'institute_name-error' : undefined}
                className={inputClass(Boolean(errors.institute_name))}
              />
            </Field>
          ) : null}
          <PillButton type="submit" variant="dark" disabled={pending}>
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
