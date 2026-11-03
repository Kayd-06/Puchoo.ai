import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import History from '../pages/History';
import { fetchApi } from '../api/client';
const { navigate } = vi.hoisted(() => ({ navigate: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
vi.mock('../context/AppContext', () => ({
  useAppContext: () => ({ activeWorkspaceId: 'sales', activeWorkspace: { name: 'Sales' } }),
}));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { workspace_role: 'owner' } }),
}));
vi.mock('../api/client', () => ({ fetchApi: vi.fn() }));
afterEach(() => {
  vi.clearAllMocks();
});

it('keeps search, status filters, SQL details, and continuation available in the clean list', async () => {
  fetchApi.mockResolvedValueOnce([
    {
      id: 'one',
      question: 'मेरे खर्चे बताओ',
      sql: 'SELECT amount FROM expenses',
      row_count: 2,
      verification: { status: 'VERIFIED' },
    },
    { id: 'two', question: 'Show sales', sql: 'SELECT total FROM sales', row_count: 1 },
  ]);
  render(<History />);
  const firstTitle = await screen.findByRole('heading', { name: 'मेरे खर्चे बताओ' });
  const first = firstTitle.closest('article');
  const sql = within(first).getByText('View SQL').closest('details');
  fireEvent.click(within(first).getByText('View SQL'));
  expect(sql).toHaveAttribute('open');
  expect(within(sql).getByText('SELECT amount FROM expenses')).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'sales' } });
  expect(screen.queryByRole('heading', { name: 'मेरे खर्चे बताओ' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  fireEvent.click(screen.getByRole('button', { name: /Verified/ }));
  expect(screen.queryByRole('heading', { name: 'Show sales' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Continue chat' }));
  expect(navigate).toHaveBeenCalledWith(
    '/ask',
    expect.objectContaining({ state: expect.any(Object) }),
  );
  expect(screen.getByRole('button', { name: 'Delete chat' })).toBeInTheDocument();
});

it('downloads saved results as CSV without running the query again', async () => {
  fetchApi.mockResolvedValueOnce([
    {
      id: 'saved',
      question: 'Sales report',
      status: 'executed',
      columns: ['total'],
      rows: [{ total: 42 }],
      row_count: 1,
    },
    { id: 'blocked', question: 'Blocked query', status: 'blocked' },
  ]);
  const create = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:export');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(<History />);
  const card = (await screen.findByRole('heading', { name: 'Sales report' })).closest('article');
  expect(within(card).getByRole('button', { name: 'Download PDF' })).toBeInTheDocument();
  fireEvent.click(within(card).getByRole('button', { name: 'Download CSV' }));
  expect(create).toHaveBeenCalledWith(expect.any(Blob));
  expect(click).toHaveBeenCalledOnce();
  expect(fetchApi).toHaveBeenCalledTimes(1);
  const blocked = screen.getByRole('heading', { name: 'Blocked query' }).closest('article');
  expect(within(blocked).queryByRole('button', { name: 'Download CSV' })).not.toBeInTheDocument();
  vi.restoreAllMocks();
});
