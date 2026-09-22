import { useEffect, useMemo, useState } from 'react';
import { ShieldCheck, CheckCircle2, AlertTriangle, ShieldAlert, History as HistoryIcon, Trash2 } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'verified', label: 'Verified' },
  { id: 'review', label: 'Needs review' },
  { id: 'blocked', label: 'Blocked' },
];

function recordCategory(item) {
  if (item.status === 'blocked') return 'blocked';
  return item.verification?.status === 'VERIFIED' ? 'verified' : 'review';
}

export default function History() {
  const { activeWorkspaceId, activeWorkspace } = useAppContext();
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadHistory() {
      setError('');
      setHistory([]);
      if (!activeWorkspaceId) return;
      setLoading(true);
      try {
        const data = await fetchApi(`/history/${activeWorkspaceId}`);
        if (!cancelled) setHistory(data || []);
      } catch (err) {
        if (!cancelled) setError(err.message || 'Could not load query history.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadHistory();
    return () => { cancelled = true; };
  }, [activeWorkspaceId]);

  const visibleHistory = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return history.filter(item => {
      const matchesFilter = filter === 'all' || recordCategory(item) === filter;
      const matchesSearch = !needle || `${item.question || ''} ${item.sql || ''}`.toLowerCase().includes(needle);
      return matchesFilter && matchesSearch;
    });
  }, [history, search, filter]);

  const executed = history.filter(item => item.status === 'executed');
  const safeCount = executed.filter(item => item.verification?.status !== 'FAILED').length;
  const safeRate = executed.length ? `${((safeCount / executed.length) * 100).toFixed(1)}%` : '—';
  const timed = executed.filter(item => Number.isFinite(Number(item.elapsed_ms)));
  const averageLatency = timed.length
    ? `${Math.round(timed.reduce((sum, item) => sum + Number(item.elapsed_ms), 0) / timed.length)}ms`
    : '—';

  const clearHistory = async () => {
    if (!activeWorkspaceId || history.length === 0) return;
    if (!window.confirm(`Clear all query history for ${activeWorkspace?.name || 'this database'}?`)) return;
    setClearing(true);
    setError('');
    try {
      await fetchApi(`/history/${activeWorkspaceId}`, { method: 'DELETE' });
      setHistory([]);
    } catch (err) {
      setError(err.message || 'Could not clear query history.');
    } finally {
      setClearing(false);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '2rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 420px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: 'var(--bg-primary)' }}>
            <HistoryIcon size={20} />
            <span style={{ fontWeight: 600, fontSize: '0.875rem', textTransform: 'uppercase' }}>Audit &amp; Traceability</span>
          </div>
          <h1 style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>Query history</h1>
          <p style={{ color: 'var(--text-muted)' }}>
            {activeWorkspace ? `Showing activity for ${activeWorkspace.name}.` : 'Select or connect a database to view its history.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <div className="card" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <ShieldCheck size={24} color="var(--accent-green)" />
            <div><div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{safeRate}</div><div className="text-xs text-muted">Safe pass rate</div></div>
          </div>
          <div className="card" style={{ padding: '1rem', display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <HistoryIcon size={24} color="var(--bg-primary)" />
            <div><div style={{ fontSize: '1.25rem', fontWeight: 600 }}>{averageLatency}</div><div className="text-xs text-muted">Avg DB latency</div></div>
          </div>
        </div>
      </div>

      {error && <div className="card" role="alert" style={{ marginBottom: '1rem', color: 'var(--accent-red)', background: 'var(--accent-red-bg)' }}>{error}</div>}

      <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem', flexWrap: 'wrap' }}>
        <input value={search} onChange={event => setSearch(event.target.value)} type="search" className="input" placeholder="Search questions or SQL..." style={{ flex: '1 1 320px' }} />
        <div style={{ display: 'flex', background: 'var(--bg-surface)', padding: '0.25rem', borderRadius: 'var(--radius-input)', border: '1px solid var(--border-color)' }}>
          {FILTERS.map(option => (
            <button key={option.id} className="btn btn-secondary" onClick={() => setFilter(option.id)} aria-pressed={filter === option.id} style={{ background: filter === option.id ? 'var(--bg-surface-raised)' : 'transparent', border: 'none' }}>{option.label}</button>
          ))}
        </div>
        <button className="btn btn-danger" onClick={clearHistory} disabled={clearing || history.length === 0}><Trash2 size={16} style={{ marginRight: '0.4rem' }} />{clearing ? 'Clearing...' : 'Clear history'}</button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {loading ? <p className="text-muted">Loading history...</p> : visibleHistory.length === 0 ? (
          <div className="card" style={{ textAlign: 'center', padding: '3rem' }}><p className="text-muted">{history.length ? 'No history matches these filters.' : 'No query history found for this database.'}</p></div>
        ) : visibleHistory.map(item => (
          <div key={item.id} className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
              <h3 style={{ fontSize: '1.125rem' }}>{item.question}</h3>
              {recordCategory(item) === 'blocked' ? <span className="badge badge-bad"><ShieldAlert size={14} /> Blocked</span> : recordCategory(item) === 'verified' ? <span className="badge badge-ok"><CheckCircle2 size={14} /> Verified</span> : <span className="badge badge-warn"><AlertTriangle size={14} /> Needs review</span>}
            </div>
            <div className="text-sm text-muted">{new Date(item.executed_at || item.created_at).toLocaleString()} • {item.row_count ?? 0} rows • {item.elapsed_ms ?? 0}ms</div>
            {item.sql && <pre style={{ background: 'var(--bg-surface-raised)', padding: '1rem', borderRadius: 'var(--radius-input)', fontSize: '0.875rem', border: '1px solid var(--border-color)', overflowX: 'auto', whiteSpace: 'pre-wrap' }}>{item.sql}</pre>}
          </div>
        ))}
      </div>
    </div>
  );
}
