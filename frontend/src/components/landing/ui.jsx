import { ArrowRight } from 'lucide-react';
import { motion, useReducedMotion } from 'framer-motion';
import { Link } from 'react-router-dom';

export const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1D4ED8]';

export function Mark({ className = 'h-7 w-7' }) {
  return (
    <svg viewBox="0 0 28 28" className={className} aria-hidden="true">
      <rect
        x="1"
        y="1"
        width="26"
        height="26"
        rx="8"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <path d="M8 18.5 14 8l6 10.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10.2 15.2h7.6" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

export function PillButton({
  to,
  href,
  children,
  variant = 'light',
  onClick,
  type = 'button',
  disabled = false,
}) {
  const classes = [
    'group inline-flex items-center justify-center gap-2 rounded-full px-5 py-2.5 text-[15px] font-medium transition-colors',
    focusRing,
    variant === 'light'
      ? 'bg-white text-[#111827] hover:bg-[#F3F4F6]'
      : 'bg-[#111827] text-white hover:bg-[#1F2937]',
    disabled ? 'cursor-not-allowed opacity-60' : '',
  ].join(' ');
  const content = (
    <>
      {children}
      <ArrowRight
        className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1"
        aria-hidden="true"
      />
    </>
  );
  if (to) {
    return (
      <Link to={to} className={classes} onClick={onClick}>
        {content}
      </Link>
    );
  }
  if (href) {
    return (
      <a href={href} className={classes} onClick={onClick}>
        {content}
      </a>
    );
  }
  return (
    <button type={type} className={classes} onClick={onClick} disabled={disabled}>
      {content}
    </button>
  );
}

export function Reveal({ children, className = '' }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-12% 0px' }}
      transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function SectionHeading({ eyebrow, title, muted, light = false }) {
  return (
    <div>
      {eyebrow ? (
        <p className={`text-sm font-medium ${light ? 'text-[#D1D5DB]' : 'text-[#6B7280]'}`}>
          {eyebrow}
        </p>
      ) : null}
      <h2
        className={`mt-3 text-[40px] leading-[1.05] font-medium tracking-[-0.03em] md:text-[48px] ${
          light ? 'text-white' : 'text-[#111827]'
        }`}
      >
        {title}{' '}
        {muted ? (
          <span className={light ? 'text-[#D1D5DB]' : 'text-[#6B7280]'}>{muted}</span>
        ) : null}
      </h2>
    </div>
  );
}
