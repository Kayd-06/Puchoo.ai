import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
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
import { useChatState } from '../hooks/useChatState';
import { fetchApi, fetchApiBlob } from '../api/client';
import { buildCsv, renderPdfHtml } from '../utils/reportExport';
import { playAnswerAudio, requestMicrophone } from '../utils/voice';

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

async function convertRecordingToWav(blob) {
  const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextConstructor)
    throw new Error('This browser cannot prepare the recording for transcription.');
  const audioContext = new AudioContextConstructor();
  try {
    const decoded = await audioContext.decodeAudioData(await blob.arrayBuffer());
    return encodeWav(decoded);
  } finally {
    await audioContext.close();
  }
}

function saveBlob(blob, filename) {
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(href), 0);
}

function reportFilename(question, extension) {
  const title =
    question
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 48) || 'report';
  return `puchoo-${title}.${extension}`;
}

function reportTable(result) {
  const columns = result?.record?.columns || [];
  const labels = result?.presentation?.column_labels || {};
  const rows = result?.record?.rows || [];
  const displayRows = result?.presentation?.display_rows || rows;
  return {
    columns,
    labels: columns.map((column) => labels[column] || column),
    rows: rows.map((row, index) =>
      columns.map((column) => displayRows[index]?.[column] ?? row[column] ?? '—'),
    ),
  };
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
  while (remaining.length > 2000) {
    let end = Math.max(remaining.lastIndexOf('\n', 1999), remaining.lastIndexOf(' ', 1999));
    end = end > 1000 ? end + 1 : 2000;
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

function createPdfReportDocument(result, labels) {
  const report = document.createElement('article');
  report.style.cssText =
    'position:fixed;left:-100000px;top:0;width:1040px;background:#fff;color:#172b36;padding:48px;font-family:Arial,"Noto Sans",sans-serif;font-size:13px;line-height:1.45;';
  const heading = document.createElement('h1');
  heading.textContent = 'Puchoo.si report';
  heading.style.cssText = 'margin:0;color:#172b36;font-size:28px;letter-spacing:-.5px;';
  const question = document.createElement('p');
  question.textContent = result.record.question;
  question.style.cssText = 'margin:12px 0 4px;font-size:18px;font-weight:600;';
  const metadata = document.createElement('p');
  metadata.textContent = `${result.record.row_count ?? 0} ${labels.rows_returned} · Generated ${new Date().toLocaleString()}`;
  metadata.style.cssText = 'margin:0 0 24px;color:#61727d;';
  const summary = document.createElement('section');
  summary.style.cssText =
    'margin:0 0 24px;border:1px solid #d9e3e8;border-radius:12px;background:#f7fafb;padding:18px 20px;';
  const summaryLabel = document.createElement('strong');
  summaryLabel.textContent = labels.executive_summary;
  const summaryText = document.createElement('p');
  summaryText.textContent = result.presentation?.headline || '';
  summaryText.style.cssText = 'margin:6px 0 0;font-size:17px;font-weight:600;';
  summary.append(summaryLabel, summaryText);

  const detail = result.presentation?.detail;
  if (detail) {
    const detailText = document.createElement('p');
    detailText.textContent = detail;
    detailText.style.cssText = 'margin:8px 0 0;color:#405662;';
    summary.append(detailText);
  }

  const tableData = reportTable(result);
  const table = document.createElement('table');
  table.style.cssText = 'width:100%;border-collapse:collapse;font-size:12px;';
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  tableData.labels.forEach((label) => {
    const cell = document.createElement('th');
    cell.textContent = label;
    cell.style.cssText =
      'background:#172b36;color:#fff;padding:10px;text-align:left;font-weight:600;';
    headerRow.append(cell);
  });
  thead.append(headerRow);
  const tbody = document.createElement('tbody');
  tableData.rows.forEach((row, index) => {
    const tableRow = document.createElement('tr');
    row.forEach((value) => {
      const cell = document.createElement('td');
      cell.textContent = String(value);
      cell.style.cssText = `padding:9px 10px;border-bottom:1px solid #d9e3e8;background:${index % 2 ? '#f7fafb' : '#fff'};vertical-align:top;`;
      tableRow.append(cell);
    });
    tbody.append(tableRow);
  });
  table.append(thead, tbody);
  report.append(heading, question, metadata, summary, table);
  return report;
}

export function queryUniversePalette(theme) {
  if (theme === 'light') {
    return {
      composite: 'source-over',
      motion: 1.45,
      orbit: '38, 54, 63',
      pulse: '48, 68, 79',
      cluster: '38, 57, 67',
      clusterEdge: '38, 57, 67',
      dust: '16, 28, 35',
      dustSpark: '24, 38, 47',
      stream: '29, 50, 64',
      star: '15, 28, 36',
      starSpark: '19, 35, 44',
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
      const dustCount = Math.min(300, Math.max(150, Math.round(width / 6)));
      const streamCount = Math.min(430, Math.max(240, Math.round(width / 4.2)));
      const motion = queryUniversePalette(document.documentElement.dataset.theme).motion;
      const dust = Array.from({ length: dustCount }, () => ({
        kind: 'dust',
        x: Math.random() * width,
        y: Math.random() * height,
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
      particles = [...clusters, ...dust, ...streams];
    };
    const draw = (time) => {
      context.clearRect(0, 0, width, height);
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

export default function AskData() {
  const location = useLocation();
  const { activeWorkspaceId, activeWorkspace, refreshWorkspaces } = useAppContext();
  const { user } = useAuth();
  const [question, setQuestion] = useChatState(user?.id, activeWorkspaceId, 'question', '');
  const [continuation, setContinuation] = useChatState(
    user?.id,
    activeWorkspaceId,
    'continuation',
    location.state?.continuation || null,
  );
  const [questionLanguage, setQuestionLanguage] = useChatState(
    user?.id,
    activeWorkspaceId,
    'questionLanguage',
    location.state?.continuation?.languageCode || null,
  );
  const [welcome, setWelcome] = useState(() => consumeWelcome(location.state?.welcome));
  const [loading, setLoading] = useChatState(user?.id, activeWorkspaceId, 'loading', false, false);
  const [result, setResult] = useChatState(user?.id, activeWorkspaceId, 'result', null);
  const [error, setError] = useState('');
  const [clarification, setClarification] = useChatState(
    user?.id,
    activeWorkspaceId,
    'clarification',
    null,
  );
  useEffect(() => {
    const next = location.state?.continuation;
    if (!next || continuation?._routeKey === location.key) return;
    setContinuation({ ...next, _routeKey: location.key });
    setQuestion('');
    setQuestionLanguage(next.languageCode || null);
    setResult(null);
    setClarification(null);
  }, [
    location.key,
    location.state?.continuation,
    continuation?._routeKey,
    setContinuation,
    setQuestion,
    setQuestionLanguage,
    setResult,
    setClarification,
  ]);

  const [voiceState, setVoiceState] = useState('idle');
  const [voiceError, setVoiceError] = useState('');
  const [exportingPdf, setExportingPdf] = useState(false);
  const [speechState, setSpeechState] = useState('idle');
  const [speechError, setSpeechError] = useState('');
  const [activeHighlight, setActiveHighlight] = useState(-1);
  const recorderRef = useRef(null);
  const streamRef = useRef(null);
  const audioChunksRef = useRef([]);
  const resultRef = useRef(null);
  const speechAudioRef = useRef(null);
  const speechUrlRef = useRef(null);
  const speechRequestRef = useRef(0);
  const presentation = result?.presentation || {};
  const resultLabels = { ...DEFAULT_RESULT_LABELS, ...presentation.labels };
  const verificationStatus = result?.record?.verification?.status;
  const verificationBadge =
    verificationStatus === 'VERIFIED'
      ? { className: 'badge badge-ok', label: resultLabels.verified_match }
      : verificationStatus === 'FAILED'
        ? { className: 'badge badge-bad', label: 'Verification failed' }
        : { className: 'badge badge-warn', label: resultLabels.needs_review };

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

  const executeProposal = async (proposal) => {
    let currentProposal = proposal;
    // A runtime-only database error can produce one corrected, fully guarded
    // proposal. Run that correction in the same user action instead of asking
    // the user to confirm a second time.
    for (let repairAttempt = 0; repairAttempt <= 1; repairAttempt += 1) {
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
      if (response?.status !== 'repair_pending_approval') {
        stopReadingResult();
        setResult(response);
        return;
      }
      currentProposal = response.proposal;
    }
    throw new Error('The query could not be executed after an automatic correction.');
  };

  const handleAsk = async () => {
    if (!question.trim() || !activeWorkspaceId) return;
    setLoading(true);
    setError('');
    stopReadingResult();
    setResult(null);
    setClarification(null);
    try {
      const questionForQuery = continuation
        ? `Previous question: ${continuation.interpretedRequest || continuation.question}\n\nFollow-up question: ${question.trim()}`
        : question.trim();
      const proposal = await fetchApi(`/query/${activeWorkspaceId}/generate`, {
        method: 'POST',
        body: JSON.stringify({ question: questionForQuery, language_code: questionLanguage }),
      });
      if (proposal.status === 'clarification_required') {
        setClarification(proposal);
        return;
      }
      await executeProposal(proposal);
    } catch (err) {
      await reportError(err, 'Error running query');
    } finally {
      setLoading(false);
    }
  };

  const releaseMicrophone = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
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
      // Gnani accepts OGG, M4A, and WAV. Unsupported browser recordings are
      // converted to WAV in startVoiceInput before this request is made.
      const extension = blob.type.includes('mp4')
        ? 'm4a'
        : blob.type.includes('ogg')
          ? 'ogg'
          : 'wav';
      audio.append('file', blob, `puchoo-question.${extension}`);
      const response = await fetchApi('/voice/transcribe', { method: 'POST', body: audio });
      const transcript = response?.transcript?.trim();
      if (!transcript) throw new Error('No speech was detected. Please try again.');
      setQuestion((current) => (current.trim() ? `${current.trim()} ${transcript}` : transcript));
      // Follow the language detected from the recording, never a browser default.
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
      setVoiceError(
        'Voice input is not supported by this browser. Try the latest Chrome, Edge, or Safari.',
      );
      return;
    }
    setVoiceState('requesting');
    try {
      const stream = await requestMicrophone();
      streamRef.current = stream;
      audioChunksRef.current = [];
      const preferredMimeType = GNANI_RECORDING_MIME_TYPES.find((type) =>
        MediaRecorder.isTypeSupported(type),
      );
      const recorder = preferredMimeType
        ? new MediaRecorder(stream, { mimeType: preferredMimeType })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        releaseMicrophone();
        setVoiceError('The microphone recording stopped unexpectedly. Please try again.');
        setVoiceState('idle');
      };
      recorder.onstop = async () => {
        setVoiceState('transcribing');
        let blob = new Blob(audioChunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        releaseMicrophone();
        if (!blob.type.includes('ogg') && !blob.type.includes('mp4')) {
          try {
            blob = await convertRecordingToWav(blob);
          } catch {
            setVoiceError(
              'We could not prepare that recording for Gnani. Please try again in the latest Chrome, Edge, or Safari.',
            );
            setVoiceState('idle');
            recorderRef.current = null;
            return;
          }
        }
        await transcribeRecording(blob);
      };
      recorder.start();
      setVoiceState('recording');
    } catch (err) {
      releaseMicrophone();
      setVoiceState('idle');
      setVoiceError(
        err.name === 'NotAllowedError'
          ? 'Microphone access was blocked. Allow microphone access in your browser, then try again.'
          : err.message || 'We could not start the microphone. Please try again.',
      );
    }
  };

  const stopVoiceInput = () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') return;
    setVoiceState('transcribing');
    recorder.stop();
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
        const audioBlob = await fetchApiBlob('/voice/synthesize', {
          method: 'POST',
          body: JSON.stringify({ text: clips[index], language_code: language }),
        });
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
      const documentPdf = await renderPdfHtml(pdf, report, {
        autoPaging: 'text',
        html2canvas: { scale: 0.75, backgroundColor: '#ffffff' },
        margin: [22, 22, 22, 22],
        width: 798,
        windowWidth: 1040,
      });
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

          <div className="ask-stage-footer">
            <span>Puchoo.si intelligence · {activeWorkspace?.name || 'Private workspace'}</span>
          </div>
        </div>
      </section>

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
          <ScopeWarning message={clarification.scope_warning} />
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
            onClick={() => {
              setContinuation(null);
              setQuestion('');
              setQuestionLanguage(null);
            }}
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
            <span>Verified output</span>
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
                  <p>{resultLabels.validated_answer}</p>
                </div>
              </div>
              <span className={verificationBadge.className}>{verificationBadge.label}</span>
              <div className="result-summary-copy">
                <strong>{presentation.headline}</strong>
                {presentation.detail && <p>{presentation.detail}</p>}
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
