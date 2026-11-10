import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { AppProvider } from '../context/AppContext';
import TopBar from '../components/layout/TopBar';
import Sidebar from '../components/layout/Sidebar';
import AskData from '../pages/AskData';
import { fetchApi } from '../api/client';

const sidebarStyles = readFileSync('src/components/layout/sidebar.css', 'utf8');
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
  document.querySelectorAll('[data-sidebar-test-styles]').forEach((style) => style.remove());
});
function mount() {
  return render(
    <MemoryRouter>
      <AppProvider>
        <TopBar />
        <Sidebar />
        <AskData />
      </AppProvider>
    </MemoryRouter>,
  );
}
it.each(
  ['owner', 'editor', 'viewer'].flatMap((role) =>
    [375, 720, 1280].map((width) => ({ role, width })),
  ),
)(
  'switches sidebar sources and isolates drafts for $role at $width px',
  async ({ role, width }) => {
    localStorage.clear();
    sessionStorage.clear();
    auth.user = { id: `selector-${role}-${width}`, tenant_id: 'selector', workspace_role: role };
    vi.stubGlobal('innerWidth', width);
    vi.stubGlobal(
      'matchMedia',
      vi.fn((query) => ({ matches: query === '(max-width: 720px)' ? width <= 720 : true })),
    );
    // jsdom does not evaluate media queries. Apply the real matching mobile rules
    // over the existing hidden-sidebar baseline, then check visibility and layout.
    const stylesheet = document.createElement('style');
    stylesheet.dataset.sidebarTestStyles = '';
    stylesheet.textContent = sidebarStyles;
    document.head.appendChild(stylesheet);
    const mediaRule = [...stylesheet.sheet.cssRules].find(
      (rule) => rule.conditionText === '(max-width: 720px)',
    );
    expect(mediaRule).toBeDefined();
    if (window.matchMedia(mediaRule.conditionText).matches) {
      const mobileStyles = document.createElement('style');
      mobileStyles.dataset.sidebarTestStyles = '';
      mobileStyles.textContent =
        '.app-sidebar-bottom { display: none; }' +
        [...mediaRule.cssRules].map((rule) => rule.cssText).join('\n');
      document.head.appendChild(mobileStyles);
    }
    vi.stubGlobal(
      'EventSource',
      class {
        addEventListener() {}
        close() {}
      },
    );
    const sources = Array.from({ length: 20 }, (_, i) => ({
      id: `${role}-${width}-${i}`,
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
    expect(screen.queryByRole('combobox', { name: 'Active data source' })).not.toBeInTheDocument();
    const select = await screen.findByRole('button', { name: /select active data source/i });
    await waitFor(() => expect(select).toHaveTextContent(sources[0].name.trim()));
    expect(select).toBeVisible();
    expect(select).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(select);
    expect(select).toHaveAttribute('aria-expanded', 'true');
    const menu = screen.getByRole('listbox', { name: 'Active data sources' });
    expect(menu).toBeVisible();
    expect(screen.getAllByRole('option')).toHaveLength(20);
    if (width <= 720) {
      expect(menu).toHaveStyle({ position: 'static', overflowY: 'auto' });
      expect(menu.style.maxHeight || getComputedStyle(menu).maxHeight).not.toBe('');
      expect(screen.getAllByRole('option')[19]).toHaveStyle({ minHeight: '44px' });
    }
    const target = width <= 720 ? 19 : 1;
    if (role !== 'viewer')
      fireEvent.change(screen.getByRole('textbox'), {
        target: { value: 'PRIVATE SOURCE A FILTER' },
      });
    fireEvent.click(screen.getByRole('option', { name: sources[target].name.trim() }));
    expect(select).toHaveTextContent(sources[target].name.trim());
    expect(select).toHaveAttribute('aria-expanded', 'false');
    expect(localStorage.getItem('pucho_active_workspace')).toBe(`${role}-${width}-${target}`);
    if (role === 'viewer') {
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
      expect(screen.getByRole('link', { name: /open history/i })).toBeInTheDocument();
      expect(fetchApi.mock.calls.some(([path]) => path.endsWith('/generate'))).toBe(false);
    } else {
      expect(screen.getByRole('textbox')).toHaveValue('');
      expect(localStorage.getItem('pucho_active_workspace')).toBe(`${role}-${width}-${target}`);
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Source B total' } });
      fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
      await waitFor(() =>
        expect(fetchApi).toHaveBeenCalledWith(
          `/query/${role}-${width}-${target}/generate`,
          expect.anything(),
        ),
      );
      const body = fetchApi.mock.calls.find(([path]) => path.endsWith('/generate'))[1].body;
      expect(body).not.toContain('PRIVATE SOURCE A');
    }
    view.unmount();
    mount();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /select active data source/i })).toHaveTextContent(
        sources[target].name.trim(),
      ),
    );
  },
);
