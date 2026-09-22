import { useState, useEffect } from 'react';
import { Settings as SettingsIcon, ShieldCheck, Database, History as HistoryIcon, User } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

export default function Settings() {
  const { profile, activeWorkspaceId, setProfile } = useAppContext();
  const [guardrails, setGuardrails] = useState(null);

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

  return (
    <div style={{ maxWidth: '800px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: 'var(--accent-green)' }}>
        <ShieldCheck size={20} />
        <span style={{ fontWeight: 600, fontSize: '0.875rem', textTransform: 'uppercase' }}>System Preferences</span>
      </div>
      <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Settings</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
        Manage your profile, connected databases, and query safety defaults.
      </p>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
          <div style={{ 
            width: '64px', height: '64px', borderRadius: '50%', background: 'var(--bg-primary)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '1.5rem', fontWeight: 'bold'
          }}>
            {profile?.name ? profile.name.charAt(0).toUpperCase() : <User />}
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ fontSize: '1.25rem', margin: 0 }}>{profile?.name || 'User'} <span className="badge badge-info" style={{ marginLeft: '0.5rem', verticalAlign: 'middle' }}>Pro Admin</span></h3>
            <p style={{ color: 'var(--text-muted)', margin: 0, fontSize: '0.875rem' }}>{profile?.department || 'Workspace'} • {profile?.email || 'email@example.com'}</p>
          </div>
          <button className="btn btn-secondary">Change password</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Full Name</label>
            <input type="text" className="input" defaultValue={profile?.name || ''} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Email Address</label>
            <input type="email" className="input" defaultValue={profile?.email || ''} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Department / Workspace</label>
            <input type="text" className="input" defaultValue={profile?.department || ''} />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Timezone</label>
            <input type="text" className="input" defaultValue={profile?.timezone || ''} />
          </div>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-primary">Save Profile</button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
          <ShieldCheck size={20} color="var(--bg-primary)" /> Safety &amp; Guardrails <span className="badge badge-ok">Strict Active</span>
        </h3>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'var(--bg-surface-raised)', borderRadius: 'var(--radius-input)' }}>
            <div>
              <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>Read-only mode <span className="badge badge-ok">System Enforced</span></div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Pucho is physically restricted from running INSERT, UPDATE, DELETE, or DROP commands.</div>
            </div>
            <div style={{ color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <ShieldCheck size={16} /> Locked ON
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'var(--bg-surface-raised)', borderRadius: 'var(--radius-input)' }}>
            <div>
              <div style={{ fontWeight: 500, marginBottom: '0.25rem' }}>Automatic row limit</div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Prevents massive runaway queries and keeps responses fast.</div>
            </div>
            <select className="input" style={{ width: '120px' }} defaultValue={guardrails?.max_rows || 100}>
              <option value={100}>100 rows</option>
              <option value={500}>500 rows</option>
              <option value={1000}>1000 rows</option>
            </select>
          </div>
        </div>
      </div>
      
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
          <HistoryIcon size={20} color="var(--text-muted)" /> Session &amp; History
        </h3>
        <p className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>Manage query records stored in your browser session.</p>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(239, 68, 68, 0.05)', padding: '1rem', borderRadius: 'var(--radius-input)', border: '1px solid rgba(239, 68, 68, 0.1)' }}>
          <div style={{ fontSize: '0.875rem', color: 'var(--accent-red)' }}>
            Pucho stores your past questions and summaries locally. Clearing will erase cached prompt completions.
          </div>
          <button className="btn btn-danger">Clear query history</button>
        </div>
      </div>

    </div>
  );
}
