import { useEffect, useState } from 'react';
import { Menu, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Mark, PillButton, focusRing } from './ui';

const links = [
  { href: '#capabilities', label: 'Capabilities' },
  { href: '#how-it-works', label: 'How it works' },
  { href: '#security', label: 'Security' },
  { href: '#faq', label: 'FAQ' },
];

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <header
      id="top"
      className={`fixed z-40 text-white transition-all ${
        scrolled || open
          ? 'inset-x-0 top-0 bg-[#0A0F14]/80 backdrop-blur-md'
          : 'inset-x-3 top-3 rounded-t-[28px] md:inset-x-4 md:top-4'
      }`}
    >
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5 md:h-[72px] md:px-8">
        <Link
          to="/"
          className={`flex items-center gap-2 font-medium tracking-[-0.03em] ${focusRing} rounded-full`}
        >
          <Mark className="h-6 w-6" />
          Puchoo.ai
        </Link>
        <p className="hidden text-sm text-[#D1D5DB] md:block">Multilingual Text-to-SQL</p>
        <div className="hidden items-center gap-6 md:flex">
          <Link to="/login" className={`text-sm text-white ${focusRing} rounded-full px-1`}>
            Log in
          </Link>
          <PillButton to="/signup">Get started</PillButton>
        </div>
        <button
          type="button"
          className={`rounded-full p-2 md:hidden ${focusRing}`}
          aria-expanded={open}
          aria-controls="mobile-nav"
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          <span className="sr-only">{open ? 'Close menu' : 'Open menu'}</span>
        </button>
      </div>
      {open ? (
        <nav
          id="mobile-nav"
          className="border-t border-white/10 px-5 py-4 md:hidden"
          aria-label="Mobile"
        >
          <div className="flex flex-col gap-3">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className={`rounded-full px-2 py-2 text-base ${focusRing}`}
                onClick={() => setOpen(false)}
              >
                {link.label}
              </a>
            ))}
            <Link
              to="/login"
              className={`rounded-full px-2 py-2 ${focusRing}`}
              onClick={() => setOpen(false)}
            >
              Log in
            </Link>
            <PillButton to="/signup" onClick={() => setOpen(false)}>
              Get started
            </PillButton>
          </div>
        </nav>
      ) : null}
    </header>
  );
}
