import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import TopBar from '../layout/TopBar';
import { fetchApi } from '../../api/client';
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('../../context/AppContext', () => ({
  useAppContext: () => ({ activeWorkspace: { name: 'School' } }),
}));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ user: { full_name: 'User' }, logout: vi.fn() }),
}));
vi.mock('../../context/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn() }),
}));
vi.mock('../ThemeToggle', () => ({ default: () => null }));
vi.mock('../../api/client', () => ({ fetchApi: vi.fn() }));
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});
async function openNotifications() {
  vi.stubGlobal(
    'EventSource',
    class {
      addEventListener() {}
      close() {}
    },
  );
  fetchApi.mockResolvedValueOnce({
    items: [
      {
        id: 'one',
        title: 'Query ready',
        body: 'Your results',
        read_at: null,
        created_at: new Date().toISOString(),
      },
    ],
    unread_count: 1,
  });
  render(<TopBar />);
  await screen.findByLabelText('1 unread notifications');
  fireEvent.click(screen.getByRole('button', { name: 'Notifications' }));
}
it('deletes a notification and clears its unread dot after server success', async () => {
  await openNotifications();
  fetchApi.mockResolvedValueOnce({ ok: true });
  fireEvent.click(screen.getByRole('button', { name: 'Delete notification: Query ready' }));
  await waitFor(() => expect(screen.queryByText('Query ready')).not.toBeInTheDocument());
  expect(fetchApi).toHaveBeenLastCalledWith('/notifications/one', { method: 'DELETE' });
  expect(screen.queryByLabelText('1 unread notifications')).not.toBeInTheDocument();
});
it('keeps the notification and unread state when deletion fails', async () => {
  await openNotifications();
  fetchApi.mockRejectedValueOnce(new Error('offline'));
  fireEvent.click(screen.getByRole('button', { name: 'Delete notification: Query ready' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not delete');
  expect(screen.getByText('Query ready')).toBeInTheDocument();
  expect(screen.getByLabelText('1 unread notifications')).toBeInTheDocument();
});
