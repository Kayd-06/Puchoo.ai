import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import AuthShell, { Field, inputClass } from '../components/auth/AuthShell';
import PasswordField, { passwordIsValid } from '../components/auth/PasswordField';
import { PillButton, focusRing } from '../components/landing/ui';
import { forgotPassword, resetPassword } from '../api/auth';

export default function ForgotPassword() {
  const navigate = useNavigate(); const [step, setStep] = useState('email'); const [email, setEmail] = useState(''); const [code, setCode] = useState(''); const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState(''); const [message, setMessage] = useState(''); const [pending, setPending] = useState(false);
  async function request(event) { event.preventDefault(); setPending(true); setMessage(''); try { await forgotPassword({ email: email.trim().toLowerCase() }); setStep('reset'); setMessage('If that account exists, a 6-digit code is on its way.'); } catch (error) { setMessage(error.message); } finally { setPending(false); } }
  async function reset(event) { event.preventDefault(); if (!/^\d{6}$/.test(code) || !passwordIsValid(password) || password !== confirm) { setMessage('Use a 6-digit code and a matching password with at least 10 characters, a letter, and a number.'); return; } setPending(true); setMessage(''); try { await resetPassword({ email: email.trim().toLowerCase(), code, password, confirm_password: confirm }); navigate('/login', { replace: true }); } catch (error) { setMessage(error.message); } finally { setPending(false); } }
  return <AuthShell title={step === 'email' ? 'Reset your password' : 'Choose a new password'} subtitle={step === 'email' ? 'We’ll send a one-time code to your verified email.' : `Enter the code sent to ${email}.`} footer={<>Remembered it? <Link to="/login" className={`text-[#111827] underline-offset-4 hover:underline ${focusRing}`}>Log in</Link></>}>
    {step === 'email' ? <form className="space-y-5" onSubmit={request}><Field id="email" label="Email"><input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass(false)} required /></Field><PillButton type="submit" variant="dark" disabled={pending}>{pending ? 'Sending code…' : 'Send reset code'}</PillButton></form> : <form className="space-y-5" onSubmit={reset}><Field id="code" label="Verification code"><input id="code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} className={inputClass(false)} required /></Field><PasswordField id="new-password" label="New password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} /><PasswordField id="confirm-password" label="Confirm new password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} /><PillButton type="submit" variant="dark" disabled={pending}>{pending ? 'Updating…' : 'Update password'}</PillButton></form>}
    {message ? <p role="status" className="mt-5 text-sm text-[#334d81]">{message}</p> : null}
  </AuthShell>;
}
