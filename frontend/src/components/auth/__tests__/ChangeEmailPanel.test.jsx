import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ChangeEmailPanel from '../ChangeEmailPanel';

vi.mock('../../../context/AuthContext', () => ({
  useAuth: () => ({
    user: { email: 'owner@example.com' },
    requestEmailChange: vi.fn(),
    verifyEmailChange: vi.fn(),
  }),
}));
afterEach(() => {
  document.documentElement.removeAttribute('data-theme');
});

it('opens the email dialog outside transformed page cards without sending a request', () => {
  document.documentElement.dataset.theme = 'light';
  const { container } = render(
    <div style={{ transform: 'translateY(0)' }}>
      <ChangeEmailPanel />
    </div>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Change email' }));
  const dialog = screen.getByRole('dialog', { name: 'Change email address' });
  expect(dialog.parentElement).toBe(document.body);
  expect(container).not.toContainElement(dialog);
  expect(screen.getByLabelText('New email address')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('keeps keyboard focus in the dialog and restores it on Escape', () => {
  render(<ChangeEmailPanel />);
  const opener = screen.getByRole('button', { name: 'Change email' });
  opener.focus();
  fireEvent.click(opener);
  expect(screen.getByLabelText('New email address')).toHaveFocus();
  const dialog = screen.getByRole('dialog');
  const controls = dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href]');
  controls[controls.length - 1].focus();
  fireEvent.keyDown(document, { key: 'Tab' });
  expect(controls[0]).toHaveFocus();
  fireEvent.keyDown(document, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
  expect(document.body.style.overflow).not.toBe('hidden');
});
