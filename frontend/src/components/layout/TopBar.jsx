import { Bell, ChevronDown, ShieldCheck, Search } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useAuth } from '../../context/AuthContext';

export default function TopBar() {
  const { activeWorkspace } = useAppContext();
  const { user } = useAuth();

  return (
    <header
      style={{
        height: '64px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 2rem',
        borderBottom: '1px solid var(--border-color)',
        backgroundColor: 'var(--bg-surface)',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          color: 'var(--accent-green)',
        }}
      >
        <ShieldCheck size={20} />
        <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>
          {activeWorkspace ? `${activeWorkspace.name} · Guardrails active` : 'Guardrails active'}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            backgroundColor: 'var(--bg-surface-raised)',
            padding: '0.375rem 0.75rem',
            borderRadius: 'var(--radius-input)',
            border: '1px solid var(--border-color)',
          }}
        >
          <Search size={16} color="var(--text-muted)" />
          <input
            type="text"
            placeholder="Search questions, SQL, history…"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-primary)',
              outline: 'none',
              width: '260px',
              fontSize: '0.875rem',
            }}
          />
        </div>

        <button type="button" aria-label="Notifications" className="btn btn-secondary" style={{ padding: '0.55rem' }}><Bell size={17} /></button>
        <button type="button"
          style={{
            width: '32px',
            height: '32px',
            borderRadius: '50%',
            backgroundColor: 'var(--bg-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 'bold',
            cursor: 'pointer', border: 'none',
          }}
        >
          {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
        </button>
        <ChevronDown size={16} color="var(--text-muted)" />
      </div>
    </header>
  );
}
