import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ThemeProvider, applyStoredTheme, useTheme } from '../ThemeContext';

function Probe() {
  const { theme, toggleTheme } = useTheme();
  return <button type="button" onClick={toggleTheme}>Toggle theme: {theme}</button>;
}

describe('theme state', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.documentElement.removeAttribute('data-theme');
  });

  it('defaults to dark and applies it to the document root', () => {
    render(<ThemeProvider><Probe /></ThemeProvider>);

    expect(screen.getByRole('button', { name: 'Toggle theme: dark' })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('restores a saved preference, toggles it, and persists the next value', () => {
    localStorage.setItem('puchoo:theme', 'light');
    render(<ThemeProvider><Probe /></ThemeProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'Toggle theme: light' }));

    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(localStorage.getItem('puchoo:theme')).toBe('dark');
  });

  it('falls back to dark when the saved preference is invalid', () => {
    localStorage.setItem('puchoo:theme', 'sepia');

    render(<ThemeProvider><Probe /></ThemeProvider>);

    expect(screen.getByRole('button', { name: 'Toggle theme: dark' })).toBeInTheDocument();
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('keeps toggling when browser storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage unavailable');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Storage unavailable');
    });

    render(<ThemeProvider><Probe /></ThemeProvider>);
    fireEvent.click(screen.getByRole('button', { name: 'Toggle theme: dark' }));

    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  });

  it('applies the saved preference before React renders', () => {
    localStorage.setItem('puchoo:theme', 'light');

    expect(applyStoredTheme()).toBe('light');
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  });
});
