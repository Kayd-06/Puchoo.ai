import { useCallback, useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Check,
  ChevronDown,
  Database,
  History,
  MessageSquare,
  Plus,
  Settings,
  ShieldCheck,
} from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useAuth } from '../../context/AuthContext';
import { can } from '../../auth/capabilities';

const NAV_ITEMS = [
  {
    to: '/ask',
    icon: MessageSquare,
    label: 'Ask data',
    hint: 'New query',
    capability: 'query_workspace',
  },
  {
    to: '/connect',
    icon: Database,
    label: 'Data sources',
    hint: 'Connect',
    capability: 'manage_data_sources',
  },
  { to: '/history', icon: History, label: 'History', hint: 'Review', capability: 'view_history' },
  {
    to: '/settings',
    icon: Settings,
    label: 'Settings',
    hint: 'Account',
    capability: 'manage_account',
  },
];

const SELECTOR_SPARKS = [
  [-56, -4],
  [-42, -17],
  [-27, -25],
  [-10, -19],
  [9, -27],
  [28, -17],
  [48, -8],
  [-48, 11],
  [-29, 20],
  [-8, 25],
  [13, 20],
  [34, 14],
  [54, 5],
];
const PICKER_CLOSE_DURATION = 180;

export default function Sidebar() {
  const { workspaces, activeWorkspace, activeWorkspaceId, setActiveWorkspaceId } = useAppContext();
  const { user } = useAuth();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerClosing, setPickerClosing] = useState(false);
  const [burstKey, setBurstKey] = useState(0);
  const pickerRef = useRef(null);
  const pickerTriggerRef = useRef(null);
  const closeTimerRef = useRef(null);
  const navItems = NAV_ITEMS.filter((item) => can(user, item.capability));
  const role = user?.role || user?.workspace_role || 'viewer';
  const selectedWorkspace =
    activeWorkspace || workspaces.find((workspace) => workspace.id === activeWorkspaceId);

  const closePicker = useCallback(() => {
    if (!pickerOpen || pickerClosing) return;
    setPickerClosing(true);
    pickerTriggerRef.current?.focus();
    closeTimerRef.current = window.setTimeout(() => {
      setPickerOpen(false);
      setPickerClosing(false);
    }, PICKER_CLOSE_DURATION);
  }, [pickerClosing, pickerOpen]);

  const togglePicker = () => {
    if (pickerOpen) {
      closePicker();
      return;
    }
    window.clearTimeout(closeTimerRef.current);
    setPickerClosing(false);
    setPickerOpen(true);
  };

  useEffect(() => {
    if (!pickerOpen) return undefined;
    const closeOnOutsidePointer = (event) => {
      if (!pickerRef.current?.contains(event.target)) closePicker();
    };
    const closeOnEscape = (event) => {
      if (event.key !== 'Escape') return;
      closePicker();
    };
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [closePicker, pickerOpen]);

  useEffect(() => () => window.clearTimeout(closeTimerRef.current), []);

  const chooseWorkspace = (workspaceId) => {
    if (workspaceId !== activeWorkspaceId) setBurstKey((current) => current + 1);
    setActiveWorkspaceId(workspaceId || null);
    closePicker();
  };

  return (
    <aside className="app-sidebar" aria-label="Workspace navigation">
      <div className="app-sidebar-brand">
        <img
          src="/puchoo-logo-192.png"
          className="app-brand-mark puchoo-brand-logo"
          alt=""
          aria-hidden="true"
          draggable="false"
        />
        <div>
          <strong>Puchoo.si</strong>
          <span>Secure intelligence</span>
        </div>
      </div>

      <div className="app-sidebar-section-label">Workspace</div>
      <nav className="app-sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `app-sidebar-link${isActive ? ' is-active' : ''}`}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>
                <b>{item.label}</b>
                <small>{item.hint}</small>
              </span>
            </NavLink>
          );
        })}
      </nav>

      <div className="app-sidebar-bottom">
        <div className="app-sidebar-section-label">Active data source</div>
        {workspaces.length ? (
          <div
            ref={pickerRef}
            className={`workspace-picker${pickerOpen ? ' is-open' : ''}${pickerClosing ? ' is-closing' : ''}`}
          >
            <button
              ref={pickerTriggerRef}
              type="button"
              className="workspace-picker-trigger"
              aria-label="Select active data source"
              aria-haspopup="listbox"
              aria-expanded={pickerOpen && !pickerClosing}
              aria-controls="active-data-source-options"
              onClick={togglePicker}
            >
              <span className="workspace-picker-dot" aria-hidden="true" />
              <span className="workspace-picker-value">
                {selectedWorkspace?.name || 'Select data source'}
              </span>
              <ChevronDown className="workspace-picker-chevron" size={16} aria-hidden="true" />
            </button>
            {burstKey > 0 && (
              <span key={burstKey} className="workspace-picker-burst" aria-hidden="true">
                {SELECTOR_SPARKS.map(([x, y], index) => (
                  <i
                    key={index}
                    style={{
                      '--spark-x': `${x}px`,
                      '--spark-y': `${y}px`,
                      '--spark-delay': `${index * 13}ms`,
                    }}
                  />
                ))}
              </span>
            )}
            {pickerOpen && (
              <div
                id="active-data-source-options"
                className={`workspace-picker-menu${pickerClosing ? ' is-closing' : ''}`}
                role="listbox"
                aria-label="Active data sources"
              >
                {workspaces.map((workspace) => {
                  const selected = workspace.id === activeWorkspaceId;
                  return (
                    <button
                      key={workspace.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`workspace-picker-option${selected ? ' is-selected' : ''}`}
                      onClick={() => chooseWorkspace(workspace.id)}
                    >
                      <Database size={14} aria-hidden="true" />
                      <span>{workspace.name}</span>
                      {selected && <Check size={14} aria-hidden="true" />}
                    </button>
                  );
                })}
              </div>
            )}
            <span className="workspace-picker-status" aria-live="polite">
              {burstKey ? `${selectedWorkspace?.name || 'Data source'} selected` : ''}
            </span>
          </div>
        ) : can(user, 'manage_data_sources') ? (
          <NavLink to="/connect" className="workspace-empty">
            <Plus size={15} /> Connect data
          </NavLink>
        ) : (
          <span className="workspace-empty">No shared data yet</span>
        )}
        <div className="workspace-access-note">
          <ShieldCheck size={14} />
          <span>{activeWorkspace ? `${role} access` : 'No source selected'}</span>
        </div>
      </div>
    </aside>
  );
}
