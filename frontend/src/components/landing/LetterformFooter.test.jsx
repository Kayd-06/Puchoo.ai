import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import LetterformFooter from './LetterformFooter';

beforeEach(() => {
  vi.useFakeTimers();
  window.matchMedia = vi.fn(() => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  }));
});
afterEach(() => vi.useRealTimers());

it('cycles the letter highlight and freezes it when paused', () => {
  const { container } = render(<LetterformFooter />);
  const highlighted = () =>
    [...container.querySelectorAll('.puchoo-letter-glyph')].findIndex((item) =>
      item.classList.contains('is-highlighted'),
    );
  expect(highlighted()).toBe(0);
  act(() => vi.advanceTimersByTime(1700));
  expect(highlighted()).toBe(1);
  fireEvent.click(screen.getByRole('button', { name: 'Pause letter animation' }));
  act(() => vi.advanceTimersByTime(3400));
  expect(highlighted()).toBe(1);
  fireEvent.click(screen.getByRole('button', { name: 'Resume letter animation' }));
  act(() => vi.advanceTimersByTime(1700));
  expect(highlighted()).toBe(2);
});

it('responds to hovering a letter and keeps navigation available', () => {
  const { container } = render(<LetterformFooter />);
  const glyph = container.querySelectorAll('.puchoo-letter-glyph')[4];
  fireEvent.pointerEnter(glyph);
  expect(glyph).toHaveClass('is-highlighted');
  act(() => vi.advanceTimersByTime(3400));
  expect(glyph).toHaveClass('is-highlighted');
  expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy');
  fireEvent.pointerLeave(container.querySelector('svg'));
  expect(container.querySelectorAll('.is-highlighted')).toHaveLength(1);
});

it('keeps letterforms static for reduced motion', () => {
  window.matchMedia = vi.fn(() => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
  const { container } = render(<LetterformFooter />);
  expect(screen.queryByRole('button', { name: 'Pause letter animation' })).not.toBeInTheDocument();
  expect(container.querySelector('footer')).toHaveAttribute('data-motion', 'false');
  act(() => vi.advanceTimersByTime(5000));
  expect(container.querySelector('.puchoo-letter-glyph')).toHaveClass('is-highlighted');
});

it('deforms the actual path when a contour dot is dragged and springs back on release', () => {
  const { container } = render(<LetterformFooter />);
  const svg = container.querySelector('.puchoo-letter-wordmark svg');
  const viewBox = svg.getAttribute('viewBox').split(' ').map(Number);
  vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue({
    left: 0,
    top: 0,
    width: viewBox[2],
    height: viewBox[3],
  });
  const hit = svg.querySelector('.puchoo-letter-node-hit');
  const dot = svg.querySelector('.puchoo-letter-node');
  const path = svg.querySelector('.puchoo-letter-fill');
  const original = path.getAttribute('d');
  const x = Number(dot.getAttribute('cx'));
  const y = Number(dot.getAttribute('cy'));
  fireEvent(
    hit,
    new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: x, clientY: y }),
  );
  fireEvent(
    svg,
    new MouseEvent('pointermove', { bubbles: true, clientX: x + 20, clientY: y - 10 }),
  );
  act(() => vi.advanceTimersByTime(800));
  expect(Number(dot.getAttribute('cx'))).toBeGreaterThan(x + 15);
  expect(path.getAttribute('d')).not.toBe(original);
  fireEvent(svg, new MouseEvent('pointerup', { bubbles: true }));
  act(() => vi.advanceTimersByTime(1600));
  expect(Number(dot.getAttribute('cx'))).toBeCloseTo(x, 1);
  expect(Number(dot.getAttribute('cy'))).toBeCloseTo(y, 1);
});
