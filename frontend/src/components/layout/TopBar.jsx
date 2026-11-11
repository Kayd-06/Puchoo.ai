import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  Menu,
  CheckCheck,
  ChevronDown,
  LogOut,
  Trash2,
  UserRound,
  Settings,
  Moon,
  Sun,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { fetchApi } from '../../api/client';
import ThemeToggle from '../ThemeToggle';
import './notifications.css';
import './accountMenu.css';
import { useTheme } from '../../context/ThemeContext';

function timeLabel(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Just now';
  const elapsed = Math.max(0, Date.now() - date.getTime());
  if (elapsed < 60_000) return 'Just now';
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}m ago`;
  if (elapsed < 86_400_000) return `${Math.floor(elapsed / 3_600_000)}h ago`;
  return date.toLocaleDateString();
}

export default function TopBar({ onOpenNavigation }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { theme, toggleTheme } = useTheme();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [deletingNotification, setDeletingNotification] = useState('');
  const [notificationError, setNotificationError] = useState('');
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
        setNotifications((current) =>
          [incoming, ...current.filter((item) => item.id !== incoming.id)].slice(0, 12),
        );
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
      if (notificationRef.current && !notificationRef.current.contains(event.target))
        setOpen(false);
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
      setNotifications((current) =>
        current.map((item) =>
          item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item,
        ),
      );
      setUnreadCount((count) => Math.max(0, count - 1));
    } catch {
      // Keep the persisted unread state if the request fails.
    }
  }

  async function deleteNotification(notification) {
    if (deletingNotification) return;
    setDeletingNotification(notification.id);
    setNotificationError('');
    try {
      await fetchApi(`/notifications/${encodeURIComponent(notification.id)}`, { method: 'DELETE' });
      setNotifications((current) => current.filter((item) => item.id !== notification.id));
      if (!notification.read_at) setUnreadCount((count) => Math.max(0, count - 1));
    } catch {
      setNotificationError('Could not delete this notification. Please try again.');
    } finally {
      setDeletingNotification('');
    }
  }

  async function markAllRead() {
    try {
      await fetchApi('/notifications/read-all', { method: 'POST' });
      setNotifications((current) =>
        current.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() })),
      );
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

  const avatar = (className = 'topbar-avatar') => (
    <span className={`${className}${user?.image_url ? ' has-image' : ''}`}>
      {user?.image_url ? (
        <img src={user.image_url} alt="" referrerPolicy="no-referrer" />
      ) : user?.full_name ? (
        user.full_name.charAt(0).toUpperCase()
      ) : (
        <UserRound size={20} fill="currentColor" strokeWidth={1.5} aria-hidden="true" />
      )}
    </span>
  );

  return (
    <header className="app-topbar">
      {onOpenNavigation && (
        <button
          type="button"
          className="workspace-menu-trigger"
          onClick={onOpenNavigation}
          aria-label="Open workspace menu"
          aria-haspopup="dialog"
          aria-controls="workspace-navigation"
        >
          <Menu size={20} />
          <span>Workspace</span>
        </button>
      )}
      <div className="app-topbar-actions">
        <ThemeToggle />
        <div ref={notificationRef} className="topbar-menu-anchor">
          <button
            type="button"
            aria-label="Notifications"
            aria-expanded={open}
            className={`topbar-icon-button notification-bell-button${open ? ' is-active' : ''}`}
            onClick={() => {
              setOpen((value) => !value);
              setAccountOpen(false);
            }}
          >
            <Bell size={18} fill="currentColor" strokeWidth={1.5} aria-hidden="true" />
            {unreadCount > 0 && (
              <span
                className="topbar-notification-count"
                aria-label={`${unreadCount} unread notifications`}
              >
                <span className="notification-sr-only">{unreadCount}</span>
              </span>
            )}
          </button>
          {open && (
            <section
              aria-label="Notifications"
              className="topbar-popover topbar-notification-panel"
            >
              <header className="topbar-popover-header">
                <div>
                  <span>Activity</span>
                  <strong>Notifications</strong>
                </div>
                {unreadCount > 0 && (
                  <button type="button" className="topbar-text-button" onClick={markAllRead}>
                    <CheckCheck size={14} /> Mark all read
                  </button>
                )}
              </header>
              {notificationError && (
                <p role="alert" className="notification-error">
                  {notificationError}
                </p>
              )}
              <div className="topbar-notification-list">
                {notifications.length === 0 ? (
                  <p className="topbar-empty-state">
                    Your important workspace activity will appear here.
                  </p>
                ) : (
                  notifications.map((notification) => (
                    <div key={notification.id} className="notification-row">
                      <button
                        type="button"
                        onClick={() => markRead(notification)}
                        className={`topbar-notification-item${notification.read_at ? '' : ' is-unread'}`}
                      >
                        <div>
                          <strong>{notification.title}</strong>
                          <span>{timeLabel(notification.created_at)}</span>
                        </div>
                        {notification.body && <p>{notification.body}</p>}
                      </button>
                      <button
                        type="button"
                        className="notification-delete"
                        aria-label={`Delete notification: ${notification.title}`}
                        disabled={Boolean(deletingNotification)}
                        onClick={() => deleteNotification(notification)}
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </section>
          )}
        </div>
        <div ref={accountRef} className="topbar-menu-anchor">
          <button
            type="button"
            aria-label="Account menu"
            aria-expanded={accountOpen}
            onClick={() => {
              setAccountOpen((value) => !value);
              setOpen(false);
            }}
            className={`topbar-account-button${accountOpen ? ' is-active' : ''}`}
          >
            {avatar()}
            {user?.full_name && <span className="account-trigger-name">{user.full_name}</span>}
            <ChevronDown
              size={14}
              className={accountOpen ? 'account-chevron-open' : ''}
              aria-hidden="true"
            />
          </button>
          {accountOpen && (
            <section aria-label="Account menu" className="topbar-popover topbar-account-panel">
              <div className="topbar-account-summary">
                {avatar()}
                <div className="topbar-account-copy">
                  <strong>{user?.full_name || user?.email}</strong>
                  <span className="topbar-account-email" title={user?.email}>
                    {user?.email}
                  </span>
                </div>
              </div>
              <div className="account-menu-links">
                <button
                  type="button"
                  onClick={() => {
                    setAccountOpen(false);
                    navigate('/settings');
                  }}
                >
                  <Settings size={16} aria-hidden="true" /> Profile settings
                </button>
                <button type="button" onClick={toggleTheme}>
                  {theme === 'dark' ? (
                    <Sun size={16} aria-hidden="true" />
                  ) : (
                    <Moon size={16} aria-hidden="true" />
                  )}
                  {theme === 'dark' ? 'Light mode' : 'Dark mode'}
                </button>
              </div>
              <button
                type="button"
                className="topbar-logout-button"
                onClick={onLogout}
                disabled={loggingOut}
              >
                <LogOut size={16} />
                {loggingOut ? 'Logging out…' : 'Log out'}
              </button>
            </section>
          )}
        </div>
      </div>
    </header>
  );
}
