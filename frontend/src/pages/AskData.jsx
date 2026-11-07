import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronDown,
  Code2,
  Database,
  Download,
  LoaderCircle,
  MessageSquarePlus,
  Mic,
  Pause,
  Play,
  ShieldCheck,
  Sparkles,
  Square,
  Volume2,
  X,
} from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { useAuth } from '../context/AuthContext';
import {
  useChatState,
  chatScope,
  scopeKey,
  consumeContinuation,
  startContinuation,
  continuationMatches,
  historyToken,
  tokenCurrent,
} from '../hooks/useChatState';
import { fetchApi, fetchApiBlob } from '../api/client';
import { buildCsv, renderReportPdf } from '../utils/reportExport';
import {
  saveBlob,
  reportFilename,
  reportTable,
  createPdfReportDocument,
} from '../utils/reportDocument';
import { disposeVoiceCapture, playAnswerAudio, requestMicrophone } from '../utils/voice';
import '../styles/chatActions.css';

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

// Gnani accepts OGG and M4A directly. Chromium commonly records WebM, which
// is not an accepted STT upload format, so that recording is converted to WAV
// before it leaves the browser.
const GNANI_RECORDING_MIME_TYPES = ['audio/ogg;codecs=opus', 'audio/mp4'];
const VOICE_LANGUAGES = [
  { code: 'en-IN', label: 'English' },
  { code: 'hi-IN', label: 'हिन्दी' },
  { code: 'bn-IN', label: 'বাংলা' },
  { code: 'gu-IN', label: 'ગુજરાતી' },
  { code: 'kn-IN', label: 'ಕನ್ನಡ' },
  { code: 'ml-IN', label: 'മലയാളം' },
  { code: 'mr-IN', label: 'मराठी' },
  { code: 'pa-IN', label: 'ਪੰਜਾਬੀ' },
  { code: 'ta-IN', label: 'தமிழ்' },
  { code: 'te-IN', label: 'తెలుగు' },
];

function encodeWav(audioBuffer) {
  const frameCount = audioBuffer.length;
  const channelCount = Math.max(1, audioBuffer.numberOfChannels);
  const output = new ArrayBuffer(44 + frameCount * 2);
  const view = new DataView(output);
  const writeText = (offset, value) => {
    [...value].forEach((character, index) =>
      view.setUint8(offset + index, character.charCodeAt(0)),
    );
  };
  const writeInt16 = (offset, sample) => view.setInt16(offset, sample, true);

  writeText(0, 'RIFF');
  view.setUint32(4, 36 + frameCount * 2, true);
  writeText(8, 'WAVE');
  writeText(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, audioBuffer.sampleRate, true);
  view.setUint32(28, audioBuffer.sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, 'data');
  view.setUint32(40, frameCount * 2, true);

  const channels = Array.from({ length: channelCount }, (_, index) =>
    audioBuffer.getChannelData(index),
  );
  for (let frame = 0; frame < frameCount; frame += 1) {
    const mixedSample =
      channels.reduce((total, channel) => total + channel[frame], 0) / channelCount;
    const pcmSample = Math.max(-1, Math.min(1, mixedSample));
    writeInt16(44 + frame * 2, pcmSample < 0 ? pcmSample * 0x8000 : pcmSample * 0x7fff);
  }
  return new Blob([output], { type: 'audio/wav' });
}

async function convertRecordingToWav(blob, signal) {
  const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextConstructor)
    throw new Error('This browser cannot prepare the recording for transcription.');
  const audioContext = new AudioContextConstructor();
  const close = () => {
    if (audioContext.state !== 'closed') void audioContext.close().catch(() => {});
  };
  signal.addEventListener('abort', close, { once: true });
  try {
    const bytes = await blob.arrayBuffer();
    signal.throwIfAborted();
    const decoded = await audioContext.decodeAudioData(bytes);
    signal.throwIfAborted();
    return encodeWav(decoded);
  } finally {
    signal.removeEventListener('abort', close);
    close();
  }
}

export function buildResultSpeechPayload(presentation, record = {}) {
  const parts = [presentation?.headline, presentation?.detail]
    .filter((part) => typeof part === 'string' && part.trim())
    .map((part) => part.trim());
  const table = reportTable({ presentation, record });
  for (const row of table.rows) {
    parts.push(
      row.map((value, index) => `${table.labels[index]}: ${String(value)}`).join('; ') + '.',
    );
  }
  return parts.join('\n\n');
}

export function splitResultSpeech(text) {
  const clips = [];
  let remaining = text;
  while (remaining.length > (clips.length ? 2000 : 300)) {
    const limit = clips.length ? 2000 : 300;
    let end = Math.max(
      remaining.lastIndexOf('\n', limit - 1),
      remaining.lastIndexOf(' ', limit - 1),
    );
    end = end > limit / 2 ? end + 1 : limit;
    if (/[\uD800-\uDBFF]/.test(remaining[end - 1])) end -= 1;
    clips.push(remaining.slice(0, end));
    remaining = remaining.slice(end);
  }
  if (remaining.trim()) clips.push(remaining);
  return clips;
}

export function resolveResultSpeechLanguage(result, questionLanguage) {
  const selectedLanguage =
    result?.presentation?.language_code ||
    result?.record?.language_code ||
    questionLanguage ||
    'en-IN';
  return VOICE_LANGUAGES.some((language) => language.code === selectedLanguage)
    ? selectedLanguage
    : 'en-IN';
}

export function isActiveResultSpeech(audioRef, audio, requestRef, requestId) {
  return audioRef.current === audio && requestRef.current === requestId;
}

