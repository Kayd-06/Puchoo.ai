import { useState } from 'react';
import { Play, Sparkles } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

export default function AskData() {
  const { activeWorkspaceId, refreshWorkspaces } = useAppContext();
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [clarification, setClarification] = useState(null);
  const verificationStatus = result?.record?.verification?.status;
  const verificationBadge =
    verificationStatus === 'VERIFIED'
      ? { className: 'badge badge-ok', label: 'Verified match' }
      : verificationStatus === 'FAILED'
        ? { className: 'badge badge-bad', label: 'Verification failed' }
        : { className: 'badge badge-warn', label: 'Not independently verified' };

  const handleAsk = async () => {
    if (!question.trim() || !activeWorkspaceId) return;
    setLoading(true);
    setError('');
    setResult(null);
    setClarification(null);
    try {
      const proposal = await fetchApi(`/query/${activeWorkspaceId}/generate`, {
        method: 'POST',
        body: JSON.stringify({ question }),
      });
      if (proposal.status === 'clarification_required') {
        setClarification(proposal);
        return;
      }

      // Auto-execute for now as requested by HLD Phase 1 pilot flow logic
      const execResult = await fetchApi(`/query/${activeWorkspaceId}/execute`, {
        method: 'POST',
        body: JSON.stringify({ proposal_id: proposal.id }),
      });

      setResult(execResult);
    } catch (err) {
      const message = err.message || 'Error executing query';
      if (message.toLowerCase().includes('workspace not found')) {
        await refreshWorkspaces();
        setError(
          'The previous workspace was no longer active. Your saved workspaces were refreshed; please try again.',
        );
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          marginBottom: '1rem',
          color: 'var(--bg-primary)',
        }}
      >
        <Sparkles size={20} />
        <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>
          Deterministic Natural-SQL Engine
        </span>
      </div>

      {clarification && (
        <div
          className="card animate-fade-slide"
          style={{
            marginBottom: '2rem',
            borderColor: 'var(--accent-amber)',
            background: 'var(--accent-amber-bg)',
          }}
        >
          <h3 style={{ marginBottom: '0.5rem' }}>I need one detail before querying</h3>
          <p style={{ color: 'var(--text-primary)', marginBottom: '1rem' }}>
            {clarification.message}
          </p>
          {clarification.interpreted_request && (
            <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Interpreted request: {clarification.interpreted_request}
            </p>
          )}
          {clarification.assumptions?.length > 0 && (
            <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Assumptions considered: {clarification.assumptions.join('; ')}
            </p>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {clarification.suggestions?.map((suggestion) => (
              <button
                key={suggestion}
                className="btn btn-secondary"
                onClick={() => setQuestion((current) => `${current}. ${suggestion}`)}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div
          className="card"
          role="alert"
          style={{
            marginBottom: '2rem',
            color: '#b42318',
            borderColor: '#fda29b',
            backgroundColor: '#fff1f0',
          }}
        >
          {error}
        </div>
      )}
      <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>What would you like to know?</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
        Ask in plain English. Pucho will safely generate, run, and verify a read-only query in an
        isolated sandbox.
      </p>

      <div
        className="card"
        style={{
          padding: '0',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          marginBottom: '2rem',
        }}
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="What were our top 5 products by revenue last month?"
          style={{
            width: '100%',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            padding: '1.5rem',
            fontSize: '1.125rem',
            resize: 'none',
            outline: 'none',
            minHeight: '120px',
          }}
        />
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '1rem 1.5rem',
            borderTop: '1px solid var(--border-color)',
            backgroundColor: 'var(--bg-surface-raised)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Press Return ↵ to ask
            </span>
            <span style={{ color: 'var(--border-color)' }}>•</span>
            <span
              style={{
                fontSize: '0.875rem',
                color: 'var(--accent-green)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
              }}
            >
              <span className="badge badge-ok">Read-only enforced</span>
            </span>
          </div>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button className="btn btn-secondary" onClick={() => setQuestion('')}>
              Clear
            </button>
            <button
              className="btn btn-primary"
              onClick={handleAsk}
              disabled={loading || !question.trim()}
              style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}
            >
              <Play size={16} fill="currentColor" />
              {loading ? 'Generating...' : 'Generate answer'}
            </button>
          </div>
        </div>
      </div>

      {result && (
        <div className="animate-fade-slide">
          {(result.record.interpreted_request || result.record.assumptions?.length > 0) && (
            <div className="card" style={{ marginBottom: '1rem' }}>
              <h3 style={{ marginBottom: '0.5rem' }}>How Pucho interpreted the request</h3>
              <p>{result.record.interpreted_request || result.record.question}</p>
              {result.record.assumptions?.length > 0 && (
                <p style={{ color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                  Assumptions: {result.record.assumptions.join('; ')}
                </p>
              )}
            </div>
          )}
          <div
            className="card"
            style={{
              marginBottom: '2rem',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
            }}
          >
            <div>
              <h3
                style={{
                  fontSize: '1.25rem',
                  marginBottom: '0.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <Sparkles size={20} color="var(--bg-primary)" /> Executive Summary
              </h3>
              <p style={{ color: 'var(--text-muted)' }}>Synthesized from validated SQL execution</p>
              <div style={{ marginTop: '1rem', fontSize: '1.125rem', lineHeight: 1.6 }}>
                {result.presentation?.headline} - {result.presentation?.detail}
              </div>
            </div>
            <span className={verificationBadge.className}>{verificationBadge.label}</span>
          </div>

          <div className="card" style={{ overflowX: 'auto' }}>
            <h3 style={{ marginBottom: '1rem' }}>Detailed Results</h3>
            {result.record.rows && result.record.rows.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)' }}>
                    {result.record.columns.map((c) => (
                      <th
                        key={c}
                        style={{
                          padding: '0.75rem 1rem',
                          color: 'var(--text-muted)',
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          letterSpacing: '0.05em',
                        }}
                      >
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.record.rows.map((row, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-color)' }}>
                      {result.record.columns.map((c) => (
                        <td key={c} style={{ padding: '0.875rem 1rem', fontSize: '0.875rem' }}>
                          {row[c]?.toString() || '-'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-muted">No rows returned.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
