import { useState } from 'react';
import { Check, Copy, KeyRound, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { createWorkspaceInvite } from '../../api/auth';
import { useAuth } from '../../context/AuthContext';

const roleCopy = {
  admin: 'Can administer this shared workspace and manage data. The workspace owner controls role-code rotation.',
  editor: 'Can connect and work with data, but cannot delete workspaces, data, or shared history.',
  viewer: 'Can inspect workspace history and approved queries only. No uploads, queries, or settings changes.',
};

export default function WorkspaceInvitePanel() {
  const { user } = useAuth();
  const [role, setRole] = useState('editor');
  const [codes, setCodes] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');

  const isOwner = !user?.workspace_owner_id && !user?.institute_owner_id;
  const sharedWorkspace = user?.workspace_type === 'business' || user?.workspace_type === 'institution';
  const roles = ['admin', 'editor', 'viewer'];

  if (!sharedWorkspace || !isOwner) return null;

  async function generate() {
    setBusy(true);
    setNotice('');
    try {
      const result = await createWorkspaceInvite(role);
      setCodes((current) => ({ ...current, [role]: result.code }));
      setNotice(`${role[0].toUpperCase()}${role.slice(1)} code is ready to share.`);
    } catch (error) {
      setNotice(error.message || 'Could not generate an invite code.');
    } finally {
      setBusy(false);
    }
  }

  async function copyCode() {
    const code = codes[role];
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setNotice('Code copied. Share it only with the intended person.');
    } catch {
      setNotice('Copy is unavailable in this browser. Select the code and copy it manually.');
    }
  }

  const code = codes[role];
  const workspaceLabel = user.workspace_name || user.institute_name || 'your shared workspace';
  return (
    <section className="card" aria-labelledby="workspace-invites" style={{ marginBottom: '1.5rem', borderColor: '#bfdbfe', background: 'linear-gradient(135deg, #f8fbff, #eff6ff)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', color: '#1d4ed8', fontSize: '.8rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.08em' }}><Users size={16} /> Share access</div>
          <h2 id="workspace-invites" style={{ margin: '.45rem 0' }}>Invite people to {workspaceLabel}</h2>
          <p style={{ margin: 0, maxWidth: '48rem', color: 'var(--text-muted)', fontSize: '.9rem', lineHeight: 1.55 }}>Each person uses their own email, password, and OTP. This code only grants the selected role inside this isolated workspace.</p>
        </div>
        <span className="badge badge-ok" style={{ display: 'inline-flex', gap: '.35rem', alignItems: 'center' }}><ShieldCheck size={14} /> Tenant isolated</span>
      </div>

      <div role="tablist" aria-label="Invite role" style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap', marginTop: '1.1rem' }}>
        {roles.map((nextRole) => <button key={nextRole} type="button" role="tab" aria-selected={role === nextRole} className={role === nextRole ? 'btn btn-primary' : 'btn btn-secondary'} onClick={() => { setRole(nextRole); setNotice(''); }} style={{ textTransform: 'capitalize' }}>{nextRole}</button>)}
      </div>
      <p style={{ margin: '.75rem 0 0', color: 'var(--text-muted)', fontSize: '.85rem' }}><strong style={{ color: 'var(--text-primary)', textTransform: 'capitalize' }}>{role}:</strong> {roleCopy[role]}</p>

      <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center', flexWrap: 'wrap', marginTop: '1.1rem' }}>
        {code ? <><code style={{ flex: '1 1 250px', padding: '.8rem 1rem', borderRadius: '10px', background: '#0f172a', color: '#e0f2fe', fontWeight: 700, letterSpacing: '.08em' }}>{code}</code><button type="button" className="btn btn-secondary" onClick={copyCode}><Copy size={15} /> Copy</button></> : <div style={{ color: 'var(--text-muted)', fontSize: '.875rem' }}><KeyRound size={15} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '.35rem' }} />No {role} code has been generated in this session.</div>}
        <button type="button" className="btn btn-primary" onClick={generate} disabled={busy}>{busy ? <RefreshCw className="voice-spinner" size={15} /> : code ? <RefreshCw size={15} /> : <KeyRound size={15} />}{busy ? 'Generating…' : code ? `Rotate ${role} code` : `Generate ${role} code`}</button>
      </div>
      <p style={{ margin: '.8rem 0 0', color: '#4b5563', fontSize: '.78rem', lineHeight: 1.45 }}><Check size={13} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '.25rem', color: '#16a34a' }} />Codes are stored as hashes on the server, shown only when generated, and rotating one role code leaves the other role codes valid. A recipient can use the same code from another device with their own email, password, and OTP.</p>
      {notice && <p role="status" style={{ margin: '.75rem 0 0', color: notice.includes('Could not') ? '#b42318' : '#166534', fontSize: '.85rem' }}>{notice}</p>}
    </section>
  );
}
