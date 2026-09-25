import { ShieldCheck, Search } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';

export default function TopBar() {
  const { profile } = useAppContext();

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
          Hardware Enclave &amp; Guardrails Active
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
            placeholder="Search insights..."
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-primary)',
              outline: 'none',
              width: '200px',
              fontSize: '0.875rem',
            }}
          />
        </div>

        <div
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
            cursor: 'pointer',
          }}
        >
          {profile?.name ? profile.name.charAt(0).toUpperCase() : 'U'}
        </div>
      </div>
    </header>
  );
}
