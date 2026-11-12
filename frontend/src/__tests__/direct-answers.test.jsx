import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
const page = () => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  Element.prototype.scrollIntoView = vi.fn();
  return render(
    <MemoryRouter>
      <AskData />
    </MemoryRouter>,
  );
};
it('shows a missing-data answer directly without trying to execute a SQL proposal', async () => {
  fetchApi.mockResolvedValue({
    status: 'answer_unavailable',
    message: 'Campaign profit cannot be determined because campaign attribution is not recorded.',
    limitations: ['Campaign dates and costs are missing.'],
    suggestions: [],
  });
  page();
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Did the campaign increase profit?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
  await waitFor(() => expect(screen.getByRole('region', { name: 'Answer' })).toBeInTheDocument());
  expect(screen.getByText(/Campaign profit cannot be determined/)).toBeInTheDocument();
  expect(screen.queryByText('Choose one detail to continue')).not.toBeInTheDocument();
  expect(fetchApi).toHaveBeenCalledTimes(1);
  expect(fetchApi.mock.calls[0][0]).toMatch(/\/generate$/);
});
it('displays partial-answer limitations prominently alongside returned results', async () => {
  fetchApi.mockReset();
  fetchApi
    .mockResolvedValueOnce({
      status: 'pending_approval',
      pending_id: 'pending-partial',
      sql_hash: 'hash',
    })
    .mockResolvedValueOnce({
      record: {
        id: 'partial',
        question: 'Compare profit',
        columns: ['revenue'],
        rows: [{ revenue: 100 }],
        answer_status: 'partial',
        limitations: ['Refunds and delivery costs are not recorded.'],
      },
      presentation: { headline: 'Revenue: 100' },
    });
  page();
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Compare profit including refunds' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
  await waitFor(() =>
    expect(screen.getByRole('status', { name: 'Answer limitations' })).toHaveTextContent(
      'Partial answer',
    ),
  );
  expect(screen.getByText('Refunds and delivery costs are not recorded.')).toBeInTheDocument();
});
it('jumps to the chart and does not scroll back when chart settings change', async () => {
  const scroll = vi.fn();
  fetchApi
    .mockResolvedValueOnce({ status: 'pending_approval', pending_id: 'p', sql_hash: 'h' })
    .mockResolvedValueOnce({
      record: {
        id: 'scroll-result',
        question: 'Sales by region',
        columns: ['region', 'sales'],
        rows: [
          { region: 'North', sales: 10 },
          { region: 'South', sales: 20 },
        ],
      },
      presentation: { headline: 'Sales by region' },
    });
  page();
  Element.prototype.scrollIntoView = scroll;
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Sales by region' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
  const jump = await screen.findByRole('button', { name: 'Jump to chart' });
  await new Promise((resolve) => setTimeout(resolve, 150));
  scroll.mockClear();
  fireEvent.click(jump);
  expect(scroll).toHaveBeenCalledTimes(1);
  const color = await screen.findByRole('button', { name: 'Chart color Teal' });
  fireEvent.click(color);
  await new Promise((resolve) => setTimeout(resolve, 150));
  expect(scroll).toHaveBeenCalledTimes(1);
});
it('runs independent questions separately and lets the user switch answers', async () => {
  fetchApi.mockReset();
  fetchApi
    .mockResolvedValueOnce({ status: 'pending_approval', pending_id: 'a', sql_hash: 'a' })
    .mockResolvedValueOnce({
      record: {
        id: 'a',
        question: 'Which regions?',
        columns: ['region'],
        rows: [{ region: 'North' }],
      },
      presentation: { headline: 'First answer' },
    })
    .mockResolvedValueOnce({ status: 'answer_unavailable', message: 'Expense data is missing.' });
  page();
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Which regions? What expenses?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
  expect(await screen.findByText('First answer')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Analysis 2/ }));
  expect(screen.getByText('Expense data is missing.')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Analysis 1/ }));
  expect(screen.getByText('First answer')).toBeInTheDocument();
  expect(fetchApi).toHaveBeenCalledTimes(3);
});
it('answers a clarification inside a multi-question run without losing the other answers', async () => {
  fetchApi.mockReset();
  fetchApi
    .mockResolvedValueOnce({ status: 'pending_approval', pending_id: 'a', sql_hash: 'a' })
    .mockResolvedValueOnce({
      record: { id: 'a', question: 'Which regions?', columns: ['region'], rows: [{ region: 'N' }] },
      presentation: { headline: 'First answer' },
    })
    .mockResolvedValueOnce({
      status: 'clarification_required',
      reason: 'ambiguous_metric',
      message: 'Which metric should determine the ranking?',
      suggestions: ['Rank by total revenue'],
      clarifications: [],
    })
    .mockResolvedValueOnce({ status: 'pending_approval', pending_id: 'b', sql_hash: 'b' })
    .mockResolvedValueOnce({
      record: { id: 'b', question: 'Best customers?', columns: ['name'], rows: [{ name: 'Ada' }] },
      presentation: { headline: 'Second answer' },
    });
  page();
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'Which regions?Show the best customers?' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
  expect(await screen.findByText('First answer')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Analysis 2/ }));
  fireEvent.click(screen.getByRole('button', { name: 'Rank by total revenue' }));
  expect(await screen.findByText('Second answer')).toBeInTheDocument();
  const rerun = JSON.parse(fetchApi.mock.calls[3][1].body);
  expect(rerun).toMatchObject({
    question: 'Show the best customers?',
    clarifications: [{ reason: 'ambiguous_metric', choice: 'Rank by total revenue' }],
  });
  expect(fetchApi).toHaveBeenCalledTimes(5);
  fireEvent.click(screen.getByRole('button', { name: /Analysis 1/ }));
  expect(screen.getByText('First answer')).toBeInTheDocument();
});
it.each([401, 403, 503])(
  'stops a multi-question run and shows the %s error through the normal error path',
  async (status) => {
    fetchApi.mockReset();
    const failure = Object.assign(new Error('The SQL model service is unavailable.'), { status });
    fetchApi.mockRejectedValueOnce(failure);
    page();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Which regions? What expenses?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
    expect(await screen.findByText('The SQL model service is unavailable.')).toBeInTheDocument();
    expect(fetchApi).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('region', { name: 'Answer' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Analysis 1/)).not.toBeInTheDocument();
  },
);
it('hides Jump to chart when the result has nothing plottable', async () => {
  fetchApi.mockReset();
  fetchApi
    .mockResolvedValueOnce({ status: 'pending_approval', pending_id: 'p', sql_hash: 'h' })
    .mockResolvedValueOnce({
      record: {
        id: 'repeated',
        question: 'Sales rows',
        columns: ['region', 'sales'],
        rows: [
          { region: 'North', sales: 10 },
          { region: 'North', sales: 20 },
        ],
      },
      presentation: { headline: 'Sales rows' },
    });
  page();
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Sales rows' } });
  fireEvent.click(screen.getByRole('button', { name: 'Run secure query' }));
  expect(await screen.findByText('Download CSV', { exact: false })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Jump to chart' })).not.toBeInTheDocument();
});
