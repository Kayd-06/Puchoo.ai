import { expect, it } from 'vitest';

import { queryUniversePalette } from '../AskData';

it('uses visible black moving particles against the light app theme', () => {
  expect(queryUniversePalette('light')).toMatchObject({
    composite: 'source-over',
    motion: 1.45,
    dust: '16, 28, 35',
    stream: '29, 50, 64',
    star: '15, 28, 36',
  });
  expect(queryUniversePalette('dark').composite).toBe('lighter');
});

it('shows the advisory scope warning as plain text and hides it when absent', async () => {
  const { render, screen } = await import('@testing-library/react');
  const { ScopeWarning } = await import('../AskData');
  const { container, rerender } = render(<ScopeWarning message="<b>Check the SQL</b>" />);
  expect(screen.getByRole('status')).toHaveTextContent('<b>Check the SQL</b>');
  expect(container.querySelector('b')).toBeNull();
  rerender(<ScopeWarning message={undefined} />);
  expect(screen.queryByRole('status')).toBeNull();
});
