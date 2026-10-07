import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowLeft, ArrowUpRight, ChevronDown, Code2, Database, LoaderCircle, MessageSquarePlus, Mic, ShieldCheck, Sparkles, Square, X } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { useAuth } from '../context/AuthContext';
import { fetchApi } from '../api/client';

const DEFAULT_RESULT_LABELS = {
  executive_summary: 'Executive summary',
  validated_answer: 'Validated against the returned data',
  detailed_results: 'Detailed results',
  rows_returned: 'rows returned',
  no_rows: 'No rows returned.',
  view_sql: 'View generated SQL',
  read_only_query: 'Read-only query',
  interpretation: 'How Puchoo.si interpreted this request',
  view_details: 'View details',
  verified_match: 'Verified match',
  needs_review: 'Needs review',
};

function QueryUniverse() {
  const canvasRef = useRef(null);
  const pointerRef = useRef({ x: 0, y: 0, active: false });

  useEffect(() => {
    const canvas = canvasRef.current;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!canvas || reducedMotion.matches) return undefined;
    const context = canvas.getContext('2d', { alpha: true });
    if (!context) return undefined;
    let frame = 0;
    let width = 0;
    let height = 0;
    let particles = [];
    const stage = canvas.parentElement;
    const updatePointer = (event) => {
      const bounds = canvas.getBoundingClientRect();
      pointerRef.current = {
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
        active: true,
      };
    };
    const clearPointer = () => { pointerRef.current.active = false; };
    const setup = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      width = Math.max(1, bounds.width);
      height = Math.max(1, bounds.height);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const dustCount = Math.min(300, Math.max(150, Math.round(width / 6)));
      const streamCount = Math.min(430, Math.max(240, Math.round(width / 4.2)));
      const dust = Array.from({ length: dustCount }, () => ({
        kind: 'dust',
        x: Math.random() * width,
        y: Math.random() * height,
        drift: (Math.random() - .5) * .00065,
        size: Math.random() > .91 ? 1.7 : .35 + Math.random() * .8,
        alpha: .21 + Math.random() * .72,
        phase: Math.random() * Math.PI * 2,
      }));
      const streams = Array.from({ length: streamCount }, (_, index) => ({
        kind: 'stream',
        angle: Math.random() * Math.PI * 2,
        radius: .19 + Math.pow(Math.random(), .55) * .65,
        speed: (.00009 + Math.random() * .00026) * (index % 3 === 0 ? -1 : 1),
        lane: .16 + Math.random() * .29,
        size: Math.random() > .92 ? 1.55 : .35 + Math.random() * .8,
        alpha: .15 + Math.random() * .62,
        phase: Math.random() * Math.PI * 2,
        tail: .014 + Math.random() * .035,
      }));
      const clusters = Array.from({ length: 17 }, () => ({
        kind: 'cluster',
        x: Math.random() * width,
        y: Math.random() * height,
        radius: 18 + Math.random() * 50,
        alpha: .015 + Math.random() * .035,
        phase: Math.random() * Math.PI * 2,
      }));
      particles = [...clusters, ...dust, ...streams];
    };
    const draw = (time) => {
      context.clearRect(0, 0, width, height);
      const centerX = width / 2;
      const centerY = height * .58;
      context.globalCompositeOperation = 'lighter';
      const pointer = pointerRef.current;

      if (pointer.active) {
        const pointerGlow = context.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 150);
        pointerGlow.addColorStop(0, 'rgba(119, 200, 255, .075)');
        pointerGlow.addColorStop(.42, 'rgba(78, 151, 219, .028)');
        pointerGlow.addColorStop(1, 'rgba(31, 92, 147, 0)');
        context.fillStyle = pointerGlow;
        context.fillRect(pointer.x - 150, pointer.y - 150, 300, 300);

        for (let ring = 0; ring < 3; ring += 1) {
          const pulse = (time * .00017 + ring / 3) % 1;
          context.beginPath();
          context.arc(pointer.x, pointer.y, 18 + pulse * 76, 0, Math.PI * 2);
          context.strokeStyle = `rgba(155, 220, 255, ${(1 - pulse) * .11})`;
          context.lineWidth = .65;
          context.stroke();
        }
      }
      // Slow, transparent orbital paths give the field depth without becoming
      // a bright static panel behind the composer.
      context.save();
      context.translate(centerX, centerY);
      for (let index = 0; index < 4; index += 1) {
        const phase = time * (.000018 + index * .000004) * (index % 2 ? -1 : 1);
        const horizontal = width * (.24 + index * .105);
        const vertical = Math.max(56, height * (.10 + index * .038));
        context.rotate(phase + index * .34);
        context.beginPath();
        context.ellipse(0, 0, horizontal, vertical, 0, 0, Math.PI * 2);
        context.strokeStyle = `rgba(139, 197, 239, ${.022 + index * .009})`;
        context.lineWidth = .55;
        context.stroke();
        context.rotate(-(phase + index * .34));
      }
      context.restore();

      // Three expanding, very low-opacity pulses provide movement between the
      // star streams without introducing a white glow in the idle UI.
      for (let index = 0; index < 3; index += 1) {
        const progress = (time * .000035 + index / 3) % 1;
        context.beginPath();
        context.ellipse(
          centerX,
          centerY,
          width * (.13 + progress * .54),
          Math.max(44, height * (.055 + progress * .19)),
          -.07,
          0,
          Math.PI * 2,
        );
        context.strokeStyle = `rgba(112, 185, 238, ${(1 - progress) * .035})`;
        context.lineWidth = .65;
        context.stroke();
      }
      particles.forEach((particle) => {
        if (particle.kind === 'cluster') {
          const breathing = .72 + Math.sin(time * .0007 + particle.phase) * .28;
          const gradient = context.createRadialGradient(particle.x, particle.y, 0, particle.x, particle.y, particle.radius);
          gradient.addColorStop(0, `rgba(131, 199, 255, ${particle.alpha * breathing})`);
          gradient.addColorStop(1, 'rgba(56, 126, 196, 0)');
          context.fillStyle = gradient;
          context.beginPath();
          context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
          context.fill();
          return;
        }
        if (particle.kind === 'dust') {
          const x = (particle.x + time * particle.drift) % width;
          const y = particle.y + Math.sin(time * .00035 + particle.phase) * 3;
          const distance = pointer.active ? Math.hypot(x - pointer.x, y - pointer.y) : Infinity;
          const cursorLift = distance < 170 ? (1 - distance / 170) * .7 : 0;
          const twinkle = .62 + Math.sin(time * .0022 + particle.phase) * .38 + cursorLift;
          context.fillStyle = `rgba(224, 240, 255, ${Math.min(1, particle.alpha * twinkle)})`;
          context.beginPath();
          context.arc(x < 0 ? x + width : x, y, particle.size, 0, Math.PI * 2);
          context.fill();
          if (particle.size > 1.35) {
            context.strokeStyle = `rgba(205, 231, 255, ${particle.alpha * .55})`;
            context.lineWidth = .55;
            context.beginPath();
            context.moveTo(x - 5, y);
            context.lineTo(x + 5, y);
            context.stroke();
          }
          return;
        }
        const angle = particle.angle + time * particle.speed;
        const ellipticalRadius = particle.radius * width;
        const verticalRadius = Math.max(58, height * particle.radius * particle.lane);
        const x = centerX + Math.cos(angle) * ellipticalRadius;
        const y = centerY + Math.sin(angle) * verticalRadius;
        const trailingAngle = angle - Math.sign(particle.speed) * particle.tail;
        const trailX = centerX + Math.cos(trailingAngle) * ellipticalRadius;
        const trailY = centerY + Math.sin(trailingAngle) * verticalRadius;
        const distance = pointer.active ? Math.hypot(x - pointer.x, y - pointer.y) : Infinity;
        const cursorLift = distance < 190 ? (1 - distance / 190) * .55 : 0;
        const twinkle = .62 + Math.sin(time * .0024 + particle.phase) * .38 + cursorLift;
        if (particle.size > .72) {
          context.beginPath();
          context.strokeStyle = `rgba(173, 218, 251, ${particle.alpha * .46 * twinkle})`;
          context.lineWidth = particle.size > 1.3 ? .9 : .42;
          context.moveTo(trailX, trailY);
          context.lineTo(x, y);
          context.stroke();
        }
        context.beginPath();
        context.fillStyle = `rgba(230, 244, 255, ${particle.alpha * twinkle})`;
        context.arc(x, y, particle.size, 0, Math.PI * 2);
        context.fill();
        if (particle.size > 1.35) {
          context.strokeStyle = `rgba(185, 225, 255, ${particle.alpha * .62})`;
          context.beginPath();
          context.moveTo(x - 7, y);
          context.lineTo(x + 7, y);
          context.stroke();
        }
      });
      context.globalCompositeOperation = 'source-over';
      frame = window.requestAnimationFrame(draw);
    };
    setup();
    frame = window.requestAnimationFrame(draw);
    window.addEventListener('resize', setup);
    stage?.addEventListener('pointermove', updatePointer, { passive: true });
    stage?.addEventListener('pointerleave', clearPointer);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', setup);
      stage?.removeEventListener('pointermove', updatePointer);
      stage?.removeEventListener('pointerleave', clearPointer);
    };
  }, []);

  return <canvas ref={canvasRef} className="ask-universe" aria-hidden="true" />;
}

