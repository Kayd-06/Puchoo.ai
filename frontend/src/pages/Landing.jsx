import { ArrowDown, ArrowUpRight, Check, Languages, Menu, Mic, Play, ShieldCheck, Volume2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Mark, focusRing } from '../components/landing/brand';

const capabilities = [
  ['01', 'Ask naturally', 'Ask in the language your team already uses. Puchoo.si turns the intent into a safe, readable proposal.'],
  ['02', 'Approve with context', 'Read the SQL and plain-language reasoning before anything touches your data.'],
  ['03', 'Move with confidence', 'Every approved answer is read-only, verified, and isolated to your workspace.'],
];

const demoSteps = [
  { label: 'Ask', eyebrow: 'Natural language request', value: 'Show the five departments with the highest spend this quarter.', note: 'English · spoken or typed' },
  { label: 'Review', eyebrow: 'Puchoo.si proposes safe SQL', value: 'SELECT department, SUM(amount) AS spend\nFROM expenses\nGROUP BY department\nORDER BY spend DESC LIMIT 5;', note: 'Read-only · approval required' },
  { label: 'Answer', eyebrow: 'Verified from your source', value: 'Engineering led spend at ₹8.4L, followed by Research at ₹6.7L.', note: 'Matched against returned data · 1.2s' },
];

function ProductDemo() {
  const [active, setActive] = useState(0);
  const [isVisible, setIsVisible] = useState(false);
  const sectionRef = useRef(null);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section || !('IntersectionObserver' in window)) {
      setIsVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => setIsVisible(entry.isIntersecting), { threshold: 0.2 });
    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isVisible || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined;
    const timer = window.setInterval(() => setActive((current) => (current + 1) % demoSteps.length), 4300);
    return () => window.clearInterval(timer);
  }, [isVisible]);
  const step = demoSteps[active];
  return <section ref={sectionRef} className="puchoo-demo-section">
    <div className="puchoo-demo-intro"><span>03 / A guided answer</span><h2>See the path<br />before the result.</h2><p>Every interaction is intentionally visible: Puchoo.si takes a question, proposes the logic, and only runs it with your approval.</p><div className="puchoo-demo-tabs">{demoSteps.map((item, index) => <button type="button" key={item.label} onClick={() => setActive(index)} className={index === active ? 'is-active' : ''}><b>{String(index + 1).padStart(2, '0')}</b>{item.label}</button>)}</div></div>
    <div className="puchoo-demo-screen"><div className="puchoo-demo-window-top"><span><i /> Puchoo.si workspace</span><span>school_data_management</span></div><div className="puchoo-demo-body" aria-live="polite"><div key={step.label} className="puchoo-demo-step"><p className="puchoo-demo-eyebrow">{step.eyebrow}</p><p className={`puchoo-demo-value ${active === 1 ? 'is-code' : ''}`}>{step.value}</p><p className="puchoo-demo-note"><Check size={15} />{step.note}</p></div></div><div className="puchoo-demo-progress">{demoSteps.map((item, index) => <span key={item.label} className={index === active ? 'is-active' : ''} />)}</div></div>
  </section>;
}

