import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell, CheckCheck, ChevronDown, LogOut, ShieldCheck } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useAuth } from '../../context/AuthContext';
import { fetchApi } from '../../api/client';

function timeLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Just now';
  const elapsed = Math.max(0, Date.now() - date.getTime());
  if (elapsed < 60_000) return 'Just now';
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}m ago`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`;
  return date.toLocaleDateString();
}

export default function TopBar() {
  const { activeWorkspace } = useAppContext();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const notificationRef = useRef(null);
  const accountRef = useRef(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const result = await fetchApi('/notifications/?limit=12');
        if (active) {
          setNotifications(result.items || []);
          setUnreadCount(result.unread_count || 0);
        }
      } catch {
        // Do not turn a failed request into a fake notification.
      }
    }
    load();
    const stream = new EventSource('/api/notifications/stream', { withCredentials: true });
    stream.addEventListener('notification', (event) => {
      try {
        const incoming = JSON.parse(event.data);
        if (!active || !incoming?.id) return;
        setNotifications((current) => [incoming, ...current.filter((item) => item.id !== incoming.id)].slice(0, 12));
        if (!incoming.read_at) setUnreadCount((count) => count + 1);
      } catch {
        // Ignore malformed stream data and retain persisted notifications.
      }
    });
    return () => {
      active = false;
      stream.close();
    };
  }, []);

  useEffect(() => {
    function closeMenus(event) {
      if (notificationRef.current && !notificationRef.current.contains(event.target)) setOpen(false);
      if (accountRef.current && !accountRef.current.contains(event.target)) setAccountOpen(false);
    }
    function closeOnEscape(event) {
      if (event.key === 'Escape') {
        setOpen(false);
        setAccountOpen(false);
      }
    }
    document.addEventListener('pointerdown', closeMenus);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeMenus);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, []);

  async function markRead(notification) {
    if (notification.read_at) return;
    try {
      await fetchApi(`/notifications/${notification.id}/read`, { method: 'POST' });
      setNotifications((current) => current.map((item) => item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item));
      setUnreadCount((count) => Math.max(0, count - 1));
    } catch {
      // Keep the persisted unread state if the request fails.
    }
  }

  async function markAllRead() {
    try {
      await fetchApi('/notifications/read-all', { method: 'POST' });
      setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() })));
      setUnreadCount(0);
    } catch {
      // The panel remains usable after a transient failure.
    }
  }

  async function onLogout() {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      navigate('/login', { replace: true });
    }
  }

  return (
    <header className="app-topbar">
      <div className="app-topbar-status">
        <ShieldCheck size={20} />
        <span>{activeWorkspace ? `${activeWorkspace.name} · Guardrails active` : 'Guardrails active'}</span>
      </div>

      <div className="app-topbar-actions">
        <div ref={notificationRef} className="topbar-menu-anchor">
          <button type="button" aria-label="Notifications" aria-expanded={open} className={`topbar-icon-button${open ? ' is-active' : ''}`} onClick={() => { setOpen((value) => !value); setAccountOpen(false); }}>
            <Bell size={17} />
            {unreadCount > 0 && <span className="topbar-notification-count" aria-label={`${unreadCount} unread notifications`}>{unreadCount > 9 ? '9+' : unreadCount}</span>}
          </button>
          {open && <section aria-label="Notifications" className="topbar-popover topbar-notification-panel">
            <header className="topbar-popover-header"><div><span>Activity</span><strong>Notifications</strong></div>{unreadCount > 0 && <button type="button" className="topbar-text-button" onClick={markAllRead}><CheckCheck size={14} /> Mark all read</button>}</header>
            <div className="topbar-notification-list">
              {notifications.length === 0 ? <p className="topbar-empty-state">Your important workspace activity will appear here.</p> : notifications.map((notification) => <button key={notification.id} type="button" onClick={() => markRead(notification)} className={`topbar-notification-item${notification.read_at ? '' : ' is-unread'}`}><div><strong>{notification.title}</strong><span>{timeLabel(notification.created_at)}</span></div>{notification.body && <p>{notification.body}</p>}</button>)}</div>
          </section>}
        </div>
        <div ref={accountRef} className="topbar-menu-anchor">
          <button type="button" aria-label="Account menu" aria-expanded={accountOpen} onClick={() => { setAccountOpen((value) => !value); setOpen(false); }} className={`topbar-account-button${accountOpen ? ' is-active' : ''}`}>
            <span className="topbar-avatar">{user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}</span>
            <ChevronDown size={16} />
          </button>
          {accountOpen && <section aria-label="Account menu" className="topbar-popover topbar-account-panel">
            <div className="topbar-account-summary">
              <span className="topbar-avatar">{user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}</span>
              <div><strong>{user?.full_name || 'Your account'}</strong><span>{user?.email}</span></div>
            </div>
            <button type="button" className="topbar-logout-button" onClick={onLogout} disabled={loggingOut}><LogOut size={16} />{loggingOut ? 'Logging out…' : 'Log out'}</button>
          </section>}
        </div>
      </div>
    </header>
  );
}
