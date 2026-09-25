import { useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import {
  ArrowRight,
  AudioLines,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  Languages,
  Plus,
  ScrollText,
  ShieldCheck,
  SquareCheck,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import NodeSphere from './NodeSphere';
import { PillButton, Reveal, SectionHeading, focusRing } from './ui';

const tools = ['FastAPI', 'React', 'Sarvam AI', 'Claude', 'PostgreSQL', 'Redis'];

const capabilities = [
  {
    id: 'multilingual',
    title: 'Multilingual questions',
    icon: Languages,
    description:
      'Ask in English or an Indian language. Sarvam AI detects the language, translates, and transliterates so the question can be understood before any SQL is proposed.',
  },
  {
    id: 'voice',
    title: 'Voice input',
    icon: AudioLines,
    description:
      'Speak the question instead of typing. Sarvam AI turns speech into text, then runs the same language detection, translation, and transliteration path.',
  },
  {
    id: 'approve',
    title: 'Approve before execute',
    icon: SquareCheck,
    description:
      'Claude Sonnet proposes the SQL. Claude Haiku gives an advisory second check. You see the SQL and a plain-language explanation. Nothing runs until you approve it.',
  },
  {
    id: 'guardrail',
    title: 'Read-only SQL guardrail',
    icon: ShieldCheck,
    description:
      'An AST-based guardrail allows only a single SELECT statement, restricts queries to approved tables and columns, and enforces row limits and timeouts.',
  },
  {
    id: 'explain',
    title: 'Explainable results',
    icon: BarChart3,
    description:
      'After approval, Puchoo.ai runs exactly one validated read-only query and returns the results, a chart suggestion, and an explanation in your language.',
  },
  {
    id: 'audit',
    title: 'Audit trail',
    icon: ScrollText,
    description:
      'An append-only audit log records every request, the generated SQL, the approval, and the result. Results are masked by policy, and history is kept per workspace.',
  },
];

const steps = [
  {
    number: '01',
    title: 'Ask',
    text: 'Type or speak a question in English or an Indian language.',
  },
  {
    number: '02',
    title: 'Review',
    text: 'Read the generated SQL and a plain-language explanation.',
  },
  {
    number: '03',
    title: 'Approve',
    text: 'Confirm the query. Nothing runs before this step.',
  },
  {
    number: '04',
    title: 'Get answers',
    text: 'See a table, a chart suggestion, and an explanation in your language.',
  },
];

const examples = [
  {
    question: 'Which course has the most students this semester?',
    language: 'English',
    dataset: 'Institute enrolment',
    bars: [72, 48, 36, 24],
  },
  {
    question: 'पिछले महीने किस विभाग का खर्च सबसे ज्यादा था?',
    language: 'Hindi',
    dataset: 'Department expenses',
    bars: [30, 64, 42, 22],
  },
  {
    question: 'Last quarter mein top 5 products by revenue kaun se the?',
    language: 'Hinglish',
    dataset: 'Campus store sales',
    bars: [80, 62, 50, 34],
  },
  {
    question: 'How many open library loans are overdue?',
    language: 'English',
    dataset: 'Library loans',
    bars: [20, 28, 44, 18],
  },
  {
    question: 'इस सप्ताह कितने छात्रों ने फीस जमा की?',
    language: 'Hindi',
    dataset: 'Fee records',
    bars: [40, 55, 70, 48],
  },
  {
    question: 'Hostel occupancy by block dikhao for this month.',
    language: 'Hinglish',
    dataset: 'Housing',
    bars: [58, 46, 66, 38],
  },
];

const faqs = [
  {
    category: 'General',
    question: 'What is Puchoo.ai?',
    answer:
      'Puchoo.ai is a secure, multilingual Text-to-SQL analytics platform. You ask about your data in English or an Indian language, by typing or by voice. It turns the question into SQL, shows that SQL with a plain-language explanation, and runs one read-only query after you approve it.',
  },
  {
    category: 'General',
    question: 'What comes back after a query runs?',
    answer:
      'The results of that one validated read-only query, a chart suggestion, and an explanation in your language.',
  },
  {
    category: 'Security',
    question: 'Can a query change my data?',
    answer:
      'No. An AST-based SQL guardrail allows only a single SELECT statement, restricts queries to approved tables and columns, and enforces row limits and timeouts.',
  },
  {
    category: 'Security',
    question: 'When does a query actually run?',
    answer:
      'Only after an explicit human approval step. FastAPI is the only security boundary. React is presentation-only and holds no secrets.',
  },
  {
    category: 'Security',
    question: 'What is recorded?',
    answer:
      'An append-only audit log records every request, the generated SQL, the approval, and the result. Results are masked by policy, and history is kept per workspace.',
  },
  {
    category: 'Languages',
    question: 'Which languages can I use, and what does Sarvam AI do?',
    answer:
      'You can type or speak in English or Indian languages. Sarvam AI handles speech-to-text, language detection, translation, and transliteration.',
  },
  {
    category: 'Languages',
    question: 'Which models propose the SQL?',
    answer:
      'Claude Sonnet proposes the SQL. Claude Haiku gives an advisory second check before you decide whether to approve it.',
  },
  {
    category: 'Accounts',
    question: 'What kinds of workspaces are there?',
    answer:
      'A Personal workspace is for an individual. An Institute members workspace is for an institution. History stays with the workspace.',
  },
];

const filters = ['General', 'Security', 'Languages', 'Accounts'];

export function About() {
  return (
    <section id="about" className="bg-[#F9FAFB] py-20 md:py-28">
      <div className="mx-auto grid max-w-6xl items-center gap-12 px-5 md:px-8 lg:grid-cols-2">
        <Reveal>
          <div className="relative aspect-square overflow-hidden rounded-3xl bg-[#0A0F14]">
            <div className="dot-grid absolute inset-0 opacity-70" aria-hidden="true" />
            <NodeSphere className="absolute inset-0 h-full w-full" />
          </div>
        </Reveal>
        <Reveal>
          <SectionHeading title="Turn plain-language questions" muted="into governed answers." />
          <p className="mt-6 max-w-xl text-[17px] leading-relaxed text-[#6B7280] md:text-[18px]">
            Ask in English or an Indian language, by typing or by voice. Puchoo.ai proposes SQL,
            explains it in plain language, and runs one validated read-only query only after you
            approve it.
          </p>
          <a
            href="#how-it-works"
            className={`mt-8 inline-flex items-center gap-2 text-[#111827] ${focusRing} rounded-full`}
          >
            How it works
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </a>
        </Reveal>
      </div>
    </section>
  );
}

export function BuiltWith() {
  const row = [...tools, ...tools];
  return (
    <section
      className="bg-white py-14"
      aria-label="Built with FastAPI, React, Sarvam AI, Claude, PostgreSQL, and Redis"
    >
      <div className="mx-auto max-w-6xl px-5 md:px-8">
        <p className="text-sm font-medium text-[#6B7280]">Built with</p>
      </div>
      <div className="relative mt-6">
        <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-white to-transparent md:w-28" />
        <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-white to-transparent md:w-28" />
        <div className="overflow-hidden">
          <div className="marquee-track items-center gap-12 px-8 py-3" aria-hidden="true">
            {row.map((name, index) => (
              <span
                key={`${name}-${index}`}
                className="text-2xl leading-none font-medium tracking-[-0.03em] text-[#111827]"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

const shapes = {
  multilingual: 'M30 90c20-50 50-70 80-40 24 24 40-10 70 6M48 118h120',
  voice: 'M110 36v62M86 78c0 28 48 28 48 0M70 78h-12M164 78h12',
  approve: 'M48 96l34 34 86-92',
  guardrail: 'M46 42h128v116H46zM72 92h76',
  explain: 'M40 140l36-62 28 34 48-78',
  audit: 'M52 36h116v128H52zM52 68h116M52 100h78',
};

function Geometry({ id }) {
  return (
    <svg viewBox="0 0 220 180" className="draw-icon h-28 w-40 text-[#1D4ED8]" aria-hidden="true">
      <path
        d={shapes[id]}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Principle() {
  return (
    <section className="relative overflow-hidden bg-[#0A0F14] px-5 py-28 text-center md:px-8 md:py-36">
      <div
        className="pointer-events-none absolute top-1/2 left-1/2 h-[420px] w-[680px] -translate-x-1/2 -translate-y-1/2"
        style={{ background: 'radial-gradient(circle, rgba(59,130,246,0.28), transparent 68%)' }}
        aria-hidden="true"
      />
      <div
        className="ring-orbit pointer-events-none absolute top-1/2 left-1/2 h-[520px] w-[520px]"
        aria-hidden="true"
      >
        <span className="absolute inset-8 rounded-full border border-white/15" />
        <span className="absolute inset-16 rounded-full border border-white/10" />
        <span className="absolute top-1/2 left-1/2 h-40 w-[28rem] -translate-x-1/2 -translate-y-1/2 rotate-12 rounded-full border border-white/20" />
      </div>
      <Reveal className="relative mx-auto max-w-4xl">
        <p className="text-[clamp(36px,6vw,72px)] leading-[1.05] font-medium tracking-[-0.04em] text-white italic">
          No query runs until you approve it.
        </p>
        <p className="mt-6 text-sm text-[#D1D5DB]">A product principle</p>
      </Reveal>
    </section>
  );
}

export function Capabilities() {
  const [active, setActive] = useState(capabilities[0].id);
  const reduce = useReducedMotion();
  const selected = capabilities.find((item) => item.id === active) || capabilities[0];

  function onKeyDown(event) {
    const ids = capabilities.map((item) => item.id);
    const index = ids.indexOf(active);
    const next = {
      ArrowDown: ids[(index + 1) % ids.length],
      ArrowRight: ids[(index + 1) % ids.length],
      ArrowUp: ids[(index - 1 + ids.length) % ids.length],
      ArrowLeft: ids[(index - 1 + ids.length) % ids.length],
      Home: ids[0],
      End: ids[ids.length - 1],
    }[event.key];
    if (!next) return;
    event.preventDefault();
    setActive(next);
    document.getElementById(`tab-${next}`)?.focus();
  }

  return (
    <section id="capabilities" className="bg-[#F9FAFB] py-20 md:py-28">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 md:px-8 lg:grid-cols-[280px_1fr]">
        <div
          role="tablist"
          aria-orientation="vertical"
          aria-label="Capabilities"
          className="flex gap-2 overflow-x-auto lg:flex-col"
        >
          {capabilities.map((item) => {
            const selectedTab = item.id === active;
            return (
              <button
                key={item.id}
                id={`tab-${item.id}`}
                type="button"
                role="tab"
                aria-selected={selectedTab}
                aria-controls={`panel-${item.id}`}
                tabIndex={selectedTab ? 0 : -1}
                onClick={() => setActive(item.id)}
                onKeyDown={onKeyDown}
                className={`rounded-2xl px-4 py-3 text-left text-sm whitespace-nowrap lg:whitespace-normal ${focusRing} ${
                  selectedTab ? 'bg-white text-[#111827]' : 'text-[#6B7280] hover:text-[#111827]'
                }`}
              >
                {item.title}
              </button>
            );
          })}
        </div>
        <div className="min-h-[280px] rounded-3xl border border-black/10 bg-white p-8 md:p-12">
          <AnimatePresence mode="wait">
            <motion.div
              key={selected.id}
              role="tabpanel"
              id={`panel-${selected.id}`}
              aria-labelledby={`tab-${selected.id}`}
              initial={reduce ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={reduce ? undefined : { opacity: 0 }}
              transition={{ duration: 0.2 }}
            >
              <Geometry id={selected.id} />
              <h3 className="mt-8 text-[32px] leading-tight font-medium tracking-[-0.03em] text-[#111827] md:text-[40px]">
                {selected.title}
              </h3>
              <p className="mt-4 max-w-xl text-[17px] leading-relaxed text-[#6B7280] md:text-[18px]">
                {selected.description}
              </p>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}

export function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-[#0A0F14] py-20 text-white md:py-28">
      <div className="mx-auto grid max-w-6xl gap-10 px-5 md:px-8 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeading light title="Four steps," muted="then an answer." />
          <p className="mt-6 max-w-md text-[17px] leading-relaxed text-[#D1D5DB] md:text-[18px]">
            The question, the SQL, and the approval stay visible. FastAPI runs one read-only query
            only after you approve it.
          </p>
        </div>
        <div className="flex flex-col gap-5">
          {steps.map((step) => (
            <Reveal key={step.number}>
              <article className="rounded-3xl border border-white/10 bg-white/[0.03] p-7 md:p-9">
                <p className="text-sm text-[#D1D5DB]">{step.number}</p>
                <h3 className="mt-4 text-[32px] font-medium tracking-[-0.03em] md:text-[40px]">
                  {step.title}
                </h3>
                <p className="mt-3 max-w-lg text-[17px] leading-relaxed text-[#D1D5DB]">
                  {step.text}
                </p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

const pipeline = ['Browser', 'FastAPI', 'Guardrail', 'Approval', 'One read-only query'];

export function Security() {
  return (
    <section id="security" className="bg-white py-20 md:py-28">
      <div className="mx-auto max-w-6xl px-5 md:px-8">
        <Reveal>
          <SectionHeading title="The boundary stays" muted="on the server." />
        </Reveal>
        <div className="mt-12 grid gap-4 md:grid-cols-3">
          <article className="rounded-3xl border border-black/10 bg-[#F9FAFB] p-6 md:col-span-2 md:p-8">
            <h3 className="text-xl font-medium tracking-[-0.02em] text-[#111827]">
              Request pipeline
            </h3>
            <ol className="mt-6 flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
              {pipeline.map((step, index) => (
                <li key={step} className="flex items-center gap-3">
                  <span
                    className={`rounded-2xl px-3 py-2 text-sm ${
                      step === 'FastAPI' ? 'bg-[#111827] text-white' : 'bg-white text-[#111827]'
                    }`}
                  >
                    {step}
                    {step === 'FastAPI' ? (
                      <span className="mt-1 block text-xs text-[#D1D5DB]">
                        Only security boundary
                      </span>
                    ) : null}
                  </span>
                  {index < pipeline.length - 1 ? (
                    <ArrowRight
                      className="hidden h-4 w-4 text-[#6B7280] md:block"
                      aria-hidden="true"
                    />
                  ) : null}
                </li>
              ))}
            </ol>
          </article>
          <SecurityCard
            title="RBAC and workspace scoping"
            text="Questions, history, and results stay inside a Personal workspace or an Institute members workspace."
          />
          <SecurityCard
            title="Result masking"
            text="Results are masked by policy before they are shown or kept in workspace history."
          />
          <SecurityCard
            title="Append-only audit log"
            text="Every request, generated SQL, approval, and result is recorded. Entries are not rewritten."
          />
          <SecurityCard
            title="Secrets never reach the browser"
            text="React is presentation-only and holds no secrets. The session token stays in an HttpOnly cookie."
          />
          <article className="rounded-3xl border border-black/10 bg-[#F9FAFB] p-6 md:col-span-2">
            <h3 className="text-xl font-medium tracking-[-0.02em] text-[#111827]">Fail closed</h3>
            <p className="mt-3 text-[16px] leading-relaxed text-[#6B7280]">
              If the guardrail, the approval step, or validation does not pass, the query does not
              run.
            </p>
          </article>
        </div>
      </div>
    </section>
  );
}

function SecurityCard({ title, text }) {
  return (
    <article className="rounded-3xl border border-black/10 bg-[#F9FAFB] p-6">
      <h3 className="text-xl font-medium tracking-[-0.02em] text-[#111827]">{title}</h3>
      <p className="mt-3 text-[16px] leading-relaxed text-[#6B7280]">{text}</p>
    </article>
  );
}

export function Examples() {
  const scroller = useRef(null);
  const reduce = useReducedMotion();

  function move(direction) {
    const node = scroller.current;
    if (!node) return;
    node.scrollBy({
      left: direction * Math.min(340, node.clientWidth * 0.8),
      behavior: reduce ? 'auto' : 'smooth',
    });
  }

  return (
    <section className="bg-[#0A0F14] py-20 text-white md:py-28" aria-labelledby="examples-heading">
      <div className="mx-auto flex max-w-6xl items-end justify-between gap-6 px-5 md:px-8">
        <div>
          <p className="text-xs tracking-[0.14em] text-[#D1D5DB] uppercase">Demo</p>
          <h2
            id="examples-heading"
            className="mt-3 text-[40px] leading-[1.05] font-medium tracking-[-0.03em] md:text-[48px]"
          >
            Questions you might ask. <span className="text-[#D1D5DB]">In a few languages.</span>
          </h2>
        </div>
        <div className="flex gap-2">
          <CarouselButton label="Previous examples" onClick={() => move(-1)}>
            <ChevronLeft aria-hidden="true" />
          </CarouselButton>
          <CarouselButton label="Next examples" onClick={() => move(1)}>
            <ChevronRight aria-hidden="true" />
          </CarouselButton>
        </div>
      </div>
      <div
        ref={scroller}
        tabIndex={0}
        aria-label="Example questions"
        className={`mt-10 flex gap-4 overflow-x-auto px-5 pb-2 md:px-8 ${focusRing}`}
        style={{ scrollPaddingLeft: '1.25rem' }}
      >
        {examples.map((example) => (
          <article
            key={example.question}
            className="min-h-[340px] w-[280px] shrink-0 rounded-3xl border border-white/10 bg-white/[0.04] p-6 md:w-[320px]"
          >
            <p className="text-xs text-[#D1D5DB]">{example.language}</p>
            <h3 className="mt-4 text-xl leading-snug font-medium tracking-[-0.02em]">
              {example.question}
            </h3>
            <p className="mt-4 text-sm text-[#D1D5DB]">{example.dataset}</p>
            <svg viewBox="0 0 200 90" className="mt-8 h-20 w-full" aria-hidden="true">
              {example.bars.map((height, index) => (
                <rect
                  key={`${example.dataset}-${height}`}
                  x={12 + index * 46}
                  y={80 - height}
                  width="28"
                  height={height}
                  rx="6"
                  fill="#3B82F6"
                  opacity={0.45 + index * 0.12}
                />
              ))}
            </svg>
          </article>
        ))}
      </div>
    </section>
  );
}

function CarouselButton({ label, onClick, children }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`grid h-11 w-11 place-items-center rounded-full bg-white text-[#111827] ${focusRing}`}
    >
      {children}
    </button>
  );
}

export function Faq() {
  const [filter, setFilter] = useState('General');
  const [open, setOpen] = useState(0);
  const visible = faqs.filter((item) => item.category === filter);

  function onFilterKey(event) {
    const index = filters.indexOf(filter);
    const next = {
      ArrowRight: filters[(index + 1) % filters.length],
      ArrowLeft: filters[(index - 1 + filters.length) % filters.length],
      Home: filters[0],
      End: filters[filters.length - 1],
    }[event.key];
    if (!next) return;
    event.preventDefault();
    setFilter(next);
    setOpen(0);
    document.getElementById(`filter-${next}`)?.focus();
  }

  return (
    <section id="faq" className="bg-[#F9FAFB] py-20 md:py-28">
      <div className="mx-auto grid max-w-6xl gap-12 px-5 md:px-8 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <SectionHeading title="Questions," muted="answered plainly." />
          <div className="mt-8 max-w-sm rounded-3xl border border-black/10 bg-white p-6">
            <h3 className="text-lg font-medium tracking-[-0.02em] text-[#111827]">
              Still have questions?
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-[#6B7280]">
              Puchoo.ai is a college OJT project. Ask your project supervisor, or use the contact
              note in the footer.
            </p>
          </div>
        </div>
        <div>
          <div role="tablist" aria-label="FAQ topics" className="flex flex-wrap gap-2">
            {filters.map((item) => {
              const selected = item === filter;
              return (
                <button
                  key={item}
                  id={`filter-${item}`}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => {
                    setFilter(item);
                    setOpen(0);
                  }}
                  onKeyDown={onFilterKey}
                  className={`rounded-full px-4 py-2 text-sm ${focusRing} ${
                    selected ? 'bg-[#111827] text-white' : 'bg-white text-[#111827]'
                  }`}
                >
                  {item}
                </button>
              );
            })}
          </div>
          <div className="mt-6 divide-y divide-black/10 border-y border-black/10">
            {visible.map((item, index) => {
              const expanded = open === index;
              const panelId = `faq-panel-${filter}-${index}`;
              return (
                <div key={item.question}>
                  <button
                    type="button"
                    className={`flex w-full items-center justify-between gap-6 py-5 text-left ${focusRing}`}
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    onClick={() => setOpen(expanded ? -1 : index)}
                  >
                    <span className="text-lg font-medium tracking-[-0.02em] text-[#111827]">
                      {item.question}
                    </span>
                    <Plus
                      className={`h-5 w-5 shrink-0 transition-transform duration-200 ${expanded ? 'rotate-45' : ''}`}
                      aria-hidden="true"
                    />
                  </button>
                  {expanded ? (
                    <div
                      id={panelId}
                      role="region"
                      className="pb-5 text-[16px] leading-relaxed text-[#6B7280]"
                    >
                      {item.answer}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}

export function FinalCta() {
  return (
    <section className="bg-[#F9FAFB] px-4 pb-20 md:px-8">
      <div className="relative mx-auto grid max-w-6xl overflow-hidden rounded-3xl bg-[#0A0F14] text-white lg:grid-cols-[1.2fr_0.8fr]">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              'radial-gradient(circle at 15% 20%, rgba(29,78,216,0.45), transparent 36%), radial-gradient(circle at 80% 80%, rgba(59,130,246,0.28), transparent 32%)',
          }}
          aria-hidden="true"
        />
        <div className="relative p-8 md:p-14">
          <h2 className="max-w-xl text-[40px] leading-[1.05] font-medium tracking-[-0.03em] md:text-[48px]">
            Start asking your data questions today.
          </h2>
          <div className="mt-8">
            <PillButton to="/signup">Get started</PillButton>
          </div>
        </div>
        <div className="relative min-h-[220px]" data-image-slot="cta">
          <img
            src="/cta-visual.png"
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            onError={(event) => {
              event.currentTarget.hidden = true;
            }}
          />
        </div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="bg-[#0A0F14] px-5 py-14 text-[#D1D5DB] md:px-8">
      <div className="mx-auto grid max-w-6xl gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <p className="text-lg font-medium tracking-[-0.03em] text-white">Puchoo.ai</p>
          <p className="mt-3 text-sm">© 2026 Puchoo.ai · A college OJT project</p>
        </div>
        <FooterColumn
          title="Product"
          links={[
            { href: '#capabilities', label: 'Capabilities' },
            { href: '#how-it-works', label: 'How it works' },
            { href: '#security', label: 'Security' },
          ]}
        />
        <FooterColumn
          title="Legal"
          links={[
            { href: '/privacy', label: 'Privacy' },
            { href: '/terms', label: 'Terms' },
          ]}
        />
        <div>
          <p className="text-sm font-medium text-white">Contact</p>
          <p className="mt-3 text-sm leading-relaxed">
            College OJT project, 2026. Questions go to your project supervisor.
          </p>
        </div>
      </div>
      <div className="mx-auto mt-12 flex max-w-6xl justify-end">
        <a href="#top" className={`text-sm text-white ${focusRing} rounded-full`}>
          Back to top
        </a>
      </div>
    </footer>
  );
}

function FooterColumn({ title, links }) {
  return (
    <div>
      <p className="text-sm font-medium text-white">{title}</p>
      <ul className="mt-3 space-y-2 text-sm">
        {links.map((link) => (
          <li key={link.href}>
            {link.href.startsWith('/') ? (
              <Link to={link.href} className={`rounded-full ${focusRing}`}>
                {link.label}
              </Link>
            ) : (
              <a href={link.href} className={`rounded-full ${focusRing}`}>
                {link.label}
              </a>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
