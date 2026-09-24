import { useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ArrowLeft, ChevronDown, Code2, LoaderCircle, MessageSquarePlus, Mic, Play, Sparkles, Square } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { fetchApi } from '../api/client';

const DEFAULT_RESULT_LABELS = {
  executive_summary: 'Executive summary',
  validated_answer: 'Validated against the returned data',
  detailed_results: 'Detailed results',
  rows_returned: 'rows returned',
  no_rows: 'No rows returned.',
  view_sql: 'View generated SQL',
  read_only_query: 'Read-only query',
  interpretation: 'How Pucho interpreted this request',
  view_details: 'View details',
  verified_match: 'Verified match',
  needs_review: 'Needs review',
};

export default function AskData() {
  const location = useLocation();
  const { activeWorkspaceId, refreshWorkspaces } = useAppContext();
  const [question, setQuestion] = useState('');
  const [continuation, setContinuation] = useState(() => location.state?.continuation || null);
  const [questionLanguage, setQuestionLanguage] = useState(() => location.state?.continuation?.languageCode || null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [clarification, setClarification] = useState(null);
  const [voiceState, setVoiceState] = useState('idle');
  const [voiceError, setVoiceError] = useState('');
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const presentation = result?.presentation || {};
  const resultLabels = { ...DEFAULT_RESULT_LABELS, ...presentation.labels };
  const verificationStatus = result?.record?.verification?.status;
  const verificationBadge = verificationStatus === 'VERIFIED'
    ? { className: 'badge badge-ok', label: resultLabels.verified_match }
    : verificationStatus === 'FAILED'
      ? { className: 'badge badge-bad', label: 'Verification failed' }
      : { className: 'badge badge-warn', label: resultLabels.needs_review };

  const handleAsk = async () => {
    if (!question.trim() || !activeWorkspaceId) return;
    setLoading(true);
    setError('');
    setResult(null);
    setClarification(null);
    try {
      const questionForQuery = continuation
        ? `Previous question: ${continuation.interpretedRequest || continuation.question}\n\nFollow-up question: ${question.trim()}`
        : question.trim();
      const proposal = await fetchApi(`/query/${activeWorkspaceId}/generate`, {
        method: 'POST',
        body: JSON.stringify({ question: questionForQuery, language_code: questionLanguage })
      });
      if (proposal.status === 'clarification_required') {
        setClarification(proposal);
        return;
      }
      
      // Auto-execute for now as requested by HLD Phase 1 pilot flow logic
      const execResult = await fetchApi(`/query/${activeWorkspaceId}/execute`, {
        method: 'POST',
        body: JSON.stringify({ proposal_id: proposal.id })
      });
      
      setResult(execResult);
    } catch (err) {
      const message = err.message || 'Error executing query';
      if (message.toLowerCase().includes('workspace not found')) {
        await refreshWorkspaces();
        setError('The previous workspace was no longer active. Your saved workspaces were refreshed; please try again.');
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  };

  const releaseMicrophone = () => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  };

  const transcribeRecording = async (blob) => {
    if (!blob.size) {
      setVoiceError('No audio was captured. Please try recording again.');
      setVoiceState('idle');
      return;
    }
    try {
      const audio = new FormData();
      audio.append('file', blob, 'puchoo-question.webm');
      const response = await fetchApi('/sarvam/transcribe', { method: 'POST', body: audio });
      const transcript = response?.transcript?.trim();
      if (!transcript) throw new Error('No speech was detected. Please try again.');
      setQuestion(current => current.trim() ? `${current.trim()} ${transcript}` : transcript);
      setQuestionLanguage(response?.language_code || null);
    } catch (err) {
      setVoiceError(err.message || 'We could not transcribe that recording. Please try again.');
    } finally {
      setVoiceState('idle');
      recorderRef.current = null;
    }
  };

  const startVoiceInput = async () => {
    setVoiceError('');
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError('Voice input is not supported by this browser. Try the latest Chrome, Edge, or Safari.');
      return;
    }
    setVoiceState('requesting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioChunksRef.current = [];
      const preferredMimeType = 'audio/webm;codecs=opus';
      const recorder = MediaRecorder.isTypeSupported(preferredMimeType)
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = event => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        releaseMicrophone();
        setVoiceError('The microphone recording stopped unexpectedly. Please try again.');
        setVoiceState('idle');
      };
      recorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        releaseMicrophone();
        transcribeRecording(blob);
      };
      recorder.start();
      setVoiceState('recording');
    } catch (err) {
      releaseMicrophone();
      setVoiceState('idle');
      setVoiceError(err.name === 'NotAllowedError'
        ? 'Microphone access was blocked. Allow microphone access in your browser, then try again.'
        : 'We could not start the microphone. Please try again.');
    }
  };

  const stopVoiceInput = () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;
    setVoiceState('transcribing');
    recorder.stop();
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--bg-primary)' }}>
        <Sparkles size={20} />
        <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>Deterministic Natural-SQL Engine</span>
      </div>

      {clarification && (
        <div className="card animate-fade-slide" style={{ marginBottom: '2rem', borderColor: 'var(--accent-amber)', background: 'var(--accent-amber-bg)' }}>
          <h3 style={{ marginBottom: '0.5rem' }}>I need one detail before querying</h3>
          <p style={{ color: 'var(--text-primary)', marginBottom: '1rem' }}>{clarification.message}</p>
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
            {clarification.suggestions?.map(suggestion => (
              <button key={suggestion} className="btn btn-secondary" onClick={() => setQuestion(current => `${current}. ${suggestion}`)}>{suggestion}</button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="card" role="alert" style={{ marginBottom: '2rem', color: '#b42318', borderColor: '#fda29b', backgroundColor: '#fff1f0' }}>
          {error}
        </div>
      )}
      {continuation && (
        <div className="continuation-banner animate-fade-slide">
          <div className="continuation-icon"><MessageSquarePlus size={19} /></div>
          <div>
            <span>Continuing a previous question</span>
            <p>{continuation.question}</p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={() => { setContinuation(null); setQuestion(''); setQuestionLanguage(null); }}><ArrowLeft size={16} /> Start fresh</button>
        </div>
      )}
      <h1 style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>What would you like to know?</h1>
      <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>
        {continuation ? 'Ask a follow-up and Pucho will use the selected question as context.' : 'Type or speak your question. Pucho will safely generate, run, and verify a read-only query in an isolated sandbox.'}
      </p>

      <div className="card" style={{ padding: '0', display: 'flex', flexDirection: 'column', overflow: 'hidden', marginBottom: '2rem' }}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={continuation ? 'For example: Break that down by month.' : 'What were our top 5 products by revenue last month?'}
          style={{
            width: '100%',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-primary)',
            padding: '1.5rem',
            fontSize: '1.125rem',
            resize: 'none',
            outline: 'none',
            minHeight: '120px'
          }}
        />
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          padding: '1rem 1.5rem',
          borderTop: '1px solid var(--border-color)',
          backgroundColor: 'var(--bg-surface-raised)'
        }}>
          <div className="ask-composer-status">
            <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Press Return ↵ to ask</span>
            <span style={{ color: 'var(--border-color)' }}>•</span>
            <span style={{ fontSize: '0.875rem', color: 'var(--accent-green)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
              <span className="badge badge-ok">Read-only enforced</span>
            </span>
            <span style={{ color: 'var(--border-color)' }}>•</span>
            <button
              type="button"
              className={`voice-button ${voiceState === 'recording' ? 'is-recording' : ''}`}
              onClick={voiceState === 'recording' ? stopVoiceInput : startVoiceInput}
              disabled={voiceState === 'requesting' || voiceState === 'transcribing'}
              aria-pressed={voiceState === 'recording'}
              aria-label={voiceState === 'recording' ? 'Stop recording' : 'Speak your question'}
              title={voiceState === 'recording' ? 'Stop recording' : 'Speak your question'}
            >
              {voiceState === 'requesting' || voiceState === 'transcribing'
                ? <LoaderCircle size={16} className="voice-spinner" />
                : voiceState === 'recording' ? <Square size={13} fill="currentColor" /> : <Mic size={16} />}
              <span>{voiceState === 'recording' ? 'Stop recording' : voiceState === 'transcribing' ? 'Transcribing…' : voiceState === 'requesting' ? 'Starting…' : 'Speak'}</span>
            </button>
          </div>
          <div style={{ display: 'flex', gap: '1rem' }}>
            <button className="btn btn-secondary" onClick={() => { setQuestion(''); setQuestionLanguage(null); }}>Clear</button>
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
      {questionLanguage && <p className="voice-language" role="status">Voice language detected: {questionLanguage}. Your transcript and executive answer stay in this language.</p>}
      {voiceError && <p className="voice-error" role="status">{voiceError}</p>}

      {result && (
        <div className="result-stack animate-fade-slide">
          {(result.record.interpreted_request || result.record.assumptions?.length > 0) && (
            <details className="query-details interpretation-details">
              <summary>
                <span className="query-details-title"><Sparkles size={18} /> {resultLabels.interpretation}</span>
                <span className="query-details-hint">{resultLabels.view_details} <ChevronDown size={16} /></span>
              </summary>
              <div className="query-details-body">
                <p className="interpretation-copy">{result.record.interpreted_request || result.record.question}</p>
              {result.record.assumptions?.length > 0 && (
                  <div className="interpretation-assumptions"><strong>Assumptions</strong><p>{result.record.assumptions.join('; ')}</p></div>
              )}
              </div>
            </details>
          )}
          <section className="result-summary-card">
            <div className="result-summary-heading">
              <div className="result-summary-icon"><Sparkles size={19} /></div>
              <div>
                <span className="result-overline">{resultLabels.executive_summary}</span>
                <p>{resultLabels.validated_answer}</p>
              </div>
            </div>
            <span className={verificationBadge.className}>{verificationBadge.label}</span>
            <div className="result-summary-copy">
              <strong>{presentation.headline}</strong>
              {presentation.detail && <p>{presentation.detail}</p>}
            </div>
            {presentation.highlights?.length > 0 && (
              <div className="result-highlights">
                {presentation.highlights.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
              </div>
            )}
          </section>

          {result.record.sql && (
            <details className="query-details">
              <summary>
                <span className="query-details-title"><Code2 size={18} /> {resultLabels.view_sql}</span>
                <span className="query-details-hint">{resultLabels.read_only_query} <ChevronDown size={16} /></span>
              </summary>
              <div className="query-details-body">
                <p>This is the read-only SQL Pucho ran to produce the answer.</p>
                <pre>{result.record.sql}</pre>
              </div>
            </details>
          )}

          <section className="result-table-card">
            <div className="result-table-heading">
              <div><span className="result-overline">{resultLabels.detailed_results}</span><p>{result.record.row_count ?? 0} {resultLabels.rows_returned}</p></div>
              <span className="result-table-status"><span></span>{resultLabels.read_only_query}</span>
            </div>
            <div className="result-table-scroll">
            {result.record.rows && result.record.rows.length > 0 ? (
              <table className="result-table">
                <thead>
                  <tr>
                    {result.record.columns.map(c => (
                      <th key={c}>{presentation.column_labels?.[c] || c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.record.rows.map((row, index) => (
                    <tr key={index}>
                      {result.record.columns.map(c => (
                        <td key={c}>{(presentation.display_rows?.[index] || row)[c]?.toString() || '—'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="result-empty">{resultLabels.no_rows}</p>
            )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
