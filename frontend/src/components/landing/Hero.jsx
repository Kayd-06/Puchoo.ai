import { useEffect, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { PillButton, focusRing } from './ui';

const stages = [
  {
    id: 'ask',
    label: 'Question',
    body: (
      <p className="text-left text-lg leading-relaxed text-white">
        पिछले महीने किस विभाग की बिक्री सबसे अधिक रही?
      </p>
    ),
  },
  {
    id: 'translate',
    label: 'English',
    body: (
      <p className="text-left text-lg leading-relaxed text-white">
        Which department had the highest sales last month?
      </p>
    ),
  },
  {
    id: 'sql',
    label: 'SQL',
    body: (
      <pre className="overflow-x-auto text-left text-[13px] leading-relaxed text-[#D1D5DB]">
        {`SELECT department, SUM(amount) AS total_sales
FROM sales
WHERE sale_date >= DATE('now', 'start of month', '-1 month')
  AND sale_date < DATE('now', 'start of month')
GROUP BY department
ORDER BY total_sales DESC
LIMIT 10;`}
      </pre>
    ),
  },
  {
    id: 'approve',
    label: 'Approval',
    body: (
      <div className="text-left">
        <p className="text-sm leading-relaxed text-[#D1D5DB]">
          This reads department totals for last month. It does not change any rows.
        </p>
        <span className="mt-5 inline-flex rounded-full bg-white px-4 py-2 text-sm font-medium text-[#111827]">
          Approve & run
        </span>
      </div>
    ),
  },
  {
    id: 'results',
    label: 'Results',
    body: (
      <div className="text-left">
        <table className="w-full text-left text-sm text-white">
          <caption className="sr-only">Demo department sales</caption>
          <thead className="text-[#D1D5DB]">
            <tr>
              <th className="pb-2 font-medium">Department</th>
              <th className="pb-2 font-medium">Sales</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['Science', '128'],
              ['Arts', '96'],
              ['Commerce', '84'],
            ].map(([name, value]) => (
              <tr key={name} className="border-t border-white/10">
                <td className="py-2">{name}</td>
                <td className="py-2">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <svg viewBox="0 0 240 72" className="mt-4 h-16 w-full" aria-hidden="true">
          {[48, 36, 28].map((height, index) => (
            <rect
              key={height}
              x={16 + index * 72}
              y={64 - height}
              width="36"
              height={height}
              rx="6"
              fill={index === 0 ? '#3B82F6' : '#1D4ED8'}
              opacity={index === 0 ? 1 : 0.7}
            />
          ))}
        </svg>
      </div>
    ),
  },
];

export default function Hero() {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(reduce ? stages.length - 1 : 0);

  useEffect(() => {
    if (reduce) return undefined;
    const timer = setInterval(() => setIndex((current) => (current + 1) % stages.length), 2400);
    return () => clearInterval(timer);
  }, [reduce]);

  const stage = stages[index];

  return (
    <section className="relative overflow-hidden bg-[#0A0F14] pt-32 text-white md:pt-40">
      <div
        className="dot-grid pointer-events-none absolute inset-0 opacity-70"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute top-[-10%] left-1/2 h-[520px] w-[720px] -translate-x-1/2 rounded-full"
        style={{
          background:
            'radial-gradient(circle, rgba(59,130,246,0.28), rgba(29,78,216,0.08) 42%, transparent 70%)',
        }}
        aria-hidden="true"
      />
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <span className="streak top-[14%]" />
        <span className="streak top-[74%]" style={{ animationDelay: '-6s' }} />
        <span className="streak top-[86%]" style={{ animationDelay: '-11s' }} />
      </div>
      <div className="relative mx-auto max-w-4xl px-5 pb-20 text-center md:px-8">
        <h1 className="text-[clamp(44px,7vw,84px)] leading-[0.96] font-medium tracking-[-0.04em]">
          Ask your data anything. <span className="text-[#D1D5DB]">In your language.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-[17px] leading-relaxed text-[#D1D5DB] md:text-[18px]">
          Safe, approved, read-only analytics for students, teams and institutes.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <PillButton to="/signup">Get started</PillButton>
          <PillButton href="#how-it-works">See how it works</PillButton>
        </div>

        <div className="mx-auto mt-14 max-w-xl rounded-3xl border border-white/10 bg-white/[0.06] p-5 text-left backdrop-blur-md md:p-6">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-xs tracking-[0.14em] text-[#D1D5DB] uppercase">Demo</p>
            <p className="text-xs text-[#D1D5DB]">{stage.label}</p>
          </div>
          <p className="sr-only">
            Demo. A Hindi question is translated, shown as SQL with a plain explanation, and run
            only after approval. The sample result is a small table and bar chart.
          </p>
          <div aria-hidden="true" className="min-h-[210px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={stage.id}
                initial={reduce ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={reduce ? undefined : { opacity: 0 }}
                transition={{ duration: 0.25 }}
              >
                {stage.body}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
        <a
          href="#about"
          className={`mt-10 inline-flex flex-col items-center gap-3 text-xs tracking-[0.18em] text-[#D1D5DB] uppercase ${focusRing} rounded-full`}
        >
          Scroll
          <span className="scroll-cue block h-8 w-px bg-white/80" aria-hidden="true" />
        </a>
      </div>
    </section>
  );
}
