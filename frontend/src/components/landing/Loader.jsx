import { useEffect, useState } from 'react';
import { useReducedMotion } from 'framer-motion';
import NodeSphere from './NodeSphere';
import { focusRing } from './ui';

const SEEN_KEY = 'puchoo-loader-seen-v2';
const START_KEY = 'puchoo-loader-start-v2';
const DURATION = 2800;

function finish(setDismissed) {
  sessionStorage.setItem(SEEN_KEY, '1');
  sessionStorage.removeItem(START_KEY);
  setDismissed(true);
}

export default function Loader() {
  const reduce = useReducedMotion();
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem(SEEN_KEY) === '1');
  const [percent, setPercent] = useState(0);
  const visible = !reduce && !dismissed;

  useEffect(() => {
    if (!visible) return undefined;
    const now = Date.now();
    const started = Number(sessionStorage.getItem(START_KEY) || now);
    if (!sessionStorage.getItem(START_KEY)) sessionStorage.setItem(START_KEY, String(now));
    const timer = setInterval(() => {
      const next = Math.min(100, Math.round(((Date.now() - started) / DURATION) * 100));
      setPercent(next);
      if (next >= 100) finish(setDismissed);
    }, 40);
    const onKey = (event) => {
      if (event.key === 'Escape') finish(setDismissed);
    };
    window.addEventListener('keydown', onKey);
    return () => {
      clearInterval(timer);
      window.removeEventListener('keydown', onKey);
    };
  }, [visible]);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-0 z-[70] grid place-items-center bg-[#070b10] px-4 text-white"
      role="dialog"
      aria-label="Loading Puchoo.ai"
    >
      <div
        className="dot-grid pointer-events-none absolute inset-0 opacity-80"
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="streak top-[18%]" />
        <span className="streak top-[46%]" style={{ animationDelay: '-5s' }} />
        <span className="streak top-[72%]" style={{ animationDelay: '-9s' }} />
      </div>
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: 'radial-gradient(circle at 50% 42%, rgba(37,99,235,0.28), transparent 46%)',
        }}
        aria-hidden="true"
      />
      <div className="relative flex w-full max-w-5xl flex-col items-center">
        <div className="relative h-[46vh] min-h-[240px] w-full max-w-3xl">
          <NodeSphere className="h-full w-full" />
        </div>
        <p className="mt-2 text-sm tracking-[0.04em] text-[#D1D5DB]">Getting ready · {percent}%</p>
        <button
          type="button"
          className={`mt-6 rounded-full px-3 py-1 text-sm text-[#D1D5DB] ${focusRing}`}
          onClick={() => finish(setDismissed)}
        >
          Skip
        </button>
      </div>
    </div>
  );
}
