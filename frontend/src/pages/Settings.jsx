import { ShieldCheck, History as HistoryIcon, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import ChangeEmailPanel from '../components/auth/ChangeEmailPanel';
import WorkspaceInvitePanel from '../components/workspace/WorkspaceInvitePanel';

export default function Settings() {
  const { user } = useAuth();
  const navigate = useNavigate();

  return (
    <div style={{ maxWidth: '800px' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          marginBottom: '0.5rem',
          color: 'var(--accent-green)',
        }}
      >
        <ShieldCheck size={20} />
        <span style={{ fontWeight: 600, fontSize: '0.875rem', textTransform: 'uppercase' }}>
          System Preferences
        </span>
      </div>
      <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Settings</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
        Manage your profile, connected databases, and query safety defaults.
      </p>

      <WorkspaceInvitePanel />

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
          <div
            style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              background: 'var(--bg-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
              fontSize: '1.5rem',
              fontWeight: 'bold',
            }}
          >
            {user?.full_name ? user.full_name.charAt(0).toUpperCase() : <User />}
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: '1.25rem', margin: 0 }}>
              {user?.full_name || 'User'}{' '}
              <span
                className="badge badge-info"
                style={{ marginLeft: '0.5rem', verticalAlign: 'middle' }}
              >
                {user?.workspace_type === 'institution' ? `Institution ${user?.workspace_role || 'member'}` : user?.workspace_type === 'business' ? `Business ${user?.workspace_role || 'member'}` : 'Personal workspace'}
              </span>
            </h3>
            <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: '0.875rem' }}>
              {user?.workspace_name || user?.institute_name || 'Puchoo.ai workspace'} • {user?.email || 'email@example.com'}
            </p>
          </div>
          <span className="badge badge-ok">Email verified</span>
        </div>

        <div
          className="settings-profile-grid"
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1rem',
            marginBottom: '1rem',
          }}
        >
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.875rem',
                color: 'var(--text-muted)',
                marginBottom: '0.5rem',
              }}
            >
              Full Name
            </label>
            <input type="text" className="input" value={user?.full_name || ''} readOnly />
          </div>
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.875rem',
                color: 'var(--text-muted)',
                marginBottom: '0.5rem',
              }}
            >
              Email Address
            </label>
            <input type="email" className="input" value={user?.email || ''} readOnly />
          </div>
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.875rem',
                color: 'var(--text-muted)',
                marginBottom: '0.5rem',
              }}
            >
              Department / Workspace
            </label>
            <input type="text" className="input" value={user?.workspace_name || user?.institute_name || (user?.workspace_type === 'institution' ? 'Institution' : user?.workspace_type === 'business' ? 'Business' : 'Personal')} readOnly />
          </div>
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.875rem',
                color: 'var(--text-muted)',
                marginBottom: '0.5rem',
              }}
            >
              Timezone
            </label>
            <input type="text" className="input" value={Intl.DateTimeFormat().resolvedOptions().timeZone} readOnly />
          </div>
        </div>
        <p className="text-muted" style={{ fontSize: '0.8rem', marginTop: '0.5rem' }}>Account details come from your verified Puchoo.ai profile.</p>
        <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}><ChangeEmailPanel /></div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}
        >
          <HistoryIcon size={20} color="var(--text-muted)" /> Session &amp; History
        </h3>
        <p className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>
          Review and manage the query history for your active workspace.
        </p>

        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'rgba(239, 68, 68, 0.05)',
            padding: '1rem',
            borderRadius: 'var(--radius-input)',
            border: '1px solid rgba(239, 68, 68, 0.1)',
          }}
        >
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            Open History to review queries, search records, or clear the active workspace history.
          </div>
          <button className="btn btn-secondary" onClick={() => navigate('/history')}>Manage history</button>
        </div>
      </div>
    </div>
  );
}
