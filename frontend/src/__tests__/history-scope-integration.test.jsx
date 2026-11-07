import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { Link, MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AskData from '../pages/AskData';
import History from '../pages/History';
import { fetchApi } from '../api/client';
import { chatScope, scopeKey, clearChatSessions, makeContinuation } from '../hooks/useChatState';

const fixture = vi.hoisted(() => ({ workspace: 'a', user: null, records: {} }));
vi.mock('../context/AppContext', () => ({
  useAppContext: () => ({
    activeWorkspaceId: fixture.workspace,
    activeWorkspace: { name: fixture.workspace },
    refreshWorkspaces: vi.fn(),
  }),
}));
vi.mock('../context/AuthContext', () => ({ useAuth: () => ({ user: fixture.user }) }));
vi.mock('../api/client', () => ({ fetchApi: vi.fn(), fetchApiBlob: vi.fn() }));
let sequence = 0;
const record = (id = 'old', question = 'original question') => ({
  id,
  question,
  sql: 'SELECT amount FROM fees',
  columns: ['amount'],
  rows: [{ amount: 20 }],
  row_count: 1,
  created_at: '2026-11-07T00:00:00Z',
  verification_status: 'VERIFIED',
});
const result = (id = 'old') => ({ record: record(id), presentation: { headline: `answer-${id}` } });
const proposal = { pending_id: 'pending', sql_hash: 'hash' };
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};
const scope = (workspace = fixture.workspace) => chatScope(fixture.user, workspace);
function seed(workspace, id = 'old') {
  sessionStorage.setItem(
    `puchoo:chat:v2:${scopeKey(scope(workspace))}`,
    JSON.stringify({ version: '', values: { question: 'cached draft', result: result(id) } }),
  );
}
function Controls({ refresh }) {
  const navigate = useNavigate();
  return (
    <nav>
      <Link to="/ask">Ask tab</Link>
      <Link to="/history">History tab</Link>
      <Link to="/other">Other tab</Link>
      <button
        onClick={() => {
          fixture.workspace = fixture.workspace === 'a' ? 'b' : 'a';
          refresh();
        }}
      >
        Switch workspace
      </button>
      <button onClick={() => navigate(-1)}>Back</button>
    </nav>
  );
}
function App({ entry = '/ask', state }) {
  const [, setVersion] = useState(0);
  return (
    <MemoryRouter initialEntries={[{ pathname: entry, state }]}>
      <Controls refresh={() => setVersion((v) => v + 1)} />
      <Routes>
        <Route path="/ask" element={<AskData />} />
        <Route path="/history" element={<History />} />
        <Route path="/other" element={<p>Other page</p>} />
      </Routes>
    </MemoryRouter>
  );
}
function ask(text = 'follow up') {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: text } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter', code: 'Enter' });
}
function defaultApi(path, options = {}) {
  if (options.method === 'DELETE') return Promise.resolve(null);
  if (path.startsWith('/history/'))
    return Promise.resolve(fixture.records[path.split('/')[2]] || []);
  if (path.endsWith('/generate')) return Promise.resolve(proposal);
  if (path.endsWith('/approve')) return Promise.resolve(result('new'));
  throw new Error(`Unexpected endpoint: ${path}`);
}
beforeEach(() => {
  fixture.workspace = 'a';
  fixture.user = {
    id: `browser-${++sequence}`,
    tenant_id: `browser-tenant-${sequence}`,
    role: 'owner',
    workspace_role: 'owner',
  };
  fixture.records = { a: [record()], b: [record('b', 'workspace B question')] };
  fetchApi.mockImplementation(defaultApi);
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  clearChatSessions();
  sessionStorage.clear();
  localStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

it('continues on its original dataset, autoexecutes on Enter, and never carries A context to B', async () => {
  render(<App entry="/history" />);
  fireEvent.click(await screen.findByRole('button', { name: /Continue chat/ }));
  ask();
  await screen.findByText('answer-new');
  const first = fetchApi.mock.calls.find(([path]) => path === '/query/a/generate');
  expect(JSON.parse(first[1].body).question).toBe(
    'Previous question: original question\n\nFollow-up question: follow up',
  );
  expect(fetchApi.mock.calls.some(([path]) => path.endsWith('/approve'))).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Switch workspace' }));
  expect(screen.queryByText('answer-new')).not.toBeInTheDocument();
  ask('B only');
  await waitFor(() =>
    expect(fetchApi.mock.calls.some(([path]) => path === '/query/b/generate')).toBe(true),
  );
  expect(
    JSON.parse(fetchApi.mock.calls.find(([path]) => path === '/query/b/generate')[1].body).question,
  ).toBe('B only');
});

it('rejects A route continuation on B and does not resurrect it through navigation back', async () => {
  const continuation = makeContinuation(scope('a'), record());
  fixture.workspace = 'b';
  render(<App state={{ continuation }} />);
  ask('B only');
  await screen.findByText('answer-new');
  expect(
    JSON.parse(fetchApi.mock.calls.find(([path]) => path.endsWith('/generate'))[1].body).question,
  ).toBe('B only');
  fireEvent.click(screen.getByRole('link', { name: 'Other tab' }));
  fireEvent.click(screen.getByRole('button', { name: 'Back' }));
  expect(screen.queryByText('original question')).not.toBeInTheDocument();
});

it.each(['single-204', 'single-202', 'all-204', 'all-202'])(
  'committed %s deletion evicts the scoped cached answer on navigation and remount',
  async (mode) => {
    seed('a');
    seed('b', 'keep-b');
    fetchApi.mockImplementation((path, options) =>
      options?.method === 'DELETE'
        ? Promise.resolve(mode.endsWith('202') ? { status: 'cleanup_pending' } : null)
        : defaultApi(path, options),
    );
    const view = render(<App entry="/history" />);
    await screen.findByRole('button', { name: /Continue chat/ });
    fireEvent.click(
      screen.getByRole('button', {
        name: mode.startsWith('all') ? /Clear history/ : /Delete chat/,
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Continue chat/ })).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole('link', { name: 'Ask tab' }));
    expect(screen.queryByText('answer-old')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox')).toHaveValue('');
    fireEvent.click(screen.getByRole('button', { name: 'Switch workspace' }));
    expect(screen.getByText('answer-keep-b')).toBeInTheDocument();
    view.unmount();
    fixture.workspace = 'a';
    render(<App />);
    expect(screen.queryByText('answer-old')).not.toBeInTheDocument();
  },
);

it('failed deletion preserves the cached answer and explains the failure', async () => {
  seed('a');
  fetchApi.mockImplementation((path, options) =>
    options?.method === 'DELETE'
      ? Promise.reject(new Error('Deletion not committed'))
      : defaultApi(path, options),
  );
  render(<App entry="/history" />);
  fireEvent.click(await screen.findByRole('button', { name: /Delete chat/ }));
  await screen.findByText('Deletion not committed');
  expect(screen.getByRole('button', { name: /Continue chat/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('link', { name: 'Ask tab' }));
  expect(screen.getByText('answer-old')).toBeInTheDocument();
});

it.each(['generate', 'approve'])(
  'ignores a late %s response after logical deletion, including after remount',
  async (stage) => {
    const pending = deferred();
    fetchApi.mockImplementation((path, options) =>
      path.endsWith(`/${stage}`) ? pending.promise : defaultApi(path, options),
    );
    render(<App />);
    ask('slow question');
    await waitFor(() =>
      expect(fetchApi.mock.calls.some(([path]) => path.endsWith(`/${stage}`))).toBe(true),
    );
    fireEvent.click(screen.getByRole('link', { name: 'History tab' }));
    fireEvent.click(await screen.findByRole('button', { name: /Clear history/ }));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /Continue chat/ })).not.toBeInTheDocument(),
    );
    await act(async () => pending.resolve(stage === 'generate' ? proposal : result('late')));
    fireEvent.click(screen.getByRole('link', { name: 'Ask tab' }));
    expect(screen.queryByText('answer-late')).not.toBeInTheDocument();
    if (stage === 'generate')
      expect(fetchApi.mock.calls.some(([path]) => path.endsWith('/approve'))).toBe(false);
    expect(screen.getByRole('textbox')).toHaveValue('');
  },
);

