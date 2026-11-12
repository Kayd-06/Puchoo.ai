import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import MemberRoleDropdown from '../MemberRoleDropdown';
afterEach(() => vi.restoreAllMocks());
it('keeps the role menu inside a narrow, short viewport', () => {
  vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(320);
  vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(200);
  render(
    <MemberRoleDropdown
      value="editor"
      options={['admin', 'editor', 'viewer']}
      label="Member role"
      onChange={vi.fn()}
    />,
  );
  const trigger = screen.getByRole('button', { name: 'Member role' });
  vi.spyOn(trigger, 'getBoundingClientRect').mockReturnValue({
    left: 280,
    top: 170,
    bottom: 195,
    width: 110,
  });
  fireEvent.click(trigger);
  const menu = screen.getByRole('listbox', { name: 'Member role' });
  const left = parseFloat(menu.style.left);
  const top = parseFloat(menu.style.top);
  const width = parseFloat(menu.style.width);
  expect(left).toBeGreaterThanOrEqual(8);
  expect(left + width).toBeLessThanOrEqual(312);
  expect(top).toBeGreaterThanOrEqual(8);
  expect(top + 148).toBeLessThanOrEqual(192);
});

it('allows scrolling the role list but closes it when the page scrolls', () => {
  render(
    <MemberRoleDropdown
      value="editor"
      options={['admin', 'editor', 'viewer']}
      label="Member role"
      onChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Member role' }));
  fireEvent.scroll(screen.getByRole('listbox'));
  expect(screen.getByRole('listbox')).toBeInTheDocument();
  fireEvent.scroll(window);
  expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
});
