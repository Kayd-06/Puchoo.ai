import { useState, useEffect } from 'react';
import { ShieldCheck, History as HistoryIcon, User } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { createInstituteInvite } from '../api/auth';

export default function Settings() {
  const { activeWorkspaceId } = useAppContext();
  const { user } = useAuth();
  const [guardrails, setGuardrails] = useState(null);
  const [inviteCode, setInviteCode] = useState('');

  useEffect(() => {
    async function loadGuardrails() {
      if (activeWorkspaceId) {
        try {
          const data = await fetchApi(`/settings/guardrails/${activeWorkspaceId}`);
          setGuardrails(data);
        } catch (err) {
          console.error(err);
        }
      }
    }
    loadGuardrails();
  }, [activeWorkspaceId]);

  async function generateInvite() {
    const result = await createInstituteInvite();
    setInviteCode(result.code);
  }

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

      {user?.workspace_type === 'institute' && !user.institute_owner_id && (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <h3 style={{ marginBottom: '0.5rem' }}>Invite institute members</h3>
          <p className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>Share a code so members can join with their own email and password.</p>
          {inviteCode && <code style={{ display: 'block', padding: '0.8rem', marginBottom: '1rem', background: 'var(--bg-surface-raised)', borderRadius: '8px' }}>{inviteCode}</code>}
          <button className="btn btn-primary" onClick={generateInvite}>{inviteCode ? 'Rotate invite code' : 'Generate invite code'}</button>
        </div>
      )}

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
                {user?.workspace_type === 'institute' ? 'Institute member' : 'Personal workspace'}
              </span>
            </h3>
            <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: '0.875rem' }}>
              {user?.institute_name || 'Puchoo.ai workspace'} • {user?.email || 'email@example.com'}
            </p>
          </div>
          <span className="badge badge-ok">Email verified</span>
        </div>

        <div
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
            <input type="text" className="input" value={user?.institute_name || (user?.workspace_type === 'institute' ? 'Institute members' : 'Personal')} readOnly />
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
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}
        >
          <ShieldCheck size={20} color="var(--bg-primary)" /> Safety &amp; Guardrails{' '}
          <span className="badge badge-ok">Strict Active</span>
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '1rem',
              background: 'var(--bg-surface-raised)',
              borderRadius: 'var(--radius-input)',
            }}
          >
            <div>
              <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>
                Read-only mode <span className="badge badge-ok">System Enforced</span>
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Pucho is physically restricted from running INSERT, UPDATE, DELETE, or DROP
                commands.
              </div>
            </div>
            <div
              style={{
                color: 'var(--accent-green)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
              }}
            >
              <ShieldCheck size={16} /> Locked ON
            </div>
          </div>

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '1rem',
              background: 'var(--bg-surface-raised)',
              borderRadius: 'var(--radius-input)',
            }}
          >
            <div>
              <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>Automatic row limit</div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                Prevents massive runaway queries and keeps responses fast.
              </div>
            </div>
            <select
              className="input"
              style={{ width: '120px' }}
              defaultValue={guardrails?.max_rows || 100}
            >
              <option value={100}>100 rows</option>
              <option value={500}>500 rows</option>
              <option value={1000}>1000 rows</option>
            </select>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}
        >
          <HistoryIcon size={20} color="var(--text-muted)" /> Session &amp; History
        </h3>
        <p className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>
          Manage query records stored in your browser session.
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
          <div style={{ fontSize: '0.875rem', color: 'var(--accent-red)' }}>
            Pucho stores your past questions and summaries locally. Clearing will erase cached
            prompt completions.
          </div>
          <button className="btn btn-danger">Clear query history</button>
        </div>
      </div>
    </div>
  );
}
