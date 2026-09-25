import { Link } from 'react-router-dom';
import { Mark, focusRing } from '../landing/ui';

export default function AuthShell({ title, subtitle, children, footer }) {
  return (
    <div className="site grid min-h-screen bg-[#070b17] lg:grid-cols-[1.08fr_.92fr]">
      <section className="relative flex min-h-[42vh] flex-col justify-between overflow-hidden bg-[#0c1830] px-6 py-8 text-white md:px-12 md:py-12">
        <div className="puchoo-noise pointer-events-none absolute inset-0" aria-hidden="true" />
        <div
          className="pointer-events-none absolute -top-20 -left-10 h-80 w-80 rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(116,156,246,0.32), transparent 68%)' }}
          aria-hidden="true"
        />
        <Link
          to="/"
          className={`relative flex items-center gap-2 font-medium tracking-[-0.03em] ${focusRing} w-fit rounded-full`}
        >
          <Mark className="h-6 w-6" />
          Puchoo.ai
        </Link>
        <div className="relative mt-16 max-w-lg lg:mt-0">
          <p className="text-xs tracking-[.18em] text-[#aebcd6] uppercase">Puchoo account</p>
          <h1 className="mt-5 text-[clamp(36px,5vw,60px)] leading-[.94] font-medium tracking-[-0.055em]">
            Intelligence starts with a <span className="text-[#9dbaf5]">safe question.</span>
          </h1>
          <p className="mt-5 text-[16px] leading-relaxed text-[#D1D5DB] md:text-[18px]">
            Secure sign-in, verified email codes, and governed data exploration in one place.
          </p>
        </div>
      </section>
      <section className="flex items-center bg-[#edf1f9] px-6 py-12 md:px-14">
        <div className="mx-auto w-full max-w-md">
          <h2 className="text-[36px] font-medium tracking-[-0.045em] text-[#0c1830]">{title}</h2>
          <p className="mt-2 text-[16px] leading-relaxed text-[#60708d]">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <p className="mt-6 text-sm text-[#6B7280]">{footer}</p>
        </div>
      </section>
    </div>
  );
}

export function Field({ id, label, error, children }) {
  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-medium text-[#111827]">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="mt-2 text-sm text-[#991B1B]">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass = (invalid) =>
  `w-full rounded-2xl border bg-white px-4 py-3 text-[16px] text-[#111827] ${focusRing} ${
    invalid ? 'border-[#991B1B]' : 'border-black/10'
  }`;
