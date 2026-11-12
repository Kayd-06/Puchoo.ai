import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Landing from '../Landing';

beforeEach(() => {
  window.matchMedia = vi.fn(() => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
});

afterEach(() => vi.useRealTimers());

it('explains speech and translation in a dedicated Gnani section', () => {
  render(<Landing />);
  expect(screen.getByRole('region', { name: 'Your voice. Powered by Gnani.' })).toBeInTheDocument();
  expect(screen.getByText(/Sarvam AI translates/)).toBeInTheDocument();
});

it('lets visitors pause the guided demo and select a step', () => {
  render(<Landing />);
  fireEvent.click(screen.getByRole('button', { name: 'Pause guided demo' }));
  expect(screen.getByRole('button', { name: 'Resume guided demo' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /02 Run/ }));
  expect(screen.getByText(/SELECT department/)).toBeInTheDocument();
});

it('closes navigation with Escape and offers a direct Gnani link', () => {
  render(<Landing />);
  const toggle = screen.getByRole('button', { name: 'Open navigation' });
  fireEvent.click(toggle);
  expect(
    within(screen.getByRole('navigation', { name: 'Landing navigation' })).getByRole('link', {
      name: 'Gnani voice',
    }),
  ).toHaveAttribute('href', '#gnani');
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
});

it('offers segmented section navigation and updates the selected item', () => {
  render(<Landing />);
  const nav = within(screen.getByRole('navigation', { name: 'Primary navigation' }));
  expect(nav.getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'location');
  const gnani = nav.getByRole('link', { name: 'Gnani' });
  expect(gnani).toHaveAttribute('href', '#gnani');
  fireEvent.click(gnani);
  expect(gnani).toHaveAttribute('aria-current', 'location');
  expect(nav.getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current');
});

it('stops and restarts walkthrough autoplay on reduced-motion changes and cleans up', () => {
  vi.useFakeTimers();
  const listeners = new Set();
  const preference = {
    matches: false,
    addEventListener: vi.fn((_event, listener) => listeners.add(listener)),
    removeEventListener: vi.fn((_event, listener) => listeners.delete(listener)),
  };
  window.matchMedia = vi.fn(() => preference);
  const changePreference = (matches) => {
    act(() => {
      preference.matches = matches;
      listeners.forEach((listener) => listener({ matches }));
    });
  };
  const view = render(<Landing />);
  const step = (name) => screen.getByRole('button', { name });
  expect(step(/01 Ask/)).toHaveAttribute('aria-pressed', 'true');
  act(() => vi.advanceTimersByTime(4300));
  expect(step(/02 Run/)).toHaveAttribute('aria-pressed', 'true');

  changePreference(true);
  act(() => vi.advanceTimersByTime(4300));
  expect(step(/02 Run/)).toHaveAttribute('aria-pressed', 'true');

  changePreference(false);
  act(() => vi.advanceTimersByTime(4300));
  expect(step(/03 Answer/)).toHaveAttribute('aria-pressed', 'true');

  view.unmount();
  expect(listeners.size).toBe(0);
  expect(preference.removeEventListener).toHaveBeenCalledTimes(
    preference.addEventListener.mock.calls.length,
  );
  expect(vi.getTimerCount()).toBe(0);
});

it('dismisses mobile navigation outside the header and restores desktop state on resize', () => {
  render(<Landing />);
  const toggle = screen.getByRole('button', { name: 'Open navigation' });
  fireEvent.click(toggle);
  fireEvent.pointerDown(document.body);
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(toggle);
  fireEvent(window, new Event('resize'));
  expect(toggle).toHaveAttribute('aria-expanded', 'false');
});