export function stopResultSpeech(audioRef, urlRef) {
  const audio = audioRef.current;
  if (audio) {
    audio.onended = null;
    audio.onerror = null;
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    audioRef.current = null;
  }
  if (urlRef.current) {
    URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
  }
}

export function ResultSpeechControls({ speechState, speechError, onPlay, onPauseResume, onStop }) {
  const isPreparing = speechState === 'loading';
  const isPlaying = speechState === 'playing';
  const isPaused = speechState === 'paused';
  const status = isPreparing
    ? 'Preparing audio'
    : isPlaying
      ? 'Playing full report'
      : isPaused
        ? 'Playback paused — tap Resume to continue'
        : speechError || 'Ready to play the answer';

  return (
    <div className="result-speech-controls">
      <div className="result-speech-actions">
        {isPreparing ? (
          <button type="button" disabled aria-label="Preparing audio">
            <LoaderCircle size={15} className="voice-spinner" /> Preparing audio…
          </button>
        ) : isPlaying || isPaused ? (
          <button
            type="button"
            onClick={onPauseResume}
            aria-label={isPlaying ? 'Pause answer' : 'Resume answer'}
          >
            {isPlaying ? (
              <Pause size={15} fill="currentColor" />
            ) : (
              <Play size={15} fill="currentColor" />
            )}
            {isPlaying ? 'Pause' : 'Resume'}
          </button>
        ) : (
          <button type="button" onClick={onPlay} aria-label="Listen to answer">
            <Volume2 size={15} /> Listen to answer
          </button>
        )}
        {(isPreparing || isPlaying || isPaused) && (
          <button
            type="button"
            className="result-speech-stop"
            onClick={onStop}
            aria-label="Stop reading answer"
          >
            <Square size={12} fill="currentColor" /> Stop
          </button>
        )}
      </div>
      <p
        className={`result-speech-status${speechError ? ' is-error' : ''}`}
        role="status"
        aria-live="polite"
      >
        {status}
      </p>
    </div>
  );
}

