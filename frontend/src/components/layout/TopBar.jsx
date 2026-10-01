import { useEffect, useState } from 'react';
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
        <div style={{ position: 'relative' }}>
          <button type="button" aria-label="Notifications" aria-expanded={open} className="btn btn-secondary" style={{ position: 'relative', padding: '0.55rem' }} onClick={() => setOpen((value) => !value)}>
            <Bell size={17} />
            {unreadCount > 0 && <span aria-label={`${unreadCount} unread notifications`} style={{ position: 'absolute', top: '-.35rem', right: '-.35rem', minWidth: '1.2rem', height: '1.2rem', padding: '0 .25rem', borderRadius: '999px', display: 'grid', placeItems: 'center', background: 'var(--accent-red)', color: '#fff', border: '2px solid var(--bg-surface)', fontSize: '.65rem', fontWeight: 700 }}>{unreadCount > 9 ? '9+' : unreadCount}</span>}
          </button>
          {open && <section aria-label="Notifications" className="card" style={{ position: 'absolute', top: 'calc(100% + .6rem)', right: 0, width: 'min(360px, calc(100vw - 2rem))', padding: '0', overflow: 'hidden', zIndex: 20, boxShadow: '0 18px 45px rgba(15, 23, 42, .16)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem 1rem .8rem', borderBottom: '1px solid var(--border-color)' }}><strong>Notifications</strong>{unreadCount > 0 && <button type="button" className="btn btn-secondary" onClick={markAllRead} style={{ padding: '.35rem .55rem', fontSize: '.75rem' }}><CheckCheck size={14} /> Mark all read</button>}</div>
            <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
              {notifications.length === 0 ? <p style={{ padding: '1.25rem 1rem', color: 'var(--text-muted)', fontSize: '.875rem' }}>No notifications yet. Real activity will appear here.</p> : notifications.map((notification) => <button key={notification.id} type="button" onClick={() => markRead(notification)} style={{ display: 'block', width: '100%', textAlign: 'left', border: 0, borderBottom: '1px solid var(--border-color)', padding: '.9rem 1rem', background: notification.read_at ? 'var(--bg-surface)' : '#f0f7ff', color: 'var(--text-primary)', cursor: notification.read_at ? 'default' : 'pointer' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: '.75rem', alignItems: 'baseline' }}><strong style={{ fontSize: '.86rem' }}>{notification.title}</strong><span style={{ flex: '0 0 auto', color: 'var(--text-muted)', fontSize: '.72rem' }}>{timeLabel(notification.created_at)}</span></div>{notification.body && <p style={{ margin: '.25rem 0 0', color: 'var(--text-muted)', fontSize: '.8rem', lineHeight: 1.4 }}>{notification.body}</p>}</button>)}</div>
          </section>}
        </div>
        <div style={{ position: 'relative' }}>
          <button type="button" aria-label="Account menu" aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)} style={{ display: 'flex', alignItems: 'center', gap: '.4rem', border: 0, background: 'transparent', padding: 0, cursor: 'pointer' }}>
            <span style={{ width: '32px', height: '32px', borderRadius: '50%', backgroundColor: 'var(--bg-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 'bold' }}>{user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}</span>
            <ChevronDown size={16} color="var(--text-muted)" />
          </button>
          {accountOpen && <section aria-label="Account menu" className="card" style={{ position: 'absolute', top: 'calc(100% + .6rem)', right: 0, width: 'min(260px, calc(100vw - 2rem))', padding: '.75rem', zIndex: 20, boxShadow: '0 18px 45px rgba(15, 23, 42, .16)' }}>
            <div style={{ padding: '.25rem .35rem .75rem', borderBottom: '1px solid var(--border-color)' }}>
              <strong style={{ display: 'block', fontSize: '.9rem' }}>{user?.full_name || 'Your account'}</strong>
              <span style={{ display: 'block', marginTop: '.2rem', color: 'var(--text-muted)', fontSize: '.78rem', overflowWrap: 'anywhere' }}>{user?.email}</span>
            </div>
            <button type="button" className="btn btn-secondary" onClick={onLogout} disabled={loggingOut} style={{ width: '100%', justifyContent: 'flex-start', marginTop: '.75rem', color: 'var(--accent-red)' }}><LogOut size={16} />{loggingOut ? 'Logging out…' : 'Log out'}</button>
          </section>}
        </div>
      </div>
    </header>
  );
}
