import { ShieldCheck, History as HistoryIcon, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ChangeEmailPanel from '../components/auth/ChangeEmailPanel';
import RecoveryCodesPanel from '../components/auth/RecoveryCodesPanel';
import WorkspaceInvitePanel from '../components/workspace/WorkspaceInvitePanel';

export default function Settings() {
  const { user } = useAuth();
  const navigate = useNavigate();

  if (user?.workspace_role === 'viewer') {
    return <section className="settings-viewer-state">
      <span className="settings-eyebrow"><ShieldCheck size={16} /> Read-only member</span>
      <h1>Settings are managed by your workspace.</h1>
      <p>Viewer accounts can inspect approved query history, but cannot change workspace settings, data sources, or access roles.</p>
      <button className="settings-action settings-action-primary" onClick={() => navigate('/history')}>Open history</button>
    </section>;
  }

  return (
    <div className="settings-page">
      <header className="settings-hero">
        <div className="settings-eyebrow">
        <ShieldCheck size={20} />
          <span>System preferences</span>
        </div>
        <div className="settings-hero-copy">
          <div>
            <h1>Settings</h1>
            <p>Control your profile, workspace access, and secure sign-in recovery.</p>
          </div>
          <span className="settings-security-chip"><ShieldCheck size={15} /> Tenant isolated</span>
        </div>
      </header>

      <div className="settings-flow">
        <WorkspaceInvitePanel />
        <RecoveryCodesPanel />

        <section className="settings-section settings-profile" aria-labelledby="profile-title">
          <div className="settings-profile-topline">
            <div className="settings-avatar">
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : <User />}
            </div>
            <div className="settings-profile-identity">
              <div className="settings-profile-titleline">
                <h2 id="profile-title">{user?.full_name || 'User'}</h2>
                <span className="settings-workspace-badge">
                  {user?.workspace_type === 'institution' ? `Institution ${user?.workspace_role || 'member'}` : user?.workspace_type === 'business' ? `Business ${user?.workspace_role || 'member'}` : 'Personal workspace'}
                </span>
              </div>
              <p>{user?.workspace_name || user?.institute_name || 'Puchoo.ai workspace'} <span>•</span> {user?.email || 'email@example.com'}</p>
            </div>
            <span className="settings-verified"><ShieldCheck size={14} /> Email verified</span>
          </div>

          <div className="settings-profile-grid">
            <label>Full name<input type="text" className="input" value={user?.full_name || ''} readOnly /></label>
            <label>Email address<input type="email" className="input" value={user?.email || ''} readOnly /></label>
            <label>Department / workspace<input type="text" className="input" value={user?.workspace_name || user?.institute_name || (user?.workspace_type === 'institution' ? 'Institution' : user?.workspace_type === 'business' ? 'Business' : 'Personal')} readOnly /></label>
            <label>Timezone<input type="text" className="input" value={Intl.DateTimeFormat().resolvedOptions().timeZone} readOnly /></label>
          </div>
          <div className="settings-section-footer">
            <p>Identity information comes from your verified Puchoo.ai profile.</p>
            <ChangeEmailPanel />
          </div>
        </section>

        <section className="settings-section settings-history" aria-labelledby="session-history-title">
          <div className="settings-history-icon"><HistoryIcon size={19} /></div>
          <div>
            <span className="settings-section-kicker">Workspace records</span>
            <h2 id="session-history-title">Session &amp; history</h2>
            <p>Review queries, inspect generated SQL, and manage the active workspace record.</p>
          </div>
          <button className="settings-action" onClick={() => navigate('/history')}>Manage history <span aria-hidden="true">↗</span></button>
        </section>
      </div>
    </div>
  );
}
