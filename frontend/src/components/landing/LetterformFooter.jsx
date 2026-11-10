import { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, Pause, Play } from 'lucide-react';
import { Mark } from './brand';
import { footerLetters, footerViewBox } from './footerLetterforms';
import './letterformFooter.css';
import { useLetterformMotion } from './useLetterformMotion';

export default function LetterformFooter() {
  const footerRef = useRef(null);
  const svgRef = useRef(null);
  const [visible, setVisible] = useState(() => !('IntersectionObserver' in window));
  const [entered, setEntered] = useState(() => !('IntersectionObserver' in window));
  const [reduced, setReduced] = useState(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  const [paused, setPaused] = useState(false);
  const [active, setActive] = useState(0);
  const [hovered, setHovered] = useState(null);

  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    function updatePreference() {
      setReduced(preference.matches);
    }
    preference.addEventListener('change', updatePreference);
    let observer;
    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(
        ([entry]) => {
          setVisible(entry.isIntersecting);
          if (entry.isIntersecting) setEntered(true);
        },
        { threshold: 0.12 },
      );
      observer.observe(footerRef.current);
    }
    return () => {
      observer?.disconnect();
      preference.removeEventListener('change', updatePreference);
    };
  }, []);

  useEffect(() => {
    if (!visible || reduced || paused || hovered !== null) return undefined;
    const timer = window.setInterval(
      () => setActive((index) => (index + 1) % footerLetters.length),
      1700,
    );
    return () => window.clearInterval(timer);
  }, [visible, reduced, paused, hovered]);

  useLetterformMotion(svgRef, visible && !reduced && !paused);
  const highlighted = hovered ?? active;
  return (
    <footer
      ref={footerRef}
      className="puchoo-letter-footer"
      data-entered={entered}
      data-motion={visible && !reduced && !paused}
    >
      <div className="puchoo-letter-footer-top">
        <div className="puchoo-letter-footer-intro">
          <a href="/" className="puchoo-letter-brand">
            <Mark className="h-8 w-8" />
            Puchoo.si
          </a>
          <p>
            Less uncertainty.
            <br />
            More <span>clarity</span> in every question.
          </p>
        </div>
        <nav aria-label="Footer navigation" className="puchoo-letter-footer-links">
          <div>
            <span>Product</span>
            <a href="#how">How it works</a>
            <a href="#gnani">Gnani voice</a>
            <a href="#faq">FAQs</a>
          </div>
          <div>
            <span>Workspace</span>
            <a href="/signup">
              Get started <ArrowUpRight size={13} />
            </a>
            <a href="/login">Log in</a>
          </div>
          <div>
            <span>Legal</span>
            <a href="/privacy">Privacy</a>
            <a href="/terms">Terms</a>
          </div>
        </nav>
      </div>
      <div className="puchoo-letter-footer-meta">
        <div>
          <p>Read-only by design. Clear by nature.</p>
          <span>© {new Date().getFullYear()} Puchoo.si</span>
        </div>
        {!reduced && (
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            aria-pressed={paused}
            aria-label={paused ? 'Resume letter animation' : 'Pause letter animation'}
          >
            {paused ? <Play size={13} /> : <Pause size={13} />}
            <span>{paused ? 'Resume motion' : 'Pause motion'}</span>
          </button>
        )}
      </div>
      <div className="puchoo-letter-wordmark" aria-hidden="true">
        <svg
          ref={svgRef}
          viewBox={footerViewBox}
          focusable="false"
          onPointerLeave={() => setHovered(null)}
        >
          {footerLetters.map((glyph, index) => (
            <g
              key={`${glyph.letter}-${index}`}
              className="puchoo-letter-reveal"
              style={{ '--letter-delay': `${index * 65}ms` }}
            >
              <g
                className={`puchoo-letter-glyph${highlighted === index ? ' is-highlighted' : ''}`}
                onPointerEnter={() => setHovered(index)}
              >
                <path className="puchoo-letter-fill" d={glyph.path} />
                <g className="puchoo-letter-nodes">
                  {glyph.nodes.map(([x, y], node) => (
                    <g key={node}>
                      <circle
                        className="puchoo-letter-node-hit"
                        data-letter-index={index}
                        data-letter-node={node}
                        cx={x}
                        cy={y}
                        r="6"
                      />
                      <circle className="puchoo-letter-node" cx={x} cy={y} r="1.5" />
                    </g>
                  ))}
                </g>
              </g>
            </g>
          ))}
        </svg>
      </div>
    </footer>
  );
}
