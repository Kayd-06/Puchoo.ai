import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import Landing from '../Landing';

beforeEach(() => {
  window.matchMedia = vi.fn(() => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
});

it('explains speech and translation in a dedicated Gnani section', () => {
  render(<Landing />);
  expect(screen.getByRole('region', { name: 'Your voice. Powered by Gnani.' })).toBeInTheDocument();
  expect(screen.getByText(/Sarvam AI translates/)).toBeInTheDocument();
});

it('lets visitors pause the guided demo and select a step', () => {
  render(<Landing />);
  fireEvent.click(screen.getByRole('button', { name: 'Pause guided demo' }));
  expect(screen.getByRole('button', { name: 'Resume guided demo' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /02 Review/ }));
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
