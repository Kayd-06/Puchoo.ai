import { useEffect, useState } from 'react';
import { Check, Copy, KeyRound, RefreshCw, Trash2, Users } from 'lucide-react';
import {
  createWorkspaceInvite,
  listWorkspaceMembers,
  removeWorkspaceMember,
  updateWorkspaceMemberRole,
} from '../../api/auth';
import { can } from '../../auth/capabilities';
import { useAuth } from '../../context/AuthContext';

const roleCopy = {
  admin:
    'Can administer this shared workspace, manage data, rotate invite codes, and manage members.',
  editor:
    'Can query existing data and review history, but cannot add, connect, delete, or configure sources.',
  viewer:
    'Can inspect workspace history and approved queries only. No uploads, queries, or settings changes.',
};

export default function WorkspaceInvitePanel() {
  const { user } = useAuth();
  const [role, setRole] = useState('editor');
  const [codes, setCodes] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [members, setMembers] = useState([]);
  const [membersBusy, setMembersBusy] = useState(true);

  const sharedWorkspace =
    user?.workspace_type === 'business' || user?.workspace_type === 'institution';
  const canAdminister = can(user, 'administer_workspace');
  const roles = ['admin', 'editor', 'viewer'];

  useEffect(() => {
    if (!sharedWorkspace || !canAdminister) return undefined;
    let current = true;
    listWorkspaceMembers()
      .then((items) => {
        if (current) setMembers(items);
      })
      .catch((error) => {
        if (current) setNotice(error.message || 'Could not load workspace members.');
      })
      .finally(() => {
        if (current) setMembersBusy(false);
      });
    return () => {
      current = false;
    };
  }, [sharedWorkspace, canAdminister]);

  if (!sharedWorkspace || !canAdminister) return null;

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

  async function changeMemberRole(member, nextRole) {
    setNotice('');
    try {
      const updated = await updateWorkspaceMemberRole(member.id, nextRole);
      setMembers((current) => current.map((item) => (item.id === member.id ? updated : item)));
      setNotice(`${member.full_name}'s role is now ${nextRole}.`);
    } catch (error) {
      setNotice(error.message || 'Could not update that member.');
    }
  }

  async function removeMember(member) {
    if (!window.confirm(`Remove ${member.full_name} from this workspace?`)) return;
    setNotice('');
    try {
      await removeWorkspaceMember(member.id);
      setMembers((current) => current.filter((item) => item.id !== member.id));
      setNotice(`${member.full_name} was removed from this workspace.`);
    } catch (error) {
      setNotice(error.message || 'Could not remove that member.');
    }
  }

  const code = codes[role];
  const workspaceLabel = user.workspace_name || user.institute_name || 'your shared workspace';
  return (
    <section
      className="settings-section workspace-invite-panel"
      aria-labelledby="workspace-invites"
    >
      <div className="workspace-invite-heading">
        <div>
          <div className="settings-section-kicker">
            <Users size={16} /> Share access
          </div>
          <h2 id="workspace-invites">Invite people to {workspaceLabel}</h2>
          <p>
            Each person uses their own email, password, and OTP. This code only grants the selected
            role inside this isolated workspace.
          </p>
        </div>
      </div>

      <div role="tablist" aria-label="Invite role" className="workspace-role-tabs">
        {roles.map((nextRole) => (
          <button
            key={nextRole}
            type="button"
            role="tab"
            aria-selected={role === nextRole}
            className={role === nextRole ? 'is-active' : ''}
            onClick={() => {
              setRole(nextRole);
              setNotice('');
            }}
          >
            {nextRole}
          </button>
        ))}
      </div>
      <p className="workspace-role-copy">
        <strong>{role}:</strong> {roleCopy[role]}
      </p>

      <div className="workspace-code-row">
        {code ? (
          <>
            <code>{code}</code>
            <button type="button" className="settings-action" onClick={copyCode}>
              <Copy size={15} /> Copy
            </button>
          </>
        ) : (
          <div className="workspace-code-empty">
            <KeyRound size={15} />
            No {role} code has been generated in this session.
          </div>
        )}
        <button
          type="button"
          className="settings-action settings-action-primary"
          onClick={generate}
          disabled={busy}
        >
          {busy ? (
            <RefreshCw className="voice-spinner" size={15} />
          ) : code ? (
            <RefreshCw size={15} />
          ) : (
            <KeyRound size={15} />
          )}
          {busy ? 'Generating…' : code ? `Rotate ${role} code` : `Generate ${role} code`}
        </button>
      </div>
      <p className="workspace-security-note">
        <Check size={13} />
        Codes are stored as hashes on the server, shown only when generated, and rotating one role
        code leaves the other role codes valid. A recipient can use the same code from another
        device with their own email, password, and OTP.
      </p>
      <div className="workspace-members" aria-busy={membersBusy}>
        <div className="workspace-members-heading">
          <strong>Workspace members</strong>
          <span>{membersBusy ? 'Loading…' : `${members.length} total`}</span>
        </div>
        {!membersBusy &&
          members.map((member) => (
            <div className="workspace-member" key={member.id}>
              <div>
                <strong>{member.full_name}</strong>
                <span>{member.email}</span>
              </div>
              {member.role === 'owner' ? (
                <span className="workspace-member-owner">Owner</span>
              ) : (
                <>
                  <select
                    className="workspace-member-role"
                    aria-label={`Role for ${member.full_name}`}
                    value={member.role}
                    onChange={(event) => changeMemberRole(member, event.target.value)}
                  >
                    {roles.map((memberRole) => (
                      <option key={memberRole} value={memberRole}>
                        {memberRole}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="workspace-member-remove"
                    aria-label={`Remove ${member.full_name}`}
                    onClick={() => removeMember(member)}
                  >
                    <Trash2 size={15} />
                  </button>
                </>
              )}
            </div>
          ))}
      </div>
      {notice && (
        <p
          role="status"
          className={`settings-notice ${notice.includes('Could not') ? 'is-error' : 'is-success'}`}
        >
          {notice}
        </p>
      )}
    </section>
  );
}
