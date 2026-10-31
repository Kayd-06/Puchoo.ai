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
  useAuth: () => ({ user: { workspace_role: 'owner' } }),
}));
vi.mock('../api/client', () => ({ fetchApi: vi.fn(), fetchApiBlob: vi.fn() }));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

async function showReport() {
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
  const audios = await showReport();
  let finish;
  fetchApiBlob.mockImplementationOnce(
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