function consumeWelcome(routeWelcome) {
  try {
    const saved = window.sessionStorage.getItem('puchoo:welcome');
    window.sessionStorage.removeItem('puchoo:welcome');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (typeof parsed?.title === 'string' && typeof parsed?.message === 'string') return parsed;
    }
  } catch {
    // A welcome banner is optional if browser storage is unavailable.
  }
  return routeWelcome || null;
}

export default function AskData() {
  const location = useLocation();
  const { activeWorkspaceId, activeWorkspace, refreshWorkspaces } = useAppContext();
  const { user } = useAuth();
  const [question, setQuestion] = useState('');
  const [continuation, setContinuation] = useState(() => location.state?.continuation || null);
  const [questionLanguage, setQuestionLanguage] = useState(() => location.state?.continuation?.languageCode || null);
  const [welcome, setWelcome] = useState(() => consumeWelcome(location.state?.welcome));
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [clarification, setClarification] = useState(null);
  const [voiceState, setVoiceState] = useState('idle');
  const [voiceError, setVoiceError] = useState('');
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const resultRef = useRef(null);
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

  const onComposerKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleAsk();
    }
  };

  useEffect(() => {
    if (!result) return undefined;
    const timer = window.setTimeout(() => {
      resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 90);
    return () => window.clearTimeout(timer);
  }, [result]);

  useEffect(() => {
    if (!welcome) return undefined;
    const timer = window.setTimeout(() => setWelcome(null), 7000);
    return () => window.clearTimeout(timer);
  }, [welcome]);

  const welcomeNotice = welcome ? (
    <section className="ask-welcome animate-fade-slide" role="status">
      <div className="ask-welcome-icon"><Sparkles size={16} /></div>
      <div><strong>{welcome.title}</strong><p>{welcome.message}</p></div>
      <button type="button" onClick={() => setWelcome(null)} aria-label="Dismiss welcome message"><X size={16} /></button>
    </section>
  ) : null;

  if (user?.workspace_role === 'viewer') {
    return <div className="ask-page">{welcomeNotice}<section className="ask-viewer-state"><div className="ask-viewer-icon"><ShieldCheck size={22} /></div><span>Viewer access</span><h1>Explore approved answers.</h1><p>Your role can review shared query history, while prompts, data sources, and workspace settings remain protected.</p><Link className="ask-primary-action" to="/history">Open history <ArrowUpRight size={17} /></Link></section></div>;
  }

  return (
    <div className="ask-page">
      {welcomeNotice}
      <section className="ask-stage">
        <QueryUniverse />
        <div className="ask-stage-content">
          <h1>A clearer way<br />to see <em>data.</em></h1>
          <p>{continuation ? 'Continue your analysis with secure context from the selected question.' : activeWorkspace ? 'Ask, verify, and act on the numbers that matter.' : 'Connect a data source to ask secure, verified questions in your own workspace.'}</p>

          {!activeWorkspace ? (
            <Link className="ask-connect-action" to="/connect"><Database size={17} /> Connect a data source <ArrowUpRight size={16} /></Link>
          ) : (
            <div className={`ask-prompt-shell${loading ? ' is-loading' : ''}`} aria-busy={loading}>
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={onComposerKeyDown}
                placeholder={continuation ? 'For example: Break that down by month.' : 'Ask a question about your data…'}
                aria-label="Ask a question about your data"
                aria-describedby={loading ? 'query-processing-status' : undefined}
                rows="3"
              />
              <div className="ask-prompt-controls">
                <div className="ask-prompt-meta">
                  <span><ShieldCheck size={14} /> Read-only</span>
                  <span className="ask-prompt-divider" />
                  <button
                    type="button"
                    className={`voice-button ${voiceState === 'recording' ? 'is-recording' : ''}`}
                    onClick={voiceState === 'recording' ? stopVoiceInput : startVoiceInput}
                    disabled={voiceState === 'requesting' || voiceState === 'transcribing'}
                    aria-pressed={voiceState === 'recording'}
                    aria-label={voiceState === 'recording' ? 'Stop recording' : 'Speak your question'}
                  >
                    {voiceState === 'requesting' || voiceState === 'transcribing' ? <LoaderCircle size={15} className="voice-spinner" /> : voiceState === 'recording' ? <Square size={12} fill="currentColor" /> : <Mic size={15} />}
                    <span>{voiceState === 'recording' ? 'Stop' : voiceState === 'transcribing' ? 'Transcribing…' : voiceState === 'requesting' ? 'Starting…' : 'Voice'}</span>
                  </button>
                </div>
                <div className="ask-prompt-actions">
                  {loading ? <span id="query-processing-status" className="ask-query-mode ask-query-processing"><i /> Generating answer</span> : <span className="ask-query-mode">Verified query <ChevronDown size={14} /></span>}
                  {question && <button className="ask-clear-button" type="button" onClick={() => { setQuestion(''); setQuestionLanguage(null); }}>Clear</button>}
                  <button className="ask-submit-button" type="button" onClick={handleAsk} disabled={loading || !question.trim()} aria-label="Run secure query">
                    {loading ? <LoaderCircle size={19} className="voice-spinner" /> : <ArrowUpRight size={20} />}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="ask-stage-footer"><span>Puchoo.si intelligence · {activeWorkspace?.name || 'Private workspace'}</span></div>
        </div>
      </section>

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
      {questionLanguage && <p className="voice-language" role="status">Voice language detected: {questionLanguage}. Your transcript and executive answer stay in this language.</p>}
      {voiceError && <p className="voice-error" role="status">{voiceError}</p>}

      {result && (
        <section ref={resultRef} className="ask-results" aria-label="Query results" tabIndex="-1">
        <div className="ask-results-heading"><span>Verified output</span><p>Generated from your active workspace</p></div>
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
                <p>This is the read-only SQL Puchoo.si ran to produce the answer.</p>
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
        </section>
      )}
    </div>
  );
}
