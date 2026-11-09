import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import AskData from '../pages/AskData';
import { fetchApi, fetchApiBlob } from '../api/client';

vi.mock('../context/AppContext', () => ({
  useAppContext: () => ({
    activeWorkspaceId: 'sales',
    activeWorkspace: { name: 'Sales' },
    refreshWorkspaces: vi.fn(),
  }),
}));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'ada', tenant_id: 'ada', workspace_role: 'owner' } }),
}));
vi.mock('../api/client', () => ({ fetchApi: vi.fn(), fetchApiBlob: vi.fn() }));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

async function showReport(secondClip) {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  Element.prototype.scrollIntoView = vi.fn();
  const audios = [];
  vi.stubGlobal(
    'Audio',
    class {
      constructor() {
        this.play = vi.fn().mockResolvedValue();
        this.pause = vi.fn();
        this.removeAttribute = vi.fn();
        this.load = vi.fn();
        audios.push(this);
      }
    },
  );
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:clip');
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  fetchApi
    .mockResolvedValueOnce({ pending_id: 'proposal', sql_hash: 'hash' })
    .mockResolvedValueOnce({
      record: {
        id: 'saved-report',
        question: 'खर्च',
        language_code: 'hi-IN',
        columns: ['amount'],
        rows: [{ amount: 0 }, { amount: 200 }],
        row_count: 2,
      },
      presentation: {
        headline: 'विवरण '.repeat(450),
        detail: 'दो परिणाम',
        language_code: 'hi-IN',
        column_labels: { amount: 'राशि' },
        display_rows: [{ amount: 0 }, { amount: 200 }],
      },
    });
  fetchApiBlob.mockResolvedValue(new Blob(['RIFF audio'], { type: 'audio/wav' }));
  if (secondClip)
    fetchApiBlob.mockResolvedValueOnce(new Blob(['first'])).mockImplementationOnce(secondClip);
  render(
    <MemoryRouter>
      <AskData />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'खर्च बताओ' } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  fireEvent.click(await screen.findByRole('button', { name: 'Listen to answer' }));
  await waitFor(() => expect(audios[0]?.play).toHaveBeenCalledOnce());
  return audios;
}

it('plays all clips in Hindi in order and reads the final table row', async () => {
  const audios = await showReport();
  for (let i = 0; i < 10; i += 1) {
    const current = audios[i];
    if (!current) break;
    await act(async () => {
      current.onended();
    });
  }
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Listen to answer' })).toBeInTheDocument(),
  );
  const requests = fetchApiBlob.mock.calls.map(([, options]) => JSON.parse(options.body));
  expect(requests.length).toBeGreaterThan(1);
  expect(requests.every((r) => r.language_code === 'hi-IN' && r.text.length <= 2000)).toBe(true);
  const spoken = requests.map((r) => r.text).join('');
  expect(spoken).toContain('राशि: 0');
  expect(spoken).toContain('राशि: 200');
});

it('stops the sequence and ignores a clip arriving after Stop', async () => {
  let finish;
  const audios = await showReport(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  await act(async () => {
    audios[0].onended();
  });
  fireEvent.click(screen.getByRole('button', { name: 'Stop reading answer' }));
  await act(async () => {
    finish(new Blob(['audio'], { type: 'audio/wav' }));
  });
  expect(audios).toHaveLength(1);
  expect(screen.getByRole('button', { name: 'Listen to answer' })).toBeInTheDocument();
});

it('prepares the next clip while the first clip is playing', async () => {
  const audios = await showReport();
  await waitFor(() => expect(fetchApiBlob).toHaveBeenCalledTimes(2));
  expect(audios).toHaveLength(1);
});

it('starts a new chat and stops active speech without deleting history', async () => {
  const audios = await showReport();
  fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
  expect(screen.queryByRole('region', { name: 'Query results' })).not.toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('');
  expect(audios[0].pause).toHaveBeenCalled();
  expect(fetchApi).toHaveBeenCalledTimes(2);
});

it('provides one chat reset action while preserving saved history', async () => {
  await showReport();
  expect(screen.queryByRole('button', { name: 'Clear chat' })).not.toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'New chat' })).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'New chat' }));
  await waitFor(() =>
    expect(screen.queryByRole('region', { name: 'Query results' })).not.toBeInTheDocument(),
  );
  expect(fetchApi).toHaveBeenCalledTimes(2);
  expect(fetchApi.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(false);
  expect(screen.getByRole('textbox')).toHaveValue('');
});

it('does not submit duplicate requests when Enter is pressed during generation', async () => {
  await showReport();
  let finish;
  fetchApi.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Compare sales by region' } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  expect(fetchApi).toHaveBeenCalledTimes(3);
  await act(async () => {
    finish({ status: 'clarification_required', message: 'Which period?', suggestions: [] });
  });
  expect(screen.getByText('Which period?')).toBeInTheDocument();
  expect(fetchApi).toHaveBeenCalledTimes(3);
});

it('places clarification beside the composer and submits the selected answer immediately', async () => {
  await showReport();
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    reason: 'missing_time_definition',
    message: 'Which period?',
    suggestions: ['Use calendar year instead'],
  });
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Compare sales by region' } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  const choice = await screen.findByRole('button', { name: 'Use calendar year instead' });
  const panel = screen.getByRole('region', { name: 'Clarify your question' });
  expect(panel.closest('.ask-stage-content')).toContainElement(screen.getByRole('textbox'));
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    message: 'Select a metric',
    suggestions: [],
  });
  fireEvent.click(choice);
  await waitFor(() => expect(fetchApi).toHaveBeenCalledTimes(4));
  expect(JSON.parse(fetchApi.mock.calls[3][1].body)).toMatchObject({
    question: 'Compare sales by region',
    clarifications: [{ reason: 'missing_time_definition', choice: 'Use calendar year instead' }],
  });
  expect(screen.getByRole('textbox')).toHaveValue('Compare sales by region');
});

it('replays prior choices separately while keeping original class and date filters', async () => {
  await showReport();
  const question =
    'Classify students in class 10 in 2025 using marks attendance fees and enrollment';
  const first = {
    reason: 'missing_classification_factor_rules',
    choice:
      'Classify using marks and attendance only; show fee-payment behavior and enrollment status separately',
  };
  const second = {
    reason: 'missing_performance_classification_definition',
    choice:
      'Compare the latest assessment with the previous assessment and show the attendance change separately; classify using marks change of at least +5 or at most -5 percentage points',
  };
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    reason: first.reason,
    message: 'Which factors?',
    suggestions: [first.choice],
    clarifications: [],
  });
  fireEvent.change(screen.getByRole('textbox'), { target: { value: question } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  const choice = await screen.findByRole('button', { name: first.choice });
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    reason: second.reason,
    message: 'Which rules?',
    suggestions: [second.choice],
    clarifications: [first],
  });
  fireEvent.click(choice);
  const nextChoice = await screen.findByRole('button', { name: second.choice });
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    reason: 'additional_definition_required',
    message: 'Provide exact rules',
    suggestions: [],
  });
  fireEvent.click(nextChoice);
  await screen.findByText('Provide exact rules');
  expect(JSON.parse(fetchApi.mock.calls.at(-1)[1].body)).toMatchObject({
    question,
    clarifications: [first, second],
  });
  expect(screen.getByRole('textbox')).toHaveValue(question);
});
