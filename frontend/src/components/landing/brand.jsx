export const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1D4ED8]';

export function Mark({ className = 'h-7 w-7' }) {
  return (
    <svg viewBox="0 0 28 28" className={className} aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" rx="8" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 18.5 14 8l6 10.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10.2 15.2h7.6" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
