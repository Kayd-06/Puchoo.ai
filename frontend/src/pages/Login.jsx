import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import AuthShell, { Field, inputClass } from '../components/auth/AuthShell';
import PasswordField from '../components/auth/PasswordField';
import { PillButton, focusRing } from '../components/landing/ui';
import { useAuth } from '../context/AuthContext';

const CHALLENGE_SECONDS = 5 * 60;
const RESEND_SECONDS = 60;
const LOGIN_EXPIRED = 'Login session expired, please sign in again';

function formatClock(total) {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

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
  const [challengeLeft, setChallengeLeft] = useState(CHALLENGE_SECONDS);
  const [resendLeft, setResendLeft] = useState(RESEND_SECONDS);

  useEffect(() => {
    if (!toast) return undefined;
    const timer = setTimeout(() => setToast(''), 5200);
    return () => clearTimeout(timer);
  }, [toast]);

  const returnToLogin = useCallback((message) => {
    setStep('password');
    setCode('');
    setErrors({});
    setToast(message);
    navigate('/login', { replace: true, state: null });
  }, [navigate]);

  useEffect(() => {
    if (step !== 'code') return undefined;
    const timer = setInterval(() => {
      setResendLeft((value) => Math.max(0, value - 1));
      setChallengeLeft((value) => {
        if (value <= 1) returnToLogin(LOGIN_EXPIRED);
        return Math.max(0, value - 1);
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [step, returnToLogin]);

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
      await requestLogin({ email: email.trim().toLowerCase(), password });
      setChallengeLeft(CHALLENGE_SECONDS);
      setResendLeft(RESEND_SECONDS);
      setStep('code');
      setToast('We sent a 6-digit code to your email.');
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
      if (error.message === LOGIN_EXPIRED) {
        returnToLogin(error.message);
        return;
      }
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
      await resendLoginCode();
      setCode('');
      setResendLeft(RESEND_SECONDS);
      setToast('We sent a new 6-digit code to your email.');
    } catch (error) {
      if (error.message === LOGIN_EXPIRED) {
        returnToLogin(error.message);
        return;
      }
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
            ? `Enter the 6-digit code sent to ${email.trim().toLowerCase()}, or a saved recovery code.`
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
                inputMode="text"
                autoComplete="one-time-code"
                maxLength={13}
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 13))}
                aria-invalid={Boolean(errors.code)}
                aria-describedby={errors.code ? 'code-error' : undefined}
                className={`${inputClass(Boolean(errors.code))} tracking-[0.4em]`}
              />
            </Field>
            <p className="text-sm text-[#3f5474]" role="timer" aria-live="polite">
              This code expires in {formatClock(challengeLeft)}.
            </p>
            <p className="rounded-xl border border-[#9dbaf5]/50 bg-white/55 px-3 py-2 text-xs leading-relaxed text-[#3f5474]">
              Email delayed? Use a saved <strong>PCH-XXXX-XXXX</strong> recovery code. Each code works once, and only after your password is accepted.
            </p>
            <PillButton type="submit" variant="dark" disabled={pending}>
              {pending ? 'Checking code…' : 'Verify and continue'}
            </PillButton>
            <button
              type="button"
              className={`text-sm text-[#111827] underline-offset-4 hover:underline ${focusRing} rounded-full disabled:opacity-60`}
              disabled={pending || resendLeft > 0}
              onClick={onResend}
            >
              {resendLeft > 0 ? `Resend code in ${resendLeft}s` : 'Resend code'}
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
