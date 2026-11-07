import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { AppProvider } from '../context/AppContext';
import TopBar from '../components/layout/TopBar';
import AskData from '../pages/AskData';
import { fetchApi } from '../api/client';
const auth = vi.hoisted(() => ({
  user: { id: 'selector', tenant_id: 'selector', workspace_role: 'owner' },
  logout: vi.fn(),
}));
vi.mock('../context/AuthContext', () => ({ useAuth: () => auth }));
vi.mock('../context/ThemeContext', () => ({
  useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn() }),
}));
vi.mock('../components/ThemeToggle', () => ({ default: () => null }));
vi.mock('../api/client', () => ({ fetchApi: vi.fn(), fetchApiBlob: vi.fn() }));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
function mount() {
  return render(
    <MemoryRouter>
      <AppProvider>
        <TopBar />
        <AskData />
      </AppProvider>
    </MemoryRouter>,
  );
}
it.each(['owner', 'editor', 'viewer'])(
  'switches existing sources and isolates drafts for %s with real AppProvider',
  async (role) => {
    localStorage.clear();
    sessionStorage.clear();
    auth.user = { id: `selector-${role}`, tenant_id: 'selector', workspace_role: role };
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
    vi.stubGlobal(
      'EventSource',
      class {
        addEventListener() {}
        close() {}
      },
    );
    const sources = Array.from({ length: 20 }, (_, i) => ({
      id: `${role}-${i}`,
      name: `Source ${i} ${'long name '.repeat(8)}`,
    }));
    fetchApi.mockImplementation(async (path) => {
      if (path === '/workspaces/') return sources;
      if (path.startsWith('/notifications')) return { items: [], unread_count: 0 };
      if (path.endsWith('/generate'))
        return { status: 'clarification_required', message: 'Pick metric', suggestions: [] };
      return {};
    });
    const view = mount();
    const select = await screen.findByRole('combobox', { name: 'Active data source' });
    await waitFor(() => expect(select).toHaveValue(`${role}-0`));
    expect(select.options).toHaveLength(21);
    if (role !== 'viewer')
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'PRIVATE SOURCE A FILTER' },
      });
    fireEvent.change(select, { target: { value: `${role}-1` } });
    expect(select).toHaveValue(`${role}-1`);
    expect(localStorage.getItem('pucho_active_workspace')).toBe(`${role}-1`);
    if (role === 'viewer') {
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: /open history/i })).toBeInTheDocument();
      expect(fetchApi.mock.calls.some(([path]) => path.endsWith('/generate'))).toBe(false);
    } else {
      expect(screen.getByRole('textbox')).toHaveValue('');
      expect(localStorage.getItem('pucho_active_workspace')).toBe(`${role}-1`);
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Source B total' } });
      fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
      await waitFor(() =>
        expect(fetchApi).toHaveBeenCalledWith(`/query/${role}-1/generate`, expect.anything()),
      );
      const body = fetchApi.mock.calls.find(([path]) => path.endsWith('/generate'))[1].body;
      expect(body).not.toContain('PRIVATE SOURCE A');
    }
    view.unmount();
    mount();
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: 'Active data source' })).toHaveValue(`${role}-1`),
    );
  },
);
