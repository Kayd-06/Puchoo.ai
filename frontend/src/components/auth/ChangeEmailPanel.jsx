import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Mail, X } from 'lucide-react';
import PasswordField from './PasswordField';
import OtpInput from './OtpInput';
import { Field, inputClass } from './AuthShell';
import { PillButton } from '../landing/ui';
import { useAuth } from '../../context/AuthContext';

export default function ChangeEmailPanel() {
  const { user, requestEmailChange, verifyEmailChange } = useAuth();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState('details');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);
  const dialogRef = useRef(null);
  const openerRef = useRef(null);

  const close = useCallback(() => {
    setOpen(false);
    setStep('details');
    setEmail('');
    setPassword('');
    setCode('');
    setMessage('');
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        close();
        return;
      }
      if (event.key !== 'Tab') return;
      const controls = [
        ...dialogRef.current.querySelectorAll(
          'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
        ),
      ];
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (
        event.shiftKey &&
        (document.activeElement === first || !dialogRef.current.contains(document.activeElement))
      ) {
        event.preventDefault();
        last?.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !dialogRef.current.contains(document.activeElement))
      ) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
      if (openerRef.current?.isConnected) openerRef.current.focus();
    };
  }, [open, close]);
  useEffect(() => {
    if (open)
      (
        dialogRef.current?.querySelector('input:not(:disabled)') ||
        dialogRef.current?.querySelector('button')
      )?.focus();
  }, [open, step]);

  async function requestCode(event) {
    event.preventDefault();
    setMessage('');
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setMessage('Enter a valid new email address.');
      return;
    }
    if (!password) {
      setMessage('Enter your current password to continue.');
      return;
    }
    setPending(true);
    try {
      const result = await requestEmailChange({
        new_email: email.trim().toLowerCase(),
        current_password: password,
      });
      setEmail(result.email);
      setPassword('');
      setStep('verify');
      setMessage(`A six-digit code was sent to ${result.email}.`);
    } catch (error) {
      setMessage(error.message || 'We could not start the email change.');
    } finally {
      setPending(false);
    }
  }
  async function confirmCode(event) {
    event.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setMessage('Enter the six-digit code from your new email.');
      return;
    }
    setPending(true);
    setMessage('');
    try {
      await verifyEmailChange({ new_email: email, code });
      setStep('complete');
      setMessage('Your verified email address has been updated.');
    } catch (error) {
      setMessage(error.message || 'That code is invalid or expired.');
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="settings-action"
        onClick={(event) => {
          openerRef.current = event.currentTarget;
          setOpen(true);
        }}
      >
        Change email
      </button>
      {open &&
        createPortal(
          <div
            className="settings-email-overlay fixed inset-0 z-[80] grid place-items-center bg-black/75 p-4 backdrop-blur-sm"
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="email-change-title"
          >
            <div className="settings-email-dialog w-full max-w-md p-6 md:p-8">
              <div className="flex items-start justify-between gap-5">
                <div>
                  <div className="settings-email-dialog-icon">
                    <Mail size={18} />
                  </div>
                  <h2 id="email-change-title">
                    {step === 'verify'
                      ? 'Verify your new email'
                      : step === 'complete'
                        ? 'Email updated'
                        : 'Change email address'}
                  </h2>
                  <p>
                    {step === 'details'
                      ? `For your security, confirm the password for ${user?.email}.`
                      : step === 'verify'
                        ? `Enter the code delivered to ${email}. It expires in 5 minutes.`
                        : 'Your account now uses the new verified email address.'}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={close}
                  aria-label="Close"
                  className="settings-email-dialog-close"
                >
                  <X size={18} />
                </button>
              </div>
              <div className="mt-7">
                {step === 'details' && (
                  <form className="space-y-4" onSubmit={requestCode} noValidate>
                    <Field id="new-email" label="New email address">
                      <input
                        id="new-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(event) => setEmail(event.target.value)}
                        className={inputClass(false)}
                      />
                    </Field>
                    <PasswordField
                      id="change-email-password"
                      label="Current password"
                      autoComplete="current-password"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                    />
                    <PillButton type="submit" variant="dark" disabled={pending}>
                      {pending ? 'Sending code…' : 'Send verification code'}
                    </PillButton>
                  </form>
                )}
                {step === 'verify' && (
                  <form className="space-y-4" onSubmit={confirmCode} noValidate>
                    <OtpInput
                      id="new-email-code"
                      value={code}
                      onChange={setCode}
                      disabled={pending}
                      autoFocus
                    />
                    <PillButton type="submit" variant="dark" disabled={pending}>
                      {pending ? 'Verifying…' : 'Verify and update email'}
                    </PillButton>
                    <button
                      type="button"
                      onClick={() => {
                        setStep('details');
                        setCode('');
                        setMessage('');
                      }}
                      className="settings-email-dialog-link"
                    >
                      Use another address
                    </button>
                  </form>
                )}
                {step === 'complete' && (
                  <button
                    type="button"
                    onClick={close}
                    className="ui-action ui-action-primary inline-flex items-center gap-2 rounded-full bg-[#0c1830] px-5 py-3 text-sm font-medium text-white"
                  >
                    <Check size={16} />
                    Done
                  </button>
                )}
                {message && (
                  <p role="status" className="mt-4 text-sm text-[#334d81]">
                    {message}
                  </p>
                )}
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