function LanguageAndVoice() {
  const languages = ['English', 'हिंदी', 'বাংলা', 'தமிழ்', 'తెలుగు', 'मराठी', 'ગુજરાતી', 'ಕನ್ನಡ', 'മലയാളം', 'ਪੰਜਾਬੀ'];
  const [playing, setPlaying] = useState(false);
  return <section className="puchoo-language-section">
    <div className="puchoo-language-header"><div><span>04 / Language belongs in the interface</span><h2>Ask it your way.</h2></div><p>Speak or type a question in the language that feels natural. Puchoo.si preserves the governed workflow while translating intent for a clear answer.</p></div>
    <div className="puchoo-language-marquee" aria-label="Supported languages"><div>{[...languages, ...languages].map((language, index) => <span key={`${language}-${index}`}>{language}<i>✦</i></span>)}</div></div>
    <div className="puchoo-voice-grid"><div className={`puchoo-voice-card ${playing ? 'is-playing' : ''}`}><div className="puchoo-voice-card-top"><span><Mic size={15} /> Voice question</span><span className="puchoo-recording-dot">Listening</span></div><div className="puchoo-waveform" aria-hidden="true">{Array.from({ length: 38 }, (_, index) => <i key={index} style={{ '--delay': `${index * -.07}s`, '--height': `${25 + ((index * 37) % 65)}%` }} />)}</div><p className="puchoo-voice-transcript">“इस महीने सबसे ज़्यादा खर्च किस विभाग में हुआ?”</p><div className="puchoo-voice-footer"><span><Languages size={15} /> Hindi detected</span><button type="button" aria-label={playing ? 'Pause voice example' : 'Play voice example'} aria-pressed={playing} onClick={() => setPlaying((value) => !value)}>{playing ? <span className="puchoo-pause-icon" /> : <Play size={14} fill="currentColor" />}</button></div></div><div className="puchoo-language-copy"><Volume2 size={22} /><h3>Voice in.<br />Verified clarity out.</h3><p>Voice input supports supported Indian languages and produces the same proposal, review, and evidence trail as a typed question.</p><a href="/signup" className={`puchoo-text-link ${focusRing}`}>Try voice questions <ArrowUpRight size={16} /></a></div></div>
  </section>;
}

function SignalField() {
  return <div className="puchoo-signal-field" aria-hidden="true">
    <div className="puchoo-signal-mesh" />
    <div className="puchoo-signal-wave puchoo-signal-wave-a" />
    <div className="puchoo-signal-wave puchoo-signal-wave-b" />
    {Array.from({ length: 14 }, (_, index) => <i className={`puchoo-signal-dot dot-${index + 1}`} key={index} style={{ '--signal-delay': `${-index * 0.47}s` }} />)}
  </div>;
}

function MainHero() {
  const [menuOpen, setMenuOpen] = useState(false);
  return <section className="puchoo-reference-shell">
    <div className="puchoo-reference-hero">
      <SignalField />
      <header className="puchoo-reference-nav">
        <a href="/" className={`relative z-20 flex items-center gap-2 text-[15px] font-semibold tracking-[-.04em] text-white ${focusRing} rounded-full`}><Mark className="h-6 w-6" />Puchoo.si</a>
        <span className="hidden text-xs font-medium tracking-[.01em] text-[#e1e8f5] sm:block">Data intelligence</span>
        <button type="button" className={`relative z-20 grid h-10 w-10 place-items-center rounded-full border border-white/10 text-white transition hover:bg-white/10 ${focusRing}`} onClick={() => setMenuOpen((value) => !value)} aria-label="Open navigation" aria-expanded={menuOpen}>{menuOpen ? <X size={18} /> : <Menu size={19} />}</button>
      </header>
      {menuOpen && <nav className="puchoo-reference-menu"><a href="#how" onClick={() => setMenuOpen(false)}>How it works</a><a href="/login" onClick={() => setMenuOpen(false)}>Log in</a><a href="/signup" onClick={() => setMenuOpen(false)}>Create account <ArrowUpRight size={15} /></a></nav>}
      <main className="puchoo-reference-copy">
        <p className="puchoo-eyebrow puchoo-reveal puchoo-reveal-1">Puchoo.si / trusted analytics</p>
        <h1 className="puchoo-reveal puchoo-reveal-2">We turn data<br className="hidden sm:block" /> uncertainty into <em>clarity.</em></h1>
        <p className="puchoo-reference-subtitle puchoo-reveal puchoo-reveal-3">Welcome to a calmer way to ask, verify, and act on the numbers that matter.</p>
        <div className="puchoo-reveal puchoo-reveal-4"><a href="/signup" className={`puchoo-reference-cta ${focusRing}`}>Start asking <ArrowUpRight size={16} /></a></div>
      </main>
      <div className="puchoo-hero-telemetry" aria-hidden="true"><span>NODE / 07</span><i /><span>VERIFY / ON</span></div>
      <div className="puchoo-hero-scale" aria-hidden="true"><span>00</span><i /><i /><i /><i /><span>100</span></div>
      <a href="#how" className={`puchoo-reference-scroll ${focusRing}`}>Scroll down <ArrowDown size={14} /></a>
    </div>
  </section>;
}

