import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { createRecoveryCodes } from '../../api/auth';

export default function RecoveryCodesPanel() {
  const [password, setPassword] = useState('');
  const [codes, setCodes] = useState([]);
  const [message, setMessage] = useState('');
  const [pending, setPending] = useState(false);

  async function generate(event) {
    event.preventDefault();
    if (!password) {
      setMessage('Enter your current password to create recovery codes.');
      return;
    }
    setPending(true);
    setMessage('');
    try {
      const result = await createRecoveryCodes({ current_password: password });
      setCodes(result.codes);
      setPassword('');
      setMessage('Save these codes now. They are not shown again.');
    } catch (error) {
      setMessage(error.message || 'Unable to create recovery codes.');
    } finally {
      setPending(false);
    }
  }

  return <section className="settings-section recovery-codes-panel" aria-labelledby="recovery-codes-title">
    <div className="settings-section-heading"><span className="settings-section-icon"><KeyRound size={18} /></span><div><span className="settings-section-kicker">Account recovery</span><h2 id="recovery-codes-title">Recovery OTPs</h2></div></div>
    <p className="settings-section-copy">Create single-use recovery codes as a secure fallback when a login email is delayed or unavailable. They never replace your password and are stored only as hashes.</p>
    {codes.length ? <div className="recovery-codes-result"><strong>Save these now — they will not be displayed again.</strong><div className="recovery-codes-grid">{codes.map((code) => <code key={code}>{code}</code>)}</div></div> : null}
    <form onSubmit={generate} className="recovery-codes-form">
      <label>Current password<input className="input" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
      <button className="settings-action" type="submit" disabled={pending}>{pending ? 'Creating…' : codes.length ? 'Replace codes' : 'Create recovery codes'}</button>
    </form>
    {message ? <p role="status" className={`settings-notice ${codes.length ? 'is-success' : ''}`}>{message}</p> : null}
  </section>;
}
