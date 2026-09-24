import { NavLink } from 'react-router-dom';
import { MessageSquare, Database, History, Settings } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';

export default function Sidebar() {
  const { workspaces, activeWorkspace, activeWorkspaceId, setActiveWorkspaceId } = useAppContext();

  const navItems = [
    { to: "/ask", icon: MessageSquare, label: "Ask Data" },
    { to: "/connect", icon: Database, label: "Connect Data" },
    { to: "/history", icon: History, label: "History" },
    { to: "/settings", icon: Settings, label: "Settings" }
  ];

  return (
    <aside style={{
      width: '260px',
      backgroundColor: 'var(--bg-surface)',
      borderRight: '1px solid var(--border-color)',
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      padding: '1.5rem 0'
    }}>
      <div style={{ padding: '0 1.5rem', marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <div style={{
          width: '32px', height: '32px',
          background: 'var(--bg-primary)',
          borderRadius: '8px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 'bold'
        }}>P</div>
        <h2 style={{ fontSize: '1.25rem', margin: 0, fontWeight: 700 }}>Pucho AI</h2>
      </div>

      <nav style={{ flex: 1, padding: '0 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `btn ${isActive ? 'btn-primary' : 'btn-secondary'}`}
            style={({ isActive }) => ({
              justifyContent: 'flex-start',
              padding: '0.75rem 1rem',
              color: isActive ? 'var(--text-on-primary)' : 'var(--text-primary)',
              backgroundColor: isActive ? 'var(--bg-primary)' : 'transparent',
              border: isActive ? 'none' : '1px solid transparent',
              borderRadius: 'var(--radius-input)',
              display: 'flex',
              gap: '0.75rem'
            })}
          >
            <item.icon size={20} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div style={{ padding: '1.5rem', borderTop: '1px solid var(--border-color)', marginTop: 'auto' }}>
          <label htmlFor="workspace-selector" style={{ display: 'block', fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '0.5rem' }}>Active DB</label>
          <select
            id="workspace-selector"
            className="input"
            value={activeWorkspaceId || ''}
            onChange={(event) => setActiveWorkspaceId(event.target.value || null)}
            disabled={workspaces.length === 0}
            aria-label="Select active database"
            style={{ padding: '0.6rem 0.75rem', marginBottom: '0.75rem' }}
          >
            {workspaces.length === 0 && <option value="">No database connected</option>}
            {workspaces.map(workspace => (
              <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
            ))}
          </select>
          {activeWorkspace && (
            <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <div style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-green)' }}></div>
            <span style={{ fontSize: '0.875rem', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {activeWorkspace.name}
            </span>
          </div>
          <span className="badge badge-ok">Read-only</span>
            </>
          )}
        </div>
    </aside>
  );
}
