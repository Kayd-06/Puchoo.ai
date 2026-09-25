import { useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Cookie, ShieldCheck, X } from 'lucide-react';
import { Link } from 'react-router-dom';

const ACKNOWLEDGED = 'puchoo-essential-cookie-notice-v1';

export default function CookieNotice() {
  const reduce = useReducedMotion();
  const [visible, setVisible] = useState(() => window.localStorage.getItem(ACKNOWLEDGED) !== '1');
  function dismiss() {
    window.localStorage.setItem(ACKNOWLEDGED, '1');
    setVisible(false);
  }

  return <AnimatePresence>{visible && <motion.aside
    role="dialog" aria-label="Essential cookie notice" aria-live="polite"
    initial={reduce ? false : { opacity: 0, y: 28, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16 }} transition={{ duration: .42, ease: [0.16, 1, .3, 1] }}
    className="fixed right-4 bottom-4 z-[100] w-[min(430px,calc(100vw-2rem))] overflow-hidden rounded-3xl border border-white/20 bg-[#0b1831]/95 p-5 text-white shadow-[0_24px_70px_rgba(3,10,26,.48)] backdrop-blur-xl"
  >
    <div className="pointer-events-none absolute -top-16 -right-12 h-40 w-40 rounded-full bg-[#769dff]/20 blur-3xl" />
    <div className="relative flex gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-white/10 text-[#b8ceff]"><Cookie size={20} /></span><div className="pr-5"><p className="font-medium tracking-[-.02em]">Your session stays private</p><p className="mt-2 text-sm leading-relaxed text-[#c1cee5]">Puchoo uses essential cookies only: an encrypted session reference to keep you signed in and a CSRF token to protect actions. We do not use advertising or cross-site tracking cookies.</p></div></div>
    <div className="relative mt-5 flex flex-wrap items-center gap-3"><button type="button" onClick={dismiss} className="rounded-full bg-[#e8eefc] px-4 py-2 text-sm font-medium text-[#0b1831] transition hover:bg-white">Got it</button><Link to="/privacy" className="text-sm text-[#c7d5ef] underline-offset-4 hover:underline">Privacy details</Link><span className="ml-auto inline-flex items-center gap-1 text-xs text-[#aee1c4]"><ShieldCheck size={14} /> essential only</span></div>
    <button type="button" onClick={dismiss} aria-label="Close cookie notice" className="absolute top-3 right-3 rounded-full p-1 text-[#b8c7e2] hover:bg-white/10"><X size={16} /></button>
  </motion.aside>}</AnimatePresence>;
}
