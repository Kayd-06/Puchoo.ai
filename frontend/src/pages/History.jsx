import { useState, useEffect } from 'react';
import { ShieldCheck, CheckCircle2, AlertTriangle, ShieldAlert, History as HistoryIcon } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

export default function History() {
  const { activeWorkspaceId } = useAppContext();
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadHistory() {
      if (!activeWorkspaceId) return;
      try {
        const data = await fetchApi(`/history/${activeWorkspaceId}`);
        setHistory(data || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadHistory();
  }, [activeWorkspaceId]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '2rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: 'var(--bg-primary)' }}>
            <HistoryIcon size={20} />
            <span style={{ fontWeight: 600, fontSize: '0.875rem', textTransform: 'uppercase' }}>Audit &amp; Traceability</span>
          </div>
          <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Query history</h1>
          <p style={{ color: 'var(--text-muted)' }}>
            Review the questions you asked and the answers Pucho generated. Every execution is cryptographically signed and read-only verified.
          </p>
        </div>
        
        <div style={{ display: 'flex', gap: '1rem' }}>
          <div className="card" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ background: 'var(--accent-green-bg)', padding: '0.5rem', borderRadius: '50%', color: 'var(--accent-green)' }}>
              <ShieldCheck size={24} />
            </div>
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>96.4%</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Safe pass rate</div>
            </div>
          </div>
          <div className="card" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ background: 'rgba(79, 110, 247, 0.1)', padding: '0.5rem', borderRadius: '50%', color: 'var(--bg-primary)' }}>
              <HistoryIcon size={24} />
            </div>
            <div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>142ms</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Avg latency</div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
        <input type="text" className="input" placeholder="Search your questions, tables, or metric key..." style={{ flex: 1 }} />
        <div style={{ display: 'flex', background: 'var(--bg-surface)', padding: '0.25rem', borderRadius: 'var(--radius-input)', border: '1px solid var(--border-color)' }}>
          <button className="btn btn-secondary" style={{ background: 'var(--bg-surface-raised)', border: 'none' }}>All</button>
          <button className="btn btn-secondary" style={{ border: 'none' }}>Verified</button>
          <button className="btn btn-secondary" style={{ border: 'none' }}>Needs review</button>
          <button className="btn btn-secondary" style={{ border: 'none' }}>Blocked</button>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {loading ? (
          <p className="text-muted">Loading history...</p>
        ) : history.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
            <p className="text-muted">No query history found for this workspace.</p>
          </div>
        ) : (
          history.map(item => (
            <div key={item.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <h3 style={{ fontSize: '1.125rem' }}>{item.question}</h3>
                {item.status === 'blocked' ? (
                   <span className="badge badge-bad"><ShieldAlert size={14} style={{ marginRight: '4px' }}/> Blocked for safety</span>
                ) : item.verification?.status === 'VERIFIED' ? (
                   <span className="badge badge-ok"><CheckCircle2 size={14} style={{ marginRight: '4px' }}/> Verified</span>
                ) : (
                   <span className="badge badge-warn"><AlertTriangle size={14} style={{ marginRight: '4px' }}/> Needs review</span>
                )}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                {new Date(item.created_at).toLocaleString()} • {item.row_count || 0} rows scanned
              </div>
              {item.sql && (
                <div style={{ background: 'var(--bg-surface-raised)', padding: '1rem', borderRadius: 'var(--radius-input)', fontFamily: 'monospace', fontSize: '0.875rem', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}>
                  {item.sql}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
