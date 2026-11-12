import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AppShell from './AppShell';

const state = vi.hoisted(() => ({ setActiveWorkspaceId: vi.fn() }));
vi.mock('../../context/AppContext', () => ({
  useAppContext: () => ({
    activeWorkspaceId: 'a',
    activeWorkspace: { id: 'a', name: 'Data A' },
    workspaces: [
      { id: 'a', name: 'Data A' },
      { id: 'b', name: 'Data B' },
    ],
    setActiveWorkspaceId: state.setActiveWorkspaceId,
  }),
}));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: {
      role: 'owner',
      capabilities: {
        query_workspace: true,
        manage_data_sources: true,
        view_history: true,
        manage_account: true,
      },
    },
  }),
}));
vi.mock('./TopBar', () => ({
  default: ({ onOpenNavigation }) => (
    <header>
      {onOpenNavigation && <button onClick={onOpenNavigation}>Open workspace menu</button>}
    </header>
  ),
}));
let mediaChanged;
const dialogMethods = Object.fromEntries(
  ['showModal', 'close'].map((name) => [
    name,
    Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name),
  ]),
);
beforeEach(() => {
  state.setActiveWorkspaceId.mockClear();
  window.matchMedia = vi.fn(() => ({
    matches: true,
    addEventListener: (_event, callback) => {
      mediaChanged = callback;
    },
    removeEventListener() {},
  }));
  // jsdom does not implement the browser's native modal dialog methods.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value: function () {
      this.setAttribute('open', '');
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value: function () {
      this.removeAttribute('open');
      this.dispatchEvent(new Event('close'));
    },
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  for (const [name, descriptor] of Object.entries(dialogMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
  document.body.style.overflow = '';
});
function mount() {
  return render(
    <MemoryRouter initialEntries={['/ask']}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="ask" element={<h1>Ask</h1>} />
          <Route path="history" element={<h1>History</h1>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

it('keeps source switching reachable in the compact navigation drawer', () => {
  mount();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  const opener = screen.getByRole('button', { name: 'Open workspace menu' });
  opener.focus();
  fireEvent.click(opener);
  const drawer = screen.getByRole('dialog', { name: 'Workspace menu' });
  expect(document.body.style.overflow).toBe('hidden');
  fireEvent.click(within(drawer).getByRole('button', { name: 'Select active data source' }));
  fireEvent.click(within(drawer).getByRole('option', { name: 'Data B' }));
  expect(state.setActiveWorkspaceId).toHaveBeenCalledWith('b');
  expect(drawer).not.toHaveAttribute('open');
  expect(document.body.style.overflow).toBe('');
  expect(opener).toHaveFocus();
});
it('closes after navigating without leaving page scrolling locked', () => {
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'Open workspace menu' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('link', { name: /History/ }));
  expect(screen.getByRole('heading', { name: 'History' })).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(document.body.style.overflow).toBe('');
});
it('restores desktop navigation and scrolling when rotating to a wide viewport', () => {
  mount();
  fireEvent.click(screen.getByRole('button', { name: 'Open workspace menu' }));
  act(() => mediaChanged({ matches: false }));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Open workspace menu' })).not.toBeInTheDocument();
  expect(screen.getByRole('complementary', { name: 'Workspace navigation' })).toBeInTheDocument();
  expect(document.body.style.overflow).toBe('');
});
it('restores an existing scroll style after closing or unmounting', () => {
  document.body.style.overflow = 'auto';
  const view = mount();
  fireEvent.click(screen.getByRole('button', { name: 'Open workspace menu' }));
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace menu' }));
  expect(document.body.style.overflow).toBe('auto');
  fireEvent.click(screen.getByRole('button', { name: 'Open workspace menu' }));
  view.unmount();
  expect(document.body.style.overflow).toBe('auto');
});
