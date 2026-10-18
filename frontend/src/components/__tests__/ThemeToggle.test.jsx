import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AuthShell from '../auth/AuthShell';
import { ThemeProvider } from '../../context/ThemeContext';
import ThemeToggle from '../ThemeToggle';
import Landing from '../../pages/Landing';

function renderWithTheme(component) {
  return render(
    <MemoryRouter>
      <ThemeProvider>{component}</ThemeProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('ThemeToggle', () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  it('announces the next theme and toggles the root theme when activated', () => {
    renderWithTheme(<ThemeToggle />);

    fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));

    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
    expect(screen.getByRole('button', { name: 'Switch to dark mode' })).toBeInTheDocument();
  });

  it('is not available in the authentication shell', () => {
    renderWithTheme(<AuthShell title="Log in" subtitle="Welcome" footer="New here?" />);

    expect(screen.queryByRole('button', { name: 'Switch to light mode' })).not.toBeInTheDocument();
  });

  it('is not available on the public landing page', () => {
    renderWithTheme(<Landing />);

    expect(screen.queryByRole('button', { name: 'Switch to light mode' })).not.toBeInTheDocument();
  });
});
