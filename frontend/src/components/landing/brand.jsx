export const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1D4ED8]';

export function Mark({ className = 'h-8 w-8' }) {
  return <img src="/puchoo-logo-192.png" className={`puchoo-brand-logo ${className}`} alt="" aria-hidden="true" draggable="false" />;
}