export function queryUniversePalette(theme) {
  if (theme === 'light') {
    return {
      composite: 'source-over',
      motion: 1.45,
      orbit: '44, 41, 38',
      pulse: '54, 51, 48',
      cluster: '44, 41, 38',
      clusterEdge: '44, 41, 38',
      dust: '22, 19, 16',
      dustSpark: '30, 27, 24',
      stream: '35, 32, 29',
      star: '21, 18, 15',
      starSpark: '25, 22, 19',
    };
  }
  return {
    composite: 'lighter',
    motion: 1,
    orbit: '139, 197, 239',
    pulse: '112, 185, 238',
    cluster: '131, 199, 255',
    clusterEdge: '56, 126, 196',
    dust: '224, 240, 255',
    dustSpark: '205, 231, 255',
    stream: '173, 218, 251',
    star: '230, 244, 255',
    starSpark: '185, 225, 255',
  };
}

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
    const clearPointer = () => {
      pointerRef.current.active = false;
    };
    const setup = () => {
      const bounds = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      width = Math.max(1, bounds.width);
      height = Math.max(1, bounds.height);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const area = width * height;
      const dustCount = Math.min(4200, Math.max(1200, Math.round(area / 340)));
      const stillCount = Math.min(6500, Math.max(1800, Math.round(area / 220)));
      const streamCount = Math.min(3200, Math.max(900, Math.round(area / 450)));
      const motion = queryUniversePalette(document.documentElement.dataset.theme).motion;
      const cornerPoint = () => {
        const corner = Math.floor(Math.random() * 4);
        const x = Math.random() ** 1.6 * width * 0.28;
        const y = Math.random() ** 1.4 * height * 0.32;
        return { x: corner % 2 ? width - x : x, y: corner > 1 ? height - y : y };
      };
      const stillStars = Array.from({ length: stillCount }, () => ({
        kind: 'still',
        ...(Math.random() < 0.45
          ? cornerPoint()
          : { x: Math.random() * width, y: Math.random() * height }),
        size: 0.3 + Math.random() * 0.9,
        alpha: 0.15 + Math.random() * 0.48,
      }));
      const dust = Array.from({ length: dustCount }, () => ({
        kind: 'dust',
        ...(Math.random() < 0.4
          ? cornerPoint()
          : { x: Math.random() * width, y: Math.random() * height }),
        drift: (Math.random() - 0.5) * 0.008 * motion,
        size: Math.random() > 0.91 ? 1.7 : 0.35 + Math.random() * 0.8,
        alpha: 0.21 + Math.random() * 0.72,
        phase: Math.random() * Math.PI * 2,
      }));
      const streams = Array.from({ length: streamCount }, (_, index) => ({
        kind: 'stream',
        angle: Math.random() * Math.PI * 2,
        radius: 0.19 + Math.pow(Math.random(), 0.55) * 0.65,
        speed: (0.00017 + Math.random() * 0.0003) * motion * (index % 3 === 0 ? -1 : 1),
        lane: 0.16 + Math.random() * 0.29,
        size: Math.random() > 0.92 ? 1.55 : 0.35 + Math.random() * 0.8,
        alpha: 0.15 + Math.random() * 0.62,
        phase: Math.random() * Math.PI * 2,
        tail: 0.014 + Math.random() * 0.035,
      }));
      const clusters = Array.from({ length: 17 }, () => ({
        kind: 'cluster',
        x: Math.random() * width,
        y: Math.random() * height,
        radius: 18 + Math.random() * 50,
        alpha: 0.015 + Math.random() * 0.035,
        phase: Math.random() * Math.PI * 2,
      }));
      particles = [...clusters, ...stillStars, ...dust, ...streams];
    };
    const draw = (time) => {
      context.clearRect(0, 0, width, height);
      context.save();
      // Exclude the whole composer, including its voice and submit controls.
      // Read current bounds so growing text and responsive layouts stay clear.
      const composer = stage?.querySelector('.ask-prompt-shell');
      if (composer) {
        const bounds = canvas.getBoundingClientRect();
        const input = composer.getBoundingClientRect();
        const padding = 14;
        context.beginPath();
        context.rect(0, 0, width, height);
        context.rect(
          input.left - bounds.left - padding,
          input.top - bounds.top - padding,
          input.width + padding * 2,
          input.height + padding * 2,
        );
        context.clip('evenodd');
      }
      const centerX = width / 2;
      const centerY = height * 0.58;
      const palette = queryUniversePalette(document.documentElement.dataset.theme);
      context.globalCompositeOperation = palette.composite;
      const pointer = pointerRef.current;

      // Slow, transparent orbital paths give the field depth without becoming
      // a bright static panel behind the composer.
      context.save();
      context.translate(centerX, centerY);
      for (let index = 0; index < 4; index += 1) {
        const phase = time * (0.000018 + index * 0.000004) * (index % 2 ? -1 : 1);
        const horizontal = width * (0.24 + index * 0.105);
        const vertical = Math.max(56, height * (0.1 + index * 0.038));
        context.rotate(phase + index * 0.34);
        context.beginPath();
        context.ellipse(0, 0, horizontal, vertical, 0, 0, Math.PI * 2);
        context.strokeStyle = `rgba(${palette.orbit}, ${0.022 + index * 0.009})`;
        context.lineWidth = 0.55;
        context.stroke();
        context.rotate(-(phase + index * 0.34));
      }
      context.restore();

      // Three expanding, very low-opacity pulses provide movement between the
      // star streams without introducing a white glow in the idle UI.
      for (let index = 0; index < 3; index += 1) {
        const progress = (time * 0.00006 * palette.motion + index / 3) % 1;
        context.beginPath();
        context.ellipse(
          centerX,
          centerY,
          width * (0.13 + progress * 0.54),
          Math.max(44, height * (0.055 + progress * 0.19)),
          -0.07,
          0,
          Math.PI * 2,
        );
        context.strokeStyle = `rgba(${palette.pulse}, ${(1 - progress) * 0.035})`;
        context.lineWidth = 0.65;
        context.stroke();
      }
      particles.forEach((particle) => {
        if (particle.kind === 'cluster') {
          const breathing = 0.72 + Math.sin(time * 0.0007 + particle.phase) * 0.28;
          const gradient = context.createRadialGradient(
            particle.x,
            particle.y,
            0,
            particle.x,
            particle.y,
            particle.radius,
          );
          gradient.addColorStop(0, `rgba(${palette.cluster}, ${particle.alpha * breathing})`);
          gradient.addColorStop(1, `rgba(${palette.clusterEdge}, 0)`);
          context.fillStyle = gradient;
          context.beginPath();
          context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
          context.fill();
          return;
        }
        if (particle.kind === 'still') {
          context.fillStyle = `rgba(${palette.star}, ${particle.alpha})`;
          context.fillRect(particle.x, particle.y, particle.size, particle.size);
          return;
        }
        if (particle.kind === 'dust') {
          const x = (particle.x + time * particle.drift) % width;
          const y = particle.y + Math.sin(time * 0.00035 + particle.phase) * 3;
          const distance = pointer.active ? Math.hypot(x - pointer.x, y - pointer.y) : Infinity;
          const cursorLift = distance < 170 ? (1 - distance / 170) * 0.7 : 0;
          const twinkle = 0.62 + Math.sin(time * 0.0022 + particle.phase) * 0.38 + cursorLift;
          context.fillStyle = `rgba(${palette.dust}, ${Math.min(1, particle.alpha * twinkle)})`;
          context.beginPath();
          context.arc(x < 0 ? x + width : x, y, particle.size, 0, Math.PI * 2);
          context.fill();
          if (particle.size > 1.35) {
            context.strokeStyle = `rgba(${palette.dustSpark}, ${particle.alpha * 0.55})`;
            context.lineWidth = 0.55;
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
        const cursorLift = distance < 190 ? (1 - distance / 190) * 0.55 : 0;
        const twinkle = 0.62 + Math.sin(time * 0.0024 + particle.phase) * 0.38 + cursorLift;
        if (particle.size > 0.72) {
          context.beginPath();
          context.strokeStyle = `rgba(${palette.stream}, ${particle.alpha * 0.46 * twinkle})`;
          context.lineWidth = particle.size > 1.3 ? 0.9 : 0.42;
          context.moveTo(trailX, trailY);
          context.lineTo(x, y);
          context.stroke();
        }
        context.beginPath();
        context.fillStyle = `rgba(${palette.star}, ${particle.alpha * twinkle})`;
        context.arc(x, y, particle.size, 0, Math.PI * 2);
        context.fill();
        if (particle.size > 1.35) {
          context.strokeStyle = `rgba(${palette.starSpark}, ${particle.alpha * 0.62})`;
          context.beginPath();
          context.moveTo(x - 7, y);
          context.lineTo(x + 7, y);
          context.stroke();
        }
      });
      context.restore();
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

// Advisory notice when the question could not be matched to the schema by
// keywords. Rendered as plain text (React escapes it); it never blocks a query.
export function ScopeWarning({ message }) {
  if (!message) return null;
  return (
    <p className="scope-warning" role="status">
      {message}
    </p>
  );
}

export function answerVerification(status, labels = DEFAULT_RESULT_LABELS) {
  if (status === 'VERIFIED')
    return { className: 'badge badge-ok', label: labels.verified_match, verified: true };
  if (status === 'VERIFICATION_MISMATCH' || status === 'FAILED')
    return {
      className: 'badge badge-bad',
      label: 'Verification failed',
      verified: false,
      notice:
        'The independent check found that this result may not answer your question. Review the SQL and refine the question before relying on these rows.',
    };
  return {
    className: 'badge badge-warn',
    label: 'Not independently verified',
    verified: false,
    notice:
      'The query passed read-only safety checks, but answer correctness has not been independently confirmed.',
  };
}

export default function AskData() {
  const location = useLocation();
  const navigate = useNavigate();
  const { activeWorkspaceId, activeWorkspace, refreshWorkspaces } = useAppContext();
  const { user } = useAuth();
  const scope = chatScope(user, activeWorkspaceId);
  const currentScope = useRef(scopeKey(scope));
  const identity = scopeKey(scope);
  useLayoutEffect(() => {
    currentScope.current = identity;
  }, [identity]);
  const [question, setQuestion] = useChatState(scope, activeWorkspaceId, 'question', '');
  const [continuation, setContinuation] = useChatState(
    scope,
    activeWorkspaceId,
    'continuation',
    null,
  );
  const [questionLanguage, setQuestionLanguage] = useChatState(
    scope,
    activeWorkspaceId,
    'questionLanguage',
    null,
  );
  const [welcome, setWelcome] = useState(() => consumeWelcome(location.state?.welcome));
  const [loading, setLoading] = useChatState(scope, activeWorkspaceId, 'loading', false, false);
  const [result, setResult] = useChatState(scope, activeWorkspaceId, 'result', null);
  const [error, setError] = useState('');
  const continuationRouteRef = useRef(null);
  const [clarification, setClarification] = useChatState(
    scope,
    activeWorkspaceId,
    'clarification',
    null,
  );
  useEffect(() => {
    const next = location.state?.continuation;
    if (!next || !scope || continuationRouteRef.current === location.key) return;
    continuationRouteRef.current = location.key;
    const accepted = consumeContinuation(scope, next);
    const { continuation: ignored, ...rest } = location.state;
    void ignored;
    navigate(location.pathname, { replace: true, state: rest });
    if (!accepted) return;
    startContinuation(scope, accepted);
  }, [
    location,
    navigate,
    scope,
    setContinuation,
    setQuestion,
    setQuestionLanguage,
    setResult,
    setClarification,
  ]);

  const [voice, setVoice] = useState({ identity, stage: 'idle', error: '' });
  const voiceState = voice.identity === identity ? voice.stage : 'idle';
  const voiceError = voice.identity === identity ? voice.error : '';
  const [exportingPdf, setExportingPdf] = useState(false);
  const [speechState, setSpeechState] = useState('idle');
  const [speechError, setSpeechError] = useState('');
  const [activeHighlight, setActiveHighlight] = useState(-1);
  const queryInFlightRef = useRef(false);
  const composingRef = useRef(false);
  useLayoutEffect(() => {
    composingRef.current = false;
  }, [identity]);
  const voiceOperationRef = useRef(null);
  useLayoutEffect(
    () => () => {
      const operation = voiceOperationRef.current;
      voiceOperationRef.current = null;
      disposeVoiceCapture(operation);
    },
    [identity],
  );
  const resultRef = useRef(null);
  const speechAudioRef = useRef(null);
  const speechUrlRef = useRef(null);
  const speechRequestRef = useRef(0);
  const presentation = result?.presentation || {};
  const resultLabels = { ...DEFAULT_RESULT_LABELS, ...presentation.labels };
  const verificationStatus = result?.record?.verification?.status;
  const verificationBadge = answerVerification(verificationStatus, resultLabels);

  const reportError = async (err, fallback) => {
    const message = err.message || fallback;
    if (message.toLowerCase().includes('workspace not found')) {
      await refreshWorkspaces();
      setError(
        'The previous workspace was no longer active. Your saved workspaces were refreshed; please try again.',
      );
    } else {
      setError(message);
    }
  };

  const requestCurrent = (token) =>
    currentScope.current === scopeKey(token.scope) && tokenCurrent(token);

  const executeProposal = async (proposal, token) => {
    let currentProposal = proposal;
    // A runtime-only database error can produce one corrected, fully guarded
    // proposal. Run that correction in the same user action instead of asking
    // the user to confirm a second time.
    for (let repairAttempt = 0; repairAttempt <= 1; repairAttempt += 1) {
      if (!requestCurrent(token)) return;
      if (!currentProposal?.pending_id || !currentProposal?.sql_hash) {
        throw new Error('The generated query could not be prepared for execution.');
      }
      const response = await fetchApi(
        `/query/${activeWorkspaceId}/pending/${currentProposal.pending_id}/approve`,
        {
          method: 'POST',
          body: JSON.stringify({ sql_hash: currentProposal.sql_hash }),
        },
      );
      if (!requestCurrent(token)) return;
      if (response?.status !== 'repair_pending_approval') {
        stopReadingResult();
        setResult(response);
        return;
      }
      currentProposal = response.proposal;
    }
    throw new Error('The query could not be executed after an automatic correction.');
  };

  const handleAsk = async (resolvedQuestion, clarificationAnswers = []) => {
    const submittedQuestion = typeof resolvedQuestion === 'string' ? resolvedQuestion : question;
    if (
      !submittedQuestion.trim() ||
      !scope ||
      loading ||
      (queryInFlightRef.current && requestCurrent(queryInFlightRef.current))
    )
      return;
    const token = historyToken(scope);
    queryInFlightRef.current = token;
    setLoading(true);
    setError('');
    stopReadingResult();
    setResult(null);
    setClarification(null);
    try {
      const questionForQuery = continuationMatches(scope, continuation)
        ? `Previous question: ${continuation.interpretedRequest || continuation.question}\n\nFollow-up question: ${submittedQuestion.trim()}`
        : submittedQuestion.trim();
      const proposal = await fetchApi(`/query/${activeWorkspaceId}/generate`, {
        method: 'POST',
        body: JSON.stringify({
          question: questionForQuery,
          language_code: questionLanguage,
          clarifications: clarificationAnswers,
        }),
      });
      if (!requestCurrent(token)) return;
      if (proposal.status === 'clarification_required') {
        setClarification(proposal);
        return;
      }
      await executeProposal(proposal, token);
    } catch (err) {
      if (requestCurrent(token)) await reportError(err, 'Error running query');
    } finally {
      if (queryInFlightRef.current === token) queryInFlightRef.current = null;
      setLoading(false);
    }
  };

  const voiceCurrent = (operation) =>
    voiceOperationRef.current === operation &&
    !operation.controller.signal.aborted &&
    currentScope.current === operation.identity;

  const startVoiceInput = async () => {
    if (voiceOperationRef.current) return;
    const operation = {
      identity,
      controller: new AbortController(),
      chunks: [],
      stream: null,
      recorder: null,
    };
    voiceOperationRef.current = operation;
    const update = (stage, error = '') => {
      if (voiceCurrent(operation)) setVoice({ identity, stage, error });
    };
    const fail = (error) => {
      update('idle', error);
      if (voiceOperationRef.current === operation) voiceOperationRef.current = null;
      disposeVoiceCapture(operation);
    };
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      fail('Voice input is not supported by this browser. Try the latest Chrome, Edge, or Safari.');
      return;
    }
    update('requesting');
    try {
      const stream = await requestMicrophone(20000, { signal: operation.controller.signal });
      if (!voiceCurrent(operation)) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      operation.stream = stream;
      const preferred = GNANI_RECORDING_MIME_TYPES.find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      const recorder = preferred
        ? new MediaRecorder(stream, { mimeType: preferred })
        : new MediaRecorder(stream);
      operation.recorder = recorder;
      recorder.ondataavailable = (event) => {
        if (voiceCurrent(operation) && event.data.size > 0) operation.chunks.push(event.data);
      };
      recorder.onerror = () =>
        fail('The microphone recording stopped unexpectedly. Please try again.');
      recorder.onstop = async () => {
        if (!voiceCurrent(operation)) return;
        update('transcribing');
        operation.stream?.getTracks().forEach((track) => track.stop());
        operation.stream = null;
        try {
          let blob = new Blob(operation.chunks, { type: recorder.mimeType || 'audio/webm' });
          operation.chunks.length = 0;
          if (!blob.size) throw new Error('No audio was captured. Please try recording again.');
          if (!blob.type.includes('ogg') && !blob.type.includes('mp4'))
            blob = await convertRecordingToWav(blob, operation.controller.signal);
          if (!voiceCurrent(operation)) return;
          const audio = new FormData();
          const extension = blob.type.includes('mp4')
            ? 'm4a'
            : blob.type.includes('ogg')
              ? 'ogg'
              : 'wav';
          audio.append('file', blob, `puchoo-question.${extension}`);
          const response = await fetchApi('/voice/transcribe', {
            method: 'POST',
            body: audio,
            signal: operation.controller.signal,
          });
          if (!voiceCurrent(operation)) return;
          const transcript = response?.transcript?.trim();
          if (!transcript) throw new Error('No speech was detected. Please try again.');
          setQuestion((current) =>
            current.trim() ? `${current.trim()} ${transcript}` : transcript,
          );
          setQuestionLanguage(response?.language_code || null);
          update('idle');
        } catch (error) {
          update(
            'idle',
            error.message || 'We could not transcribe that recording. Please try again.',
          );
        } finally {
          if (voiceOperationRef.current === operation) voiceOperationRef.current = null;
          disposeVoiceCapture(operation);
        }
      };
      recorder.start();
      update('recording');
    } catch (error) {
      fail(
        error.name === 'NotAllowedError'
          ? 'Microphone access was blocked. Allow microphone access in your browser, then try again.'
          : error.message || 'We could not start the microphone. Please try again.',
      );
    }
  };

  const stopVoiceInput = () => {
    const operation = voiceOperationRef.current;
    if (!operation || !voiceCurrent(operation) || operation.recorder?.state === 'inactive') return;
    setVoice({ identity, stage: 'transcribing', error: '' });
    try {
      operation.recorder.stop();
    } catch {
      disposeVoiceCapture(operation);
      voiceOperationRef.current = null;
      setVoice({
        identity,
        stage: 'idle',
        error: 'The microphone recording stopped unexpectedly. Please try again.',
      });
    }
  };

  const stopReadingResult = () => {
    speechRequestRef.current += 1;
    stopResultSpeech(speechAudioRef, speechUrlRef);
    setSpeechState('idle');
    setSpeechError('');
    setActiveHighlight(-1);
  };

  const playResultSpeech = async () => {
    if (!result || speechState === 'loading') return;
    const clips = splitResultSpeech(buildResultSpeechPayload(presentation, result.record));
    if (!clips.length) {
      setSpeechError('There is no report available to read aloud.');
      return;
    }

    stopReadingResult();
    const requestId = speechRequestRef.current + 1;
    speechRequestRef.current = requestId;
    const language = resolveResultSpeechLanguage(result, questionLanguage);
    const pendingClips = new Map();
    const prepareClip = (index) => {
      if (!pendingClips.has(index)) {
        // Capture failures now so background requests never reject unhandled.
        pendingClips.set(
          index,
          fetchApiBlob('/voice/synthesize', {
            method: 'POST',
            body: JSON.stringify({ text: clips[index], language_code: language }),
          }).then(
            (blob) => ({ blob }),
            (error) => ({ error }),
          ),
        );
      }
      return pendingClips.get(index);
    };
    const playClip = async (index) => {
      if (speechRequestRef.current !== requestId) return;
      stopResultSpeech(speechAudioRef, speechUrlRef);
      setActiveHighlight(-1);
      if (index >= clips.length) {
        setSpeechState('idle');
        return;
      }
      setSpeechState('loading');
      try {
        const prepared = await prepareClip(index);
        pendingClips.delete(index);
        if (prepared.error) throw prepared.error;
        const audioBlob = prepared.blob;
        if (speechRequestRef.current !== requestId) return;
        const objectUrl = URL.createObjectURL(audioBlob);
        const audio = new Audio(objectUrl);
        speechUrlRef.current = objectUrl;
        speechAudioRef.current = audio;
        audio.onended = () => {
          if (isActiveResultSpeech(speechAudioRef, audio, speechRequestRef, requestId)) {
            void playClip(index + 1);
          }
        };
        audio.onerror = () => {
          if (!isActiveResultSpeech(speechAudioRef, audio, speechRequestRef, requestId)) return;
          stopResultSpeech(speechAudioRef, speechUrlRef);
          setSpeechState('idle');
          setSpeechError('Audio playback could not start. Please try again.');
        };
        const playbackState = await playAnswerAudio(audio);
        if (isActiveResultSpeech(speechAudioRef, audio, speechRequestRef, requestId)) {
          if (index + 1 < clips.length) void prepareClip(index + 1);
          setSpeechState(playbackState);
          setActiveHighlight(playbackState === 'playing' ? 0 : -1);
        }
      } catch (err) {
        if (speechRequestRef.current !== requestId) return;
        stopResultSpeech(speechAudioRef, speechUrlRef);
        setSpeechState('idle');
        setSpeechError(err.message || 'Speech is temporarily unavailable. Please try again.');
      }
    };
    await playClip(0);
  };

  const startNewChat = () => {
    composingRef.current = false;
    stopReadingResult();
    setContinuation(null);
    setQuestion('');
    setQuestionLanguage(null);
    setResult(null);
    setClarification(null);
    setError('');
    disposeVoiceCapture(voiceOperationRef.current);
    voiceOperationRef.current = null;
    setVoice({ identity, stage: 'idle', error: '' });
    window.requestAnimationFrame(() => document.querySelector('.ask-page textarea')?.focus());
  };

  const pauseOrResumeResultSpeech = async () => {
    const audio = speechAudioRef.current;
    if (!audio) return;
    if (speechState === 'playing') {
      audio.pause();
      setSpeechState('paused');
      setActiveHighlight(-1);
      return;
    }
    if (speechState === 'paused') {
      const requestId = speechRequestRef.current;
      try {
        await audio.play();
        if (!isActiveResultSpeech(speechAudioRef, audio, speechRequestRef, requestId)) return;
        setSpeechState('playing');
        setActiveHighlight(0);
      } catch {
        if (!isActiveResultSpeech(speechAudioRef, audio, speechRequestRef, requestId)) return;
        stopReadingResult();
        setSpeechError('Audio playback could not resume. Please try again.');
      }
    }
  };

  const onComposerKeyDown = (event) => {
    if (
      event.isComposing ||
      event.nativeEvent?.isComposing ||
      composingRef.current ||
      event.keyCode === 229
    )
      return;
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleAsk();
    }
  };

  const downloadReportCsv = () => {
    if (!result) return;
    const table = reportTable(result);
    const csv = buildCsv([table.labels, ...table.rows]);
    saveBlob(
      new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' }),
      reportFilename(result.record.question, 'csv'),
    );
  };

  const downloadReportPdf = async () => {
    if (!result || exportingPdf) return;
    setExportingPdf(true);
    let report;
    try {
      const { jsPDF } = await import('jspdf');
      report = createPdfReportDocument(result, resultLabels);
      document.body.append(report);
      const pdf = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
      const { default: html2canvas } = await import('html2canvas');
      const documentPdf = await renderReportPdf(pdf, report, html2canvas);
      documentPdf.save(reportFilename(result.record.question, 'pdf'));
    } catch {
      setError('We could not prepare the PDF. Please try downloading the CSV instead.');
    } finally {
      report?.remove();
      setExportingPdf(false);
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
    return () => {
      speechRequestRef.current += 1;
      stopResultSpeech(speechAudioRef, speechUrlRef);
    };
  }, [result]);

  const highlightCount = presentation.highlights?.length || 0;
  useEffect(() => {
    if (speechState !== 'playing' || !highlightCount) return undefined;
    const interval = window.setInterval(() => {
      setActiveHighlight((current) => (current + 1) % highlightCount);
    }, 1500);
    return () => window.clearInterval(interval);
  }, [highlightCount, speechState]);

  useEffect(() => {
    if (!welcome) return undefined;
    const timer = window.setTimeout(() => setWelcome(null), 7000);
    return () => window.clearTimeout(timer);
  }, [welcome]);

  const welcomeNotice = welcome ? (
    <section className="ask-welcome animate-fade-slide" role="status">
      <div className="ask-welcome-icon">
        <Sparkles size={16} />
      </div>
      <div>
        <strong>{welcome.title}</strong>
        <p>{welcome.message}</p>
      </div>
      <button type="button" onClick={() => setWelcome(null)} aria-label="Dismiss welcome message">
        <X size={16} />
      </button>
    </section>
  ) : null;

  if (user?.workspace_role === 'viewer') {
    return (
      <div className="ask-page">
        {welcomeNotice}
        <section className="ask-viewer-state">
          <div className="ask-viewer-icon">
            <ShieldCheck size={22} />
          </div>
          <span>Viewer access</span>
          <h1>Explore approved answers.</h1>
          <p>
            Your role can review shared query history, while prompts, data sources, and workspace
            settings remain protected.
          </p>
          <Link className="ask-primary-action" to="/history">
            Open history <ArrowUpRight size={17} />
          </Link>
        </section>
      </div>
    );
  }

  return (
    <div className="ask-page">
      {welcomeNotice}
      <section className="ask-stage">
        <QueryUniverse />
        <div className="ask-stage-content">
          <h1>
            A clearer way
            <br />
            to see <em>data.</em>
          </h1>
          <p>
            {continuation
              ? 'Continue your analysis with secure context from the selected question.'
              : activeWorkspace
                ? 'Ask, verify, and act on the numbers that matter.'
                : 'Connect a data source to ask secure, verified questions in your own workspace.'}
          </p>

          {!activeWorkspace ? (
            <Link className="ask-connect-action" to="/connect">
              <Database size={17} /> Connect a data source <ArrowUpRight size={16} />
            </Link>
          ) : (
            <div className={`ask-prompt-shell${loading ? ' is-loading' : ''}`} aria-busy={loading}>
              <textarea
                value={question}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  // Typed edits must not inherit a previous recording's language.
                  setQuestionLanguage(null);
                }}
                onCompositionStart={() => {
                  composingRef.current = true;
                }}
                onCompositionEnd={() => {
                  composingRef.current = false;
                }}
                onKeyDown={onComposerKeyDown}
                placeholder={
                  continuation
                    ? 'For example: Break that down by month.'
                    : 'Ask a question about your data…'
                }
                aria-label="Ask a question about your data"
                aria-describedby={loading ? 'query-processing-status' : undefined}
                rows="3"
              />
              <div className="ask-prompt-controls">
                <div className="ask-prompt-meta">
                  <span>
                    <ShieldCheck size={14} /> Read-only
                  </span>
                  <span className="ask-prompt-divider" />
                  <button
                    type="button"
                    className={`voice-button ${voiceState === 'recording' ? 'is-recording' : ''}`}
                    onClick={voiceState === 'recording' ? stopVoiceInput : startVoiceInput}
                    disabled={voiceState === 'requesting' || voiceState === 'transcribing'}
                    aria-pressed={voiceState === 'recording'}
                    aria-label={
                      voiceState === 'recording' ? 'Stop recording' : 'Speak your question'
                    }
                  >
                    {voiceState === 'requesting' || voiceState === 'transcribing' ? (
                      <LoaderCircle size={15} className="voice-spinner" />
                    ) : voiceState === 'recording' ? (
                      <Square size={12} fill="currentColor" />
                    ) : (
                      <Mic size={15} />
                    )}
                    <span>
                      {voiceState === 'recording'
                        ? 'Stop'
                        : voiceState === 'transcribing'
                          ? 'Transcribing…'
                          : voiceState === 'requesting'
                            ? 'Starting…'
                            : 'Voice'}
                    </span>
                  </button>
                  <span
                    className="voice-provider"
                    aria-label="Speech transcription powered by Gnani"
                  >
                    Powered by Gnani
                  </span>
                </div>
                <div className="ask-prompt-actions">
                  {loading ? (
                    <span
                      id="query-processing-status"
                      className="ask-query-mode ask-query-processing"
                    >
                      <i /> Analyzing data
                    </span>
                  ) : (
                    <span className="ask-query-mode">
                      Verified query <ChevronDown size={14} />
                    </span>
                  )}
                  {question && (
                    <button
                      className="ask-clear-button"
                      type="button"
                      onClick={() => {
                        setQuestion('');
                        setQuestionLanguage(null);
                      }}
                    >
                      Clear
                    </button>
                  )}
                  <button
                    className="ask-submit-button"
                    type="button"
                    onClick={handleAsk}
                    disabled={loading || !question.trim()}
                    aria-label="Run secure query"
                  >
                    {loading ? (
                      <LoaderCircle size={19} className="voice-spinner" />
                    ) : (
                      <ArrowUpRight size={20} />
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {clarification && (
            <div
              className="ask-clarification animate-fade-slide"
              role="region"
              aria-label="Clarify your question"
              aria-live="polite"
            >
              <h3 style={{ marginBottom: '0.5rem' }}>Choose one detail to continue</h3>
              <p style={{ marginBottom: '1rem' }}>{clarification.message}</p>
              <ScopeWarning message={clarification.scope_warning} />
              {clarification.interpreted_request && (
                <p className="clarification-context" style={{ marginBottom: '0.75rem' }}>
                  Interpreted request: {clarification.interpreted_request}
                </p>
              )}
              {clarification.assumptions?.length > 0 && (
                <p className="clarification-context" style={{ marginBottom: '0.75rem' }}>
                  Assumptions considered: {clarification.assumptions.join('; ')}
                </p>
              )}
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {clarification.suggestions?.map((suggestion) => (
                  <button
                    key={suggestion}
                    className="btn btn-secondary"
                    disabled={loading}
                    onClick={() => {
                      void handleAsk(question, [
                        ...(clarification.clarifications || []),
                        { reason: clarification.reason, choice: suggestion },
                      ]);
                    }}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="ask-stage-footer">
            <span>Puchoo.si intelligence · {activeWorkspace?.name || 'Private workspace'}</span>
          </div>
        </div>
      </section>

      {error && (
        <div className="ask-error" role="alert">
          <span aria-hidden="true">
            <X size={16} />
          </span>
          <p>{error}</p>
          <button type="button" onClick={() => setError('')} aria-label="Dismiss error">
            <X size={15} />
          </button>
        </div>
      )}
      {(result || continuation || question || clarification) && (
        <div className="ask-chat-actions" aria-label="Chat actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={startNewChat}
            disabled={loading || voiceState !== 'idle'}
          >
            <MessageSquarePlus size={15} /> New chat
          </button>
        </div>
      )}
      {continuation && (
        <div className="continuation-banner animate-fade-slide">
          <div className="continuation-icon">
            <MessageSquarePlus size={19} />
          </div>
          <div>
            <span>Continuing a previous question</span>
            <p>{continuation.question}</p>
          </div>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={startNewChat}
            disabled={loading || voiceState !== 'idle'}
          >
            <ArrowLeft size={16} /> Start fresh
          </button>
        </div>
      )}
      {questionLanguage && (
        <p className="voice-language" role="status">
          Question and answer language:{' '}
          {VOICE_LANGUAGES.find((language) => language.code === questionLanguage)?.label ||
            questionLanguage}
          .
        </p>
      )}
      {voiceError && (
        <p className="voice-error" role="status">
          {voiceError}
        </p>
      )}

      {result && (
        <section ref={resultRef} className="ask-results" aria-label="Query results" tabIndex="-1">
          <div className="ask-results-heading">
            <span>{verificationBadge.verified ? 'Verified output' : 'Query results'}</span>
            <p>Generated from your active workspace</p>
          </div>
          <div className="result-stack animate-fade-slide">
            <ScopeWarning message={result.record.scope_warning} />
            {(result.record.interpreted_request || result.record.assumptions?.length > 0) && (
              <details className="query-details interpretation-details">
                <summary>
                  <span className="query-details-title">
                    <Sparkles size={18} /> {resultLabels.interpretation}
                  </span>
                  <span className="query-details-hint">
                    {resultLabels.view_details} <ChevronDown size={16} />
                  </span>
                </summary>
                <div className="query-details-body">
                  <p className="interpretation-copy">
                    {result.record.interpreted_request || result.record.question}
                  </p>
                  {result.record.assumptions?.length > 0 && (
                    <div className="interpretation-assumptions">
                      <strong>Assumptions</strong>
                      <p>{result.record.assumptions.join('; ')}</p>
                    </div>
                  )}
                </div>
              </details>
            )}
            <section
              className={`result-summary-card${speechState === 'playing' ? ' is-speaking' : ''}`}
            >
              <div className="result-summary-heading">
                <div className="result-summary-icon">
                  <Sparkles size={19} />
                </div>
                <div>
                  <span className="result-overline">{resultLabels.executive_summary}</span>
                  <p>
                    {verificationBadge.verified
                      ? resultLabels.validated_answer
                      : 'Read-only query results'}
                  </p>
                </div>
              </div>
              <span className={verificationBadge.className}>{verificationBadge.label}</span>
              {verificationBadge.notice && (
                <p className="result-verification-notice" role="status">
                  {verificationBadge.notice}
                </p>
              )}
              <div className="result-summary-copy">
                <strong>{presentation.headline}</strong>
                {presentation.detail && <p>{presentation.detail}</p>}
                {presentation.translation_unavailable && (
                  <p className="result-translation-note" role="status">
                    Translation is unavailable right now, so this answer is shown in English.
                  </p>
                )}
              </div>
              <ResultSpeechControls
                speechState={speechState}
                speechError={speechError}
                onPlay={playResultSpeech}
                onPauseResume={pauseOrResumeResultSpeech}
                onStop={stopReadingResult}
              />
              {presentation.highlights?.length > 0 && (
                <div className="result-highlights">
                  {presentation.highlights.map(([label, value], index) => (
                    <div key={label} className={activeHighlight === index ? 'is-speaking' : ''}>
                      <span>{label}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {result.record.sql && (
              <details className="query-details">
                <summary>
                  <span className="query-details-title">
                    <Code2 size={18} /> {resultLabels.view_sql}
                  </span>
                  <span className="query-details-hint">
                    {resultLabels.read_only_query} <ChevronDown size={16} />
                  </span>
                </summary>
                <div className="query-details-body">
                  <p>This is the read-only SQL Puchoo.si ran to produce the answer.</p>
                  <pre>{result.record.sql}</pre>
                </div>
              </details>
            )}

            <section className="result-table-card">
              <div className="result-table-heading">
                <div>
                  <span className="result-overline">{resultLabels.detailed_results}</span>
                  <p>
                    {result.record.row_count ?? 0} {resultLabels.rows_returned}
                  </p>
                  {result.record.truncated && (
                    <p role="status">
                      Showing the first {result.record.row_count} rows; the row limit was reached.
                      Narrow the question to see the rest.
                    </p>
                  )}
                </div>
                <div className="result-table-actions">
                  <span className="result-table-status">
                    <span></span>
                    {resultLabels.read_only_query}
                  </span>
                  {result.record.rows?.length > 0 && (
                    <div className="result-export-actions" aria-label="Download report">
                      <button type="button" onClick={downloadReportCsv}>
                        <Download size={14} /> Download CSV
                      </button>
                      <button type="button" onClick={downloadReportPdf} disabled={exportingPdf}>
                        <Download size={14} /> {exportingPdf ? 'Preparing PDF…' : 'Download PDF'}
                      </button>
                    </div>
                  )}
                </div>
              </div>
              <div className="result-table-scroll">
                {result.record.rows && result.record.rows.length > 0 ? (
                  <table className="result-table">
                    <thead>
                      <tr>
                        {result.record.columns.map((c) => (
                          <th key={c}>{presentation.column_labels?.[c] || c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.record.rows.map((row, index) => (
                        <tr key={index}>
                          {result.record.columns.map((c) => (
                            <td key={c}>
                              {(presentation.display_rows?.[index] || row)[c]?.toString() || '—'}
                            </td>
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
