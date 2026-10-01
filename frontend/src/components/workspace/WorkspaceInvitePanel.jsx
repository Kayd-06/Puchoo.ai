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
    <section className="settings-section workspace-invite-panel" aria-labelledby="workspace-invites">
      <div className="workspace-invite-heading">
        <div>
          <div className="settings-section-kicker"><Users size={16} /> Share access</div>
          <h2 id="workspace-invites">Invite people to {workspaceLabel}</h2>
          <p>Each person uses their own email, password, and OTP. This code only grants the selected role inside this isolated workspace.</p>
        </div>
        <span className="settings-security-chip"><ShieldCheck size={14} /> Tenant isolated</span>
      </div>

      <div role="tablist" aria-label="Invite role" className="workspace-role-tabs">
        {roles.map((nextRole) => <button key={nextRole} type="button" role="tab" aria-selected={role === nextRole} className={role === nextRole ? 'is-active' : ''} onClick={() => { setRole(nextRole); setNotice(''); }}>{nextRole}</button>)}
      </div>
      <p className="workspace-role-copy"><strong>{role}:</strong> {roleCopy[role]}</p>

      <div className="workspace-code-row">
        {code ? <><code>{code}</code><button type="button" className="settings-action" onClick={copyCode}><Copy size={15} /> Copy</button></> : <div className="workspace-code-empty"><KeyRound size={15} />No {role} code has been generated in this session.</div>}
        <button type="button" className="settings-action settings-action-primary" onClick={generate} disabled={busy}>{busy ? <RefreshCw className="voice-spinner" size={15} /> : code ? <RefreshCw size={15} /> : <KeyRound size={15} />}{busy ? 'Generating…' : code ? `Rotate ${role} code` : `Generate ${role} code`}</button>
      </div>
      <p className="workspace-security-note"><Check size={13} />Codes are stored as hashes on the server, shown only when generated, and rotating one role code leaves the other role codes valid. A recipient can use the same code from another device with their own email, password, and OTP.</p>
      {notice && <p role="status" className={`settings-notice ${notice.includes('Could not') ? 'is-error' : 'is-success'}`}>{notice}</p>}
    </section>
  );
}
