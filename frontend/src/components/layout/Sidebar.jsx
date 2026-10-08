import { NavLink } from 'react-router-dom';
import { Database, History, MessageSquare, Plus, Settings, ShieldCheck } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useAuth } from '../../context/AuthContext';

const NAV_ITEMS = [
  { to: '/ask', icon: MessageSquare, label: 'Ask data', hint: 'New query' },
  { to: '/connect', icon: Database, label: 'Data sources', hint: 'Connect' },
  { to: '/history', icon: History, label: 'History', hint: 'Review' },
  { to: '/settings', icon: Settings, label: 'Settings', hint: 'Workspace' },
];

export default function Sidebar() {
  const { workspaces, activeWorkspace, activeWorkspaceId, setActiveWorkspaceId } = useAppContext();
  const { user } = useAuth();
  const isViewer = user?.workspace_role === 'viewer';
  const navItems = NAV_ITEMS.filter((item) => !isViewer || item.to === '/history');

  return (
    <aside className="app-sidebar" aria-label="Workspace navigation">
      <div className="app-sidebar-brand">
        <img src="/puchoo-logo-192.png" className="app-brand-mark puchoo-brand-logo" alt="" aria-hidden="true" draggable="false" />
        <div><strong>Puchoo.si</strong><span>Secure intelligence</span></div>
      </div>

      <div className="app-sidebar-section-label">Workspace</div>
      <nav className="app-sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `app-sidebar-link${isActive ? ' is-active' : ''}`}>
              <Icon size={18} strokeWidth={1.8} />
              <span><b>{item.label}</b><small>{item.hint}</small></span>
            </NavLink>
          );
        })}
      </nav>

      <div className="app-sidebar-bottom">
        <div className="app-sidebar-section-label">Active data source</div>
        {workspaces.length ? (
          <label className="workspace-picker">
            <select value={activeWorkspaceId || ''} onChange={(event) => setActiveWorkspaceId(event.target.value || null)} aria-label="Select active data source">
              {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
            </select>
          </label>
        ) : <NavLink to="/connect" className="workspace-empty"><Plus size={15} /> Connect data</NavLink>}
        <div className="workspace-access-note"><ShieldCheck size={14} /><span>{activeWorkspace ? `${isViewer ? 'Viewer' : 'Read-only'} access` : 'No source selected'}</span></div>
      </div>
    </aside>
  );
}
