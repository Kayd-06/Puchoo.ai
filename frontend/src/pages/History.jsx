import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Code2,
  History as HistoryIcon,
  MessageSquarePlus,
  Rows3,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  X,
} from 'lucide-react';
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

function formatTimestamp(value) {
  if (!value) return 'Just now';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Recent' : date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}

function StatusBadge({ category }) {
  if (category === 'blocked') return <span className="badge badge-bad"><ShieldAlert size={14} /> Blocked</span>;
  if (category === 'verified') return <span className="badge badge-ok"><CheckCircle2 size={14} /> Verified</span>;
  return <span className="badge badge-warn"><AlertTriangle size={14} /> Needs review</span>;
}

export default function History() {
  const navigate = useNavigate();
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
      const matchesSearch = !needle || `${item.question || ''} ${item.interpreted_request || ''} ${item.sql || ''}`.toLowerCase().includes(needle);
      return matchesFilter && matchesSearch;
    });
  }, [history, search, filter]);

  const categoryCounts = useMemo(() => history.reduce((counts, item) => {
    counts.all += 1;
    counts[recordCategory(item)] += 1;
    return counts;
  }, { all: 0, verified: 0, review: 0, blocked: 0 }), [history]);

  const executed = history.filter(item => item.status === 'executed');
  const verifiedRate = executed.length ? `${Math.round((categoryCounts.verified / executed.length) * 100)}%` : '—';
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

  const continueConversation = (item) => {
    navigate('/ask', {
      state: {
        continuation: {
          question: item.question,
          interpretedRequest: item.interpreted_request,
          rowCount: item.row_count,
          languageCode: item.language_code,
        },
      },
    });
  };

  const resetFilters = () => {
    setFilter('all');
    setSearch('');
  };

  const activeFilter = FILTERS.find(option => option.id === filter);

  return (
    <div className="history-page">
      <section className="history-hero">
        <div>
          <div className="history-eyebrow"><HistoryIcon size={16} /> Query activity</div>
          <h1>History</h1>
          <p>{activeWorkspace ? `Your recent questions for ${activeWorkspace.name}. Pick one to ask a follow-up.` : 'Select a database to view its history.'}</p>
        </div>
        <div className="history-metrics" aria-label="History summary">
          <div className="history-metric"><span className="history-metric-icon metric-safe"><ShieldCheck size={18} /></span><div><strong>{verifiedRate}</strong><span>Verified rate</span></div></div>
          <div className="history-metric"><span className="history-metric-icon metric-time"><Clock3 size={18} /></span><div><strong>{averageLatency}</strong><span>Average response</span></div></div>
        </div>
      </section>

      {error && <div className="card" role="alert" style={{ marginBottom: '1rem', color: 'var(--accent-red)', background: 'var(--accent-red-bg)' }}>{error}</div>}

      <section className="history-toolbar" aria-label="Filter history">
        <label className="history-search">
          <Search size={18} aria-hidden="true" />
          <input value={search} onChange={event => setSearch(event.target.value)} type="search" placeholder="Search questions or SQL" aria-label="Search questions or SQL" />
          {search && <button type="button" onClick={() => setSearch('')} aria-label="Clear search"><X size={16} /></button>}
        </label>
        <div className="history-filters" role="group" aria-label="Filter by status">
          {FILTERS.map(option => (
            <button key={option.id} type="button" onClick={() => setFilter(option.id)} aria-pressed={filter === option.id} className={filter === option.id ? 'is-active' : ''}>
              <span>{option.label}</span><span className="history-filter-count">{categoryCounts[option.id]}</span>
            </button>
          ))}
        </div>
        <button className="btn btn-danger history-clear" onClick={clearHistory} disabled={clearing || history.length === 0}><Trash2 size={16} />{clearing ? 'Clearing…' : 'Clear history'}</button>
      </section>

      <div className="history-list-header">
        <span>{activeFilter.label}: {visibleHistory.length} {visibleHistory.length === 1 ? 'question' : 'questions'}</span>
        <span>Newest first</span>
      </div>

      <div className="history-list">
        {loading ? <p className="text-muted">Loading history…</p> : visibleHistory.length === 0 ? (
          <div className="card history-empty">
            <HistoryIcon size={24} />
            <h3>{history.length ? `No ${activeFilter.label.toLowerCase()} questions found` : 'No questions yet'}</h3>
            <p className="text-muted">{history.length ? 'Try a different status, or clear your search.' : 'Ask your first data question and it will appear here.'}</p>
            {history.length > 0 && <button className="btn btn-secondary" onClick={resetFilters}>Show all history</button>}
          </div>
        ) : visibleHistory.map(item => {
          const category = recordCategory(item);
          const context = item.interpreted_request && item.interpreted_request !== item.question ? item.interpreted_request : null;
          return (
            <article key={item.id} className="history-card">
              <div className="history-card-main">
                <div className="history-card-topline"><span>{formatTimestamp(item.executed_at || item.created_at)}</span><StatusBadge category={category} /></div>
                <h2>{item.question}</h2>
                {context && <p className="history-context">Interpreted as: {context}</p>}
                <div className="history-meta">
                  <span><Rows3 size={15} /> {item.row_count ?? 0} rows returned</span>
                  <span><Clock3 size={15} /> {item.elapsed_ms ?? 0}ms</span>
                  {item.model_attempts > 1 && <span>{item.model_attempts} attempts</span>}
                </div>
              </div>
              <div className="history-card-actions">
                <button className="btn btn-primary" onClick={() => continueConversation(item)}><MessageSquarePlus size={16} /> Continue chat</button>
                {item.sql && <details className="sql-details"><summary><Code2 size={16} /> View SQL <ChevronDown size={15} /></summary><pre>{item.sql}</pre></details>}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