it('a newly chosen conversation rejects the prior same-workspace query response', async () => {
  const pending = deferred();
  fetchApi.mockImplementation((path, options) =>
    path.endsWith('/approve') ? pending.promise : defaultApi(path, options),
  );
  render(<App />);
  ask('previous slow query');
  await waitFor(() =>
    expect(fetchApi.mock.calls.some(([path]) => path.endsWith('/approve'))).toBe(true),
  );
  fireEvent.click(screen.getByRole('link', { name: 'History tab' }));
  fireEvent.click(await screen.findByRole('button', { name: /Continue chat/ }));
  await act(async () => pending.resolve(result('unrelated-late')));
  expect(screen.queryByText('answer-unrelated-late')).not.toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('');
});

it('filters a delayed history fetch after a cross-tab committed clear', async () => {
  const pending = deferred();
  fetchApi.mockImplementation(() => pending.promise);
  render(<App entry="/history" />);
  const journal = `puchoo:history:v1:${scope().tenantId}:a:clear`;
  act(() => {
    localStorage.setItem(journal, 'remote-clear');
    window.dispatchEvent(new StorageEvent('storage', { key: journal, newValue: 'remote-clear' }));
  });
  await act(async () => pending.resolve([record()]));
  expect(screen.queryByRole('button', { name: /Continue chat/ })).not.toBeInTheDocument();
});

it('a delayed A deletion cannot clear B history after workspace switching', async () => {
  const pending = deferred();
  fetchApi.mockImplementation((path, options) =>
    options?.method === 'DELETE' ? pending.promise : defaultApi(path, options),
  );
  render(<App entry="/history" />);
  fireEvent.click(await screen.findByRole('button', { name: /Delete chat/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Switch workspace' }));
  await screen.findByText('workspace B question');
  await act(async () => pending.resolve({ status: 'cleanup_pending' }));
  expect(screen.getByText('workspace B question')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Continue chat/ })).toBeInTheDocument();
});

it('a cross-tab single deletion clears the mounted answer and permits a fresh question', async () => {
  seed('a');
  render(<App />);
  expect(screen.getByText('answer-old')).toBeInTheDocument();
  const journal = `puchoo:history:v1:${scope().tenantId}:a:record:old`;
  act(() => {
    localStorage.setItem(journal, 'remote-delete');
    window.dispatchEvent(new StorageEvent('storage', { key: journal, newValue: 'remote-delete' }));
  });
  expect(screen.queryByText('answer-old')).not.toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('');
  ask('a new question');
  await screen.findByText('answer-new');
});

it('a changed account or role never renders the previous identity snapshot', () => {
  seed('a');
  const view = render(<App />);
  expect(screen.getByText('answer-old')).toBeInTheDocument();
  fixture.user = { ...fixture.user, role: 'viewer', workspace_role: 'viewer' };
  view.rerender(<App />);
  expect(screen.queryByText('answer-old')).not.toBeInTheDocument();
  fixture.user = { ...fixture.user, id: 'another-browser-user' };
  view.rerender(<App />);
  expect(screen.queryByText('answer-old')).not.toBeInTheDocument();
});
