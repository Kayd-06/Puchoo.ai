import { fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import AskData from '../pages/AskData';
import { clearChatSessions } from '../hooks/useChatState';
import { fetchApi } from '../api/client';

vi.mock('../context/AppContext', () => ({
  useAppContext: () => ({
    activeWorkspaceId: 'sales',
    activeWorkspace: { name: 'Sales' },
    refreshWorkspaces: vi.fn(),
  }),
}));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'ada', workspace_role: 'owner' } }),
}));
vi.mock('../api/client', () => ({ fetchApi: vi.fn(), fetchApiBlob: vi.fn() }));
afterEach(() => {
  clearChatSessions();
  sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

it('restores the question, Hindi answer, and whole table after navigating away and remounting', () => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  Element.prototype.scrollIntoView = vi.fn();
  const saved = {
    question: 'खर्च बताओ',
    questionLanguage: 'hi-IN',
    result: {
      record: {
        question: 'खर्च बताओ',
        columns: ['amount'],
        rows: [{ amount: 0 }, { amount: 200 }],
        row_count: 2,
      },
      presentation: {
        headline: 'आपका खर्च',
        column_labels: { amount: 'राशि' },
        language_code: 'hi-IN',
      },
    },
  };
  for (const [field, value] of Object.entries(saved))
    sessionStorage.setItem(`puchoo:chat:v1:ada:sales:${field}`, JSON.stringify({ value }));
  const page = () => (
    <MemoryRouter initialEntries={['/ask']}>
      <Link to="/settings">Settings tab</Link>
      <Link to="/ask">Ask tab</Link>
      <Routes>
        <Route path="/ask" element={<AskData />} />
        <Route path="/settings" element={<p>Settings page</p>} />
      </Routes>
    </MemoryRouter>
  );
  const first = render(page());
  expect(screen.getByRole('textbox')).toHaveValue(saved.question);
  expect(screen.getByText('आपका खर्च')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Settings tab' }));
  expect(screen.getByText('Settings page')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Ask tab' }));
  expect(screen.getByText('आपका खर्च')).toBeInTheDocument();
  expect(screen.getByRole('cell', { name: '200' })).toBeInTheDocument();
  first.unmount();
  render(page());
  expect(screen.getByRole('textbox')).toHaveValue(saved.question);
  expect(screen.getByText('आपका खर्च')).toBeInTheDocument();
  expect(fetchApi).not.toHaveBeenCalled();
});
