import { useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import AuthShell, { Field, inputClass } from '../components/auth/AuthShell';
import PasswordField from '../components/auth/PasswordField';
import { PillButton, focusRing } from '../components/landing/ui';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { requestLogin, resendLoginCode, verifyLogin } = useAuth();
  const [email, setEmail] = useState(() => location.state?.email || '');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState(() => (location.state?.verificationPending ? 'code' : 'password'));
  const [errors, setErrors] = useState({});
  const [toast, setToast] = useState('');
  const [pending, setPending] = useState(false);
  const [recoveryAvailable, setRecoveryAvailable] = useState(false);
  const [emailDelivered, setEmailDelivered] = useState(true);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(''), 5200);
    return () => clearTimeout(timer);
  }, [toast]);

  async function onSubmit(event) {
    event.preventDefault();
    const next = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
      next.email = 'Enter a valid email address.';
    if (!password) next.password = 'Enter your password.';
    setErrors(next);
    if (Object.keys(next).length) return;
    setPending(true);
    setToast('');
    try {
      const challenge = await requestLogin({ email: email.trim().toLowerCase(), password });
      setRecoveryAvailable(Boolean(challenge.recovery_available));
      setEmailDelivered(challenge.email_delivered !== false);
      setStep('code');
      setToast(challenge.email_delivered === false
        ? 'Email delivery is unavailable. Use one of your recovery codes.'
        : 'We sent a 6-digit code to your email.');
    } catch (error) {
      setToast(error.message || 'Invalid email or password');
    } finally {
      setPending(false);
    }
  }

  async function onVerify(event) {
    event.preventDefault();
    const normalizedCode = code.trim().toUpperCase();
    if (!/^\d{6}$/.test(normalizedCode) && !/^PCH-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(normalizedCode)) {
      setErrors({ code: 'Enter a 6-digit email code or PCH-XXXX-XXXX recovery code.' });
      return;
    }
    setPending(true);
    setToast('');
    try {
      await verifyLogin({ email: email.trim().toLowerCase(), code: normalizedCode });
      navigate('/ask', { replace: true });
    } catch (error) {
      setToast(error.message || 'That code is invalid or has expired.');
    } finally {
      setPending(false);
    }
  }

  async function onResend() {
    setPending(true);
    setToast('');
    setErrors({});
    try {
      const challenge = await resendLoginCode({ email: email.trim().toLowerCase() });
      setCode('');
      setRecoveryAvailable(Boolean(challenge.recovery_available));
      setEmailDelivered(challenge.email_delivered !== false);
      setToast(challenge.email_delivered === false
        ? 'Email delivery is still unavailable. Use one of your recovery codes.'
        : 'We sent a new 6-digit code to your email.');
    } catch (error) {
      setToast(error.message || 'Unable to resend the verification code.');
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <title>Log in · Puchoo.ai</title>
      <AuthShell
        title={step === 'code' ? 'Check your email' : 'Log in'}
        subtitle={
          step === 'code'
            ? recoveryAvailable
              ? `Enter the 6-digit email code sent to ${email.trim().toLowerCase()} or one of your recovery codes.`
              : `Enter the 6-digit code sent to ${email.trim().toLowerCase()}. It expires in 10 minutes.`
            : 'A verification code is emailed after your password is accepted.'
        }
        footer={
          <>
            New to Puchoo.ai?{' '}
            <Link
              to="/signup"
              className={`text-[#111827] underline-offset-4 hover:underline ${focusRing} rounded-full`}
            >
              Get started
            </Link>
          </>
        }
      >
        {step === 'code' ? (
          <form className="space-y-5" onSubmit={onVerify} noValidate>
            <Field id="code" label="Verification code" error={errors.code}>
              <input
                id="code"
                name="code"
                inputMode={recoveryAvailable ? 'text' : 'numeric'}
                autoComplete="one-time-code"
                maxLength={13}
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 13))}
                aria-invalid={Boolean(errors.code)}
                aria-describedby={errors.code ? 'code-error' : undefined}
                className={`${inputClass(Boolean(errors.code))} tracking-[0.4em]`}
              />
            </Field>
            {recoveryAvailable ? <p className="rounded-xl border border-[#9dbaf5]/50 bg-white/55 px-3 py-2 text-xs leading-relaxed text-[#3f5474]">{emailDelivered ? 'Email delayed? ' : 'Email is currently unavailable. '}Use a saved <strong>PCH-XXXX-XXXX</strong> recovery code. Each code works once.</p> : null}
            <PillButton type="submit" variant="dark" disabled={pending}>
              {pending ? 'Checking code…' : 'Verify and continue'}
            </PillButton>
            <button
              type="button"
              className={`text-sm text-[#111827] underline-offset-4 hover:underline ${focusRing} rounded-full`}
              disabled={pending}
              onClick={onResend}
            >
              Resend code
            </button>
            <button
              type="button"
              className={`ml-4 text-sm text-[#111827] underline-offset-4 hover:underline ${focusRing} rounded-full`}
              disabled={pending}
              onClick={() => {
                setStep('password');
                setCode('');
                setErrors({});
                setToast('');
              }}
            >
              Use a different email
            </button>
          </form>
        ) : null}
        {step === 'password' ? (
          <form className="space-y-5" onSubmit={onSubmit} noValidate>
            <Field id="email" label="Email" error={errors.email}>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? 'email-error' : undefined}
                className={inputClass(Boolean(errors.email))}
              />
            </Field>
            <PasswordField
              id="password"
              label="Password"
              autoComplete="current-password"
              value={password}
              error={errors.password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <div className="-mt-2 text-right">
              <Link to="/forgot-password" className={`text-sm text-[#334d81] underline-offset-4 hover:underline ${focusRing} rounded-full`}>Forgot password?</Link>
            </div>
            <PillButton type="submit" variant="dark" disabled={pending}>
              {pending ? 'Logging in…' : 'Log in'}
            </PillButton>
          </form>
        ) : null}
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