export default function Landing() {
  const [PrivacyNotice, setPrivacyNotice] = useState(null);

  useEffect(() => {
    document.title = 'Puchoo.si | Secure AI analytics for every team';
  }, []);

  useEffect(() => {
    // Do not introduce a late layout/paint during the landing page's critical
    // loading window. The essential-cookie notice still appears shortly after.
    const task = window.setTimeout(() => {
      import('../components/SessionPrivacyNotice').then((module) => setPrivacyNotice(() => module.default));
    }, 6000);
    return () => window.clearTimeout(task);
  }, []);

  return <div id="main-content" className="puchoo-reference-page">
    <script type="application/ld+json">{JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'SoftwareApplication',
      name: 'Puchoo.si',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      description: 'Secure natural-language analytics with read-only SQL review and isolated workspaces.',
      url: 'https://puchoo.ai/',
    })}</script>
    <MainHero />
    <section id="how" className="puchoo-editorial-intro">
      <div className="puchoo-section-kicker">01 / About Puchoo.si</div>
      <div className="puchoo-editorial-grid"><h2>From a question<br />to a decision.</h2><div><p>Puchoo.si is the secure analytics workspace for people who should not have to become SQL experts to understand their own data.</p><a href="/signup" className={`puchoo-text-link ${focusRing}`}>Explore your workspace <ArrowUpRight size={16} /></a></div></div>
      <div className="puchoo-editorial-globe" aria-hidden="true"><span /><span /><span /><i /></div>
    </section>
    <section className="puchoo-capability-section">
      <div className="puchoo-section-heading"><span>02 / The Puchoo.si method</span><p>Built to make sophisticated data workflows feel direct, deliberate, and human.</p></div>
      <div className="puchoo-capability-list">{capabilities.map(([number, title, body]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{body}</p><div className="puchoo-capability-line" /></article>)}</div>
    </section>
    <section className="puchoo-proof-section">
      <div className="puchoo-proof-card"><div className="puchoo-proof-top"><span>LIVE WORKSPACE</span><span><Check size={14} /> Guardrails active</span></div><p className="puchoo-proof-question">“Which departments changed spending most this quarter?”</p><div className="puchoo-proof-result"><ShieldCheck size={18} /><span>SQL proposed, reviewed and verified before the answer appears.</span></div></div>
      <div className="puchoo-proof-copy"><span>03 / Your data, in control</span><h2>Intelligence that knows its boundaries.</h2><p>Your workspace stays isolated. Read-only guardrails, human approval, and verified responses are built into every question.</p><a href="/signup" className={`puchoo-reference-cta puchoo-reference-cta-light ${focusRing}`}>Create a workspace <ArrowUpRight size={16} /></a></div>
    </section>
    <ProductDemo />
    <LanguageAndVoice />
    <section className="puchoo-closing-section"><SignalField /><div><span>05 / Start with one question</span><h2>Make your next decision<br />a little more certain.</h2><p>Connect a source, ask in plain language, and stay in control from the first question to the final answer.</p><a href="/signup" className={`puchoo-reference-cta ${focusRing}`}>Create your workspace <ArrowUpRight size={16} /></a></div></section>
    <footer className="puchoo-reference-footer"><a href="/" className="flex items-center gap-2 font-semibold tracking-[-.04em]"><Mark className="h-6 w-6" />Puchoo.si</a><span>© {new Date().getFullYear()} Puchoo.si</span><div><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/login">Log in</a></div></footer>
    {PrivacyNotice && <PrivacyNotice />}
  </div>;
}
