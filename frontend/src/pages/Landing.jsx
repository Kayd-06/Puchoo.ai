import {
  ArrowDown,
  ArrowUpRight,
  Check,
  Languages,
  Menu,
  Mic,
  Play,
  Pause,
  AudioLines,
  ShieldCheck,
  Volume2,
  X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import '../styles/landingMotion.css';
import LetterformFooter from '../components/landing/LetterformFooter';
import { Mark, focusRing } from '../components/landing/brand';

const capabilities = [
  [
    '01',
    'Ask naturally',
    'Ask in the language your team already uses. Puchoo.si turns the intent into guarded read-only SQL and runs it automatically.',
  ],
  [
    '02',
    'Automatic guarded run',
    'Server-side guardrails validate the SQL, then run it read-only. View query lets you inspect it afterward.',
  ],
  [
    '03',
    'Move with confidence',
    'Queries run read-only within your workspace; advisory verification can flag uncertainty.',
  ],
];

const demoSteps = [
  {
    label: 'Ask',
    eyebrow: 'Natural language request',
    value: 'Show the five departments with the highest spend this quarter.',
    note: 'English · spoken or typed',
  },
  {
    label: 'Run',
    eyebrow: 'Guarded read-only SQL',
    value:
      'SELECT department, SUM(amount) AS spend\nFROM expenses\nGROUP BY department\nORDER BY spend DESC LIMIT 5;',
    note: 'Automatic run · View query optional',
  },
  {
    label: 'Answer',
    eyebrow: 'Verified from your source',
    value: 'Engineering led spend at ₹8.4L, followed by Research at ₹6.7L.',
    note: 'Matched against returned data · 1.2s',
  },
];

function ProductDemo() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const [isVisible, setIsVisible] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const sectionRef = useRef(null);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setReducedMotion(preference.matches);
    updatePreference();
    preference.addEventListener('change', updatePreference);
    return () => preference.removeEventListener('change', updatePreference);
  }, []);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section || !('IntersectionObserver' in window)) {
      setIsVisible(true);
      return undefined;
    }
    const observer = new IntersectionObserver(([entry]) => setIsVisible(entry.isIntersecting), {
      threshold: 0.2,
    });
    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (paused || !isVisible || reducedMotion) return undefined;
    const timer = window.setInterval(
      () => setActive((current) => (current + 1) % demoSteps.length),
      4300,
    );
    return () => window.clearInterval(timer);
  }, [isVisible, paused, reducedMotion]);
  const step = demoSteps[active];
  return (
    <section id="demo" ref={sectionRef} className="puchoo-demo-section">
      <div className="puchoo-demo-intro" data-scroll-reveal>
        <span>04 / A guided answer</span>
        <h2>
          See the path
          <br />
          before the result.
        </h2>
        <p>
          Every interaction stays inspectable: Puchoo.si takes a question, builds guarded SQL, and
          runs it automatically after server-side validation.
        </p>
        <div className="puchoo-demo-tabs">
          {demoSteps.map((item, index) => (
            <button
              type="button"
              key={item.label}
              onClick={() => setActive(index)}
              aria-pressed={index === active}
              className={index === active ? 'is-active' : ''}
            >
              <b>{String(index + 1).padStart(2, '0')}</b> {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="puchoo-demo-pause"
          onClick={() => setPaused((value) => !value)}
          aria-label={paused ? 'Resume guided demo' : 'Pause guided demo'}
        >
          {paused ? <Play size={14} /> : <Pause size={14} />}{' '}
          {paused ? 'Resume walkthrough' : 'Pause walkthrough'}
        </button>
      </div>
      <div className="puchoo-demo-screen" data-scroll-reveal>
        <div className="puchoo-demo-window-top">
          <span>
            <i /> Puchoo.si workspace
          </span>
          <span>school_data_management</span>
        </div>
        <div className="puchoo-demo-body" aria-live={paused ? 'polite' : 'off'}>
          <div key={step.label} className="puchoo-demo-step">
            <p className="puchoo-demo-eyebrow">{step.eyebrow}</p>
            <p className={`puchoo-demo-value ${active === 1 ? 'is-code' : ''}`}>{step.value}</p>
            <p className="puchoo-demo-note">
              <Check size={15} />
              {step.note}
            </p>
          </div>
        </div>
        <div className="puchoo-demo-progress">
          {demoSteps.map((item, index) => (
            <span key={item.label} className={index === active ? 'is-active' : ''} />
          ))}
        </div>
      </div>
    </section>
  );
}

function LanguageAndVoice() {
  const languages = [
    'English',
    'हिंदी',
    'বাংলা',
    'தமிழ்',
    'తెలుగు',
    'मराठी',
    'ગુજરાતી',
    'ಕನ್ನಡ',
    'മലയാളം',
    'ਪੰਜਾਬੀ',
  ];
  const [playing, setPlaying] = useState(false);
  const [languagesRunning, setLanguagesRunning] = useState(true);
  return (
    <section id="languages" className="puchoo-language-section">
      <div className="puchoo-language-header" data-scroll-reveal>
        <div>
          <span>05 / Language belongs in the interface</span>
          <h2>Ask it your way.</h2>
        </div>
        <p>
          Speak or type a question in the language that feels natural. Puchoo.si preserves the
          governed workflow while translating intent for a clear answer.
        </p>
      </div>
      <div className="puchoo-language-marquee" aria-label="Supported languages">
        <div style={{ animationPlayState: languagesRunning ? 'running' : 'paused' }}>
          {[...languages, ...languages].map((language, index) => (
            <span
              key={`${language}-${index}`}
              aria-hidden={index >= languages.length ? true : undefined}
            >
              {language}
              <i>✦</i>
            </span>
          ))}
        </div>
      </div>
      <button
        type="button"
        className="puchoo-marquee-pause"
        onClick={() => setLanguagesRunning((value) => !value)}
        aria-pressed={!languagesRunning}
      >
        {languagesRunning ? <Pause size={14} /> : <Play size={14} />}
        {languagesRunning ? 'Pause language scroll' : 'Resume language scroll'}
      </button>
      <div className="puchoo-voice-grid" data-scroll-reveal>
        <div className={`puchoo-voice-card ${playing ? 'is-playing' : ''}`}>
          <div className="puchoo-voice-card-top">
            <span>
              <Mic size={15} /> Voice question
            </span>
            <span className="puchoo-recording-dot">Visual example</span>
          </div>
          <div className="puchoo-waveform" aria-hidden="true">
            {Array.from({ length: 38 }, (_, index) => (
              <i
                key={index}
                style={{
                  '--delay': `${index * -0.07}s`,
                  '--height': `${25 + ((index * 37) % 65)}%`,
                }}
              />
            ))}
          </div>
          <p className="puchoo-voice-transcript">“इस महीने सबसे ज़्यादा खर्च किस विभाग में हुआ?”</p>
          <div className="puchoo-voice-footer">
            <span>
              <Languages size={15} /> Hindi detected
            </span>
            <button
              type="button"
              aria-label={playing ? 'Pause waveform animation' : 'Animate voice waveform'}
              aria-pressed={playing}
              onClick={() => setPlaying((value) => !value)}
            >
              {playing ? (
                <span className="puchoo-pause-icon" />
              ) : (
                <Play size={14} fill="currentColor" />
              )}
            </button>
          </div>
        </div>
        <div className="puchoo-language-copy">
          <Volume2 size={22} />
          <h3>
            Voice in.
            <br />
            Verified clarity out.
          </h3>
          <p>
            Voice input supports Indian languages and produces the same automatic guarded run and
            evidence trail as a typed question.
          </p>
          <a href="/signup" className={`puchoo-text-link ${focusRing}`}>
            Try voice questions <ArrowUpRight size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}

function SignalField() {
  return (
    <div className="puchoo-signal-field" aria-hidden="true">
      <div className="puchoo-signal-mesh" />
      <div className="puchoo-signal-wave puchoo-signal-wave-a" />
      <div className="puchoo-signal-wave puchoo-signal-wave-b" />
      {Array.from({ length: 14 }, (_, index) => (
        <i
          className={`puchoo-signal-dot dot-${index + 1}`}
          key={index}
          style={{ '--signal-delay': `${-index * 0.47}s` }}
        />
      ))}
    </div>
  );
}

function MainHero() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeNav, setActiveNav] = useState('home');
  const menuButton = useRef(null);
  useEffect(() => {
    if (!menuOpen) return undefined;
    function closeMenu(event) {
      if (event.key === 'Escape') {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    }
    document.addEventListener('keydown', closeMenu);
    return () => document.removeEventListener('keydown', closeMenu);
  }, [menuOpen]);
  return (
    <section id="home" className="puchoo-reference-shell">
      <div className="puchoo-reference-hero">
        <SignalField />
        <header className="puchoo-reference-nav puchoo-segmented-header">
          <div className="puchoo-nav-left">
            <a
              href="#home"
              className="puchoo-nav-brand"
              aria-label="Puchoo.si home"
              onClick={() => setActiveNav('home')}
            >
              <Mark className="h-9 w-9" />
            </a>
            <nav aria-label="Primary navigation" className="puchoo-nav-segments">
              {[
                ['home', 'Home'],
                ['how', 'How it works'],
                ['gnani', 'Gnani'],
                ['faq', 'FAQs'],
              ].map(([id, label]) => (
                <a
                  key={id}
                  href={`#${id}`}
                  onClick={() => setActiveNav(id)}
                  aria-current={activeNav === id ? 'location' : undefined}
                >
                  {label}
                </a>
              ))}
            </nav>
          </div>
          <div className="puchoo-nav-note">
            <span>
              <i /> Data intelligence
            </span>
            <span>Read-only by design</span>
          </div>
          <a href="/signup" className="puchoo-nav-action">
            Get started <ArrowUpRight size={16} />
          </a>
          <button
            type="button"
            className="puchoo-nav-mobile-toggle"
            onClick={() => setMenuOpen((value) => !value)}
            ref={menuButton}
            aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
            aria-controls="landing-navigation"
            aria-expanded={menuOpen}
          >
            {menuOpen ? <X size={18} /> : <Menu size={19} />}
          </button>
        </header>
        {menuOpen && (
          <nav
            id="landing-navigation"
            aria-label="Landing navigation"
            className="puchoo-reference-menu"
          >
            <a href="#how" onClick={() => setMenuOpen(false)}>
              How it works
            </a>
            <a href="#demo" onClick={() => setMenuOpen(false)}>
              Product walkthrough
            </a>
            <a href="#gnani" onClick={() => setMenuOpen(false)}>
              Gnani voice
            </a>
            <a href="#faq" onClick={() => setMenuOpen(false)}>
              Questions & answers
            </a>
            <a href="/login" onClick={() => setMenuOpen(false)}>
              Log in
            </a>
            <a href="/signup" onClick={() => setMenuOpen(false)}>
              Create account <ArrowUpRight size={15} />
            </a>
          </nav>
        )}
        <div className="puchoo-reference-copy">
          <p className="puchoo-eyebrow puchoo-reveal puchoo-reveal-1">
            Puchoo.si / trusted analytics
          </p>
          <h1 className="puchoo-reveal puchoo-reveal-2">
            We turn data
            <br className="hidden sm:block" /> uncertainty into <em>clarity.</em>
          </h1>
          <p className="puchoo-reference-subtitle puchoo-reveal puchoo-reveal-3">
            Welcome to a calmer way to ask, verify, and act on the numbers that matter.
          </p>
          <div className="puchoo-reveal puchoo-reveal-4">
            <a href="/signup" className={`puchoo-reference-cta ${focusRing}`}>
              Start asking <ArrowUpRight size={16} />
            </a>
          </div>
        </div>
        <div className="puchoo-hero-telemetry" aria-hidden="true">
          <span>NODE / 07</span>
          <i />
          <span>VERIFY / ON</span>
        </div>
        <div className="puchoo-hero-scale" aria-hidden="true">
          <span>00</span>
          <i />
          <i />
          <i />
          <i />
          <span>100</span>
        </div>
        <a href="#how" className={`puchoo-reference-scroll ${focusRing}`}>
          Scroll down <ArrowDown size={14} />
        </a>
      </div>
    </section>
  );
}

function GnaniSection() {
  return (
    <section id="gnani" className="puchoo-gnani-section" aria-labelledby="gnani-title">
      <div className="puchoo-gnani-heading" data-scroll-reveal>
        <span className="puchoo-section-kicker">06 / The voice behind the question</span>
        <div className="puchoo-gnani-badge">
          <AudioLines size={17} /> Speech powered by Gnani
        </div>
        <h2 id="gnani-title">
          Your voice. <br />
          Powered by Gnani.
        </h2>
        <p>
          A question should start with a thought, not a keyboard. Gnani brings speech to your
          Puchoo.si workspace, from the first spoken question to an answer you can hear.
        </p>
        <a href="/signup" className={`puchoo-text-link ${focusRing}`}>
          Find your voice <ArrowUpRight size={16} />
        </a>
      </div>
      <div className="puchoo-gnani-flow" data-scroll-reveal>
        <div className="puchoo-gnani-flow-top">
          <span>ONE QUESTION. A CONNECTED FLOW.</span>
          <AudioLines size={20} />
        </div>
        <ol>
          <li>
            <span className="puchoo-gnani-icon">
              <Mic size={22} />
            </span>
            <div>
              <span className="puchoo-gnani-label">01 / SPEAK</span>
              <h3>Start in your language.</h3>
              <p>Gnani transcribes your recorded question into text in the language you spoke.</p>
            </div>
          </li>
          <li>
            <span className="puchoo-gnani-icon">
              <Languages size={22} />
            </span>
            <div>
              <span className="puchoo-gnani-label">02 / UNDERSTAND</span>
              <h3>Keep the meaning.</h3>
              <p>
                Sarvam AI translates the question to English and the answer back. Puchoo.si
                validates and runs the read-only query.
              </p>
            </div>
          </li>
          <li>
            <span className="puchoo-gnani-icon">
              <Volume2 size={22} />
            </span>
            <div>
              <span className="puchoo-gnani-label">03 / LISTEN</span>
              <h3>Hear the answer.</h3>
              <p>Gnani turns answer text into speech so you can listen as well as read.</p>
            </div>
          </li>
        </ol>
        <div className="puchoo-gnani-flow-bottom">
          <ShieldCheck size={16} />
          <span>Same workspace. Same read-only guardrails.</span>
        </div>
      </div>
    </section>
  );
}

function CommonQuestions() {
  return (
    <section id="faq" className="puchoo-faq-section">
      <div data-scroll-reveal>
        <span className="puchoo-section-kicker">07 / A little more clarity</span>
        <h2>
          Good questions.
          <br />
          Clear answers.
        </h2>
        <p>Everything starts with understanding what happens to your question.</p>
      </div>
      <div className="puchoo-faq-list" data-scroll-reveal>
        {[
          [
            'Do I need to know SQL?',
            'No. Ask in plain language, by typing or speaking. Puchoo.si proposes the SQL and shows the reasoning alongside the result.',
          ],
          [
            'Can a question change my data?',
            'Analytics queries run through server-side validation with read-only guardrails. Your workspace scopes access to the data sources available to you.',
          ],
          [
            'What do Gnani and Sarvam AI do?',
            'Gnani handles speech transcription and spoken answers. Sarvam AI handles translation, while Puchoo.si manages the analytics workflow.',
          ],
          [
            'Where do I start?',
            'Create a workspace, connect a data source, and ask your first question. You can inspect the proposed SQL and the returned evidence in the app.',
          ],
        ].map(([question, answer]) => (
          <details key={question}>
            <summary>
              {question}
              <ArrowUpRight size={18} />
            </summary>
            <p>{answer}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

// Reveal once, without hiding content when observers or motion are unavailable.
function useLandingMotion(pageRef) {
  useEffect(() => {
    const page = pageRef.current;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    let observer;
    let frame = 0;
    function configureReveals() {
      observer?.disconnect();
      if (preference.matches || !('IntersectionObserver' in window)) return;
      observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('puchoo-scroll-arrived');
            observer.unobserve(entry.target);
          });
        },
        { threshold: 0.12 },
      );
      page.querySelectorAll('[data-scroll-reveal]').forEach((element) => observer.observe(element));
    }
    function updateScroll() {
      frame = 0;
      const distance = document.documentElement.scrollHeight - window.innerHeight;
      const progress = distance > 0 ? Math.min(1, Math.max(0, window.scrollY / distance)) : 0;
      page.style.setProperty('--reading-progress', progress);
      page.style.setProperty(
        '--hero-drift',
        preference.matches ? '0px' : `${Math.min(window.scrollY * 0.12, 90)}px`,
      );
    }
    function requestUpdate() {
      if (!frame) frame = window.requestAnimationFrame(updateScroll);
    }
    configureReveals();
    updateScroll();
    function onPreferenceChange() {
      configureReveals();
      requestUpdate();
    }
    preference.addEventListener('change', onPreferenceChange);
    window.addEventListener('scroll', requestUpdate, { passive: true });
    window.addEventListener('resize', requestUpdate);
    return () => {
      observer?.disconnect();
      window.cancelAnimationFrame(frame);
      preference.removeEventListener('change', onPreferenceChange);
      window.removeEventListener('scroll', requestUpdate);
      window.removeEventListener('resize', requestUpdate);
    };
  }, [pageRef]);
}

export default function Landing() {
  const pageRef = useRef(null);
  const [globePaused, setGlobePaused] = useState(false);
  useLandingMotion(pageRef);
  const [PrivacyNotice, setPrivacyNotice] = useState(null);

  useEffect(() => {
    document.title = 'Puchoo.si | Secure AI analytics for every team';
  }, []);

  useEffect(() => {
    // Do not introduce a late layout/paint during the landing page's critical
    // loading window. The essential-cookie notice still appears shortly after.
    const task = window.setTimeout(() => {
      import('../components/SessionPrivacyNotice').then((module) =>
        setPrivacyNotice(() => module.default),
      );
    }, 6000);
    return () => window.clearTimeout(task);
  }, []);

  return (
    <div ref={pageRef} className="puchoo-reference-page">
      <div className="puchoo-reading-progress" aria-hidden="true" />
      <script type="application/ld+json">
        {JSON.stringify({
          '@context': 'https://schema.org',
          '@type': 'SoftwareApplication',
          name: 'Puchoo.si',
          applicationCategory: 'BusinessApplication',
          operatingSystem: 'Web',
          description:
            'Secure natural-language analytics with automatic guarded read-only SQL and isolated workspaces.',
        })}
      </script>
      <main id="main-content">
        <MainHero />
        <section
          id="how"
          className={`puchoo-editorial-intro${globePaused ? ' is-motion-paused' : ''}`}
        >
          <div className="puchoo-section-kicker">01 / About Puchoo.si</div>
          <div className="puchoo-editorial-grid" data-scroll-reveal>
            <h2>
              From a question
              <br />
              to a decision.
            </h2>
            <div>
              <p>
                Puchoo.si is the secure analytics workspace for people who should not have to become
                SQL experts to understand their own data.
              </p>
              <a href="/signup" className={`puchoo-text-link ${focusRing}`}>
                Explore your workspace <ArrowUpRight size={16} />
              </a>
            </div>
          </div>
          <button
            type="button"
            className="puchoo-globe-pause"
            aria-pressed={globePaused}
            onClick={() => setGlobePaused((paused) => !paused)}
          >
            {globePaused ? <Play size={13} /> : <Pause size={13} />}
            {globePaused ? 'Resume globe animation' : 'Pause globe animation'}
          </button>
          <div className="puchoo-editorial-globe" aria-hidden="true">
            <span />
            <span />
            <span />
            <i />
          </div>
        </section>
        <section className="puchoo-capability-section">
          <div className="puchoo-section-heading" data-scroll-reveal>
            <span>02 / The Puchoo.si method</span>
            <p>Built to make sophisticated data workflows feel direct, deliberate, and human.</p>
          </div>
          <div className="puchoo-capability-list" data-scroll-reveal>
            {capabilities.map(([number, title, body]) => (
              <article key={number}>
                <span>{number}</span>
                <h3>{title}</h3>
                <p>{body}</p>
                <div className="puchoo-capability-line" />
              </article>
            ))}
          </div>
        </section>
        <section className="puchoo-proof-section">
          <div className="puchoo-proof-card" data-scroll-reveal>
            <div className="puchoo-proof-top">
              <span>LIVE WORKSPACE</span>
              <span>
                <Check size={14} /> Guardrails active
              </span>
            </div>
            <p className="puchoo-proof-question">
              “Which departments changed spending most this quarter?”
            </p>
            <div className="puchoo-proof-result">
              <ShieldCheck size={18} />
              <span>Guarded read-only SQL ran automatically; View query shows what executed.</span>
            </div>
          </div>
          <div className="puchoo-proof-copy" data-scroll-reveal>
            <span>03 / Your data, in control</span>
            <h2>Intelligence that knows its boundaries.</h2>
            <p>
              Your workspace stays isolated. Read-only guardrails, scoped automatic execution, and
              advisory responses are built into every question.
            </p>
            <a
              href="/signup"
              className={`puchoo-reference-cta puchoo-reference-cta-light ${focusRing}`}
            >
              Create a workspace <ArrowUpRight size={16} />
            </a>
          </div>
        </section>
        <ProductDemo />
        <LanguageAndVoice />
        <GnaniSection />
        <CommonQuestions />
        <section className="puchoo-closing-section">
          <SignalField />
          <div data-scroll-reveal>
            <span>08 / Start with one question</span>
            <h2>
              Make your next decision
              <br />a little more certain.
            </h2>
            <p>
              Connect a source, ask in plain language, and stay in control from the first question
              to the final answer.
            </p>
            <a href="/signup" className={`puchoo-reference-cta ${focusRing}`}>
              Create your workspace <ArrowUpRight size={16} />
            </a>
          </div>
        </section>
      </main>
      <LetterformFooter />
      {PrivacyNotice && <PrivacyNotice />}
    </div>
  );
}
