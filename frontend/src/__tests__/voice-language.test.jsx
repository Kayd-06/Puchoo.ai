import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import AskData from '../pages/AskData';
import { fetchApi } from '../api/client';

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
  vi.clearAllMocks();
});

it('automatically detects the spoken language and uses it for the submitted question', async () => {
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  const stop = vi.fn();
  vi.stubGlobal('navigator', {
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }) },
  });
  class Recorder {
    static isTypeSupported() {
      return true;
    }
    mimeType = 'audio/ogg';
    state = 'inactive';
    start() {
      this.state = 'recording';
    }
    stop() {
      this.state = 'inactive';
      this.ondataavailable({ data: new Blob(['OggS audio'], { type: this.mimeType }) });
      this.onstop();
    }
  }
  vi.stubGlobal('MediaRecorder', Recorder);
  fetchApi.mockResolvedValueOnce({ transcript: 'कुल बिक्री बताओ', language_code: 'hi-IN' });
  render(
    <MemoryRouter>
      <AskData />
    </MemoryRouter>,
  );
  expect(screen.queryByRole('combobox', { name: 'Voice language' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Speak your question' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Stop recording' }));
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('कुल बिक्री बताओ'));
  const [endpoint, options] = fetchApi.mock.calls[0];
  expect(endpoint).toBe('/voice/transcribe');
  expect(options.body.has('language_code')).toBe(false);
  expect(options.body.get('file').name).toBe('puchoo-question.ogg');
  expect(stop).toHaveBeenCalledOnce();
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    clarification: 'Which month?',
  });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  await waitFor(() => expect(fetchApi).toHaveBeenCalledTimes(2));
  expect(JSON.parse(fetchApi.mock.calls[1][1].body)).toMatchObject({
    language_code: 'hi-IN',
    question: 'कुल बिक्री बताओ',
  });
  // A typed replacement must not retain the preceding Hindi recording's hint.
  fetchApi.mockResolvedValueOnce({
    status: 'clarification_required',
    clarification: 'Which month?',
  });
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Show total expenses' } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  await waitFor(() => expect(fetchApi).toHaveBeenCalledTimes(3));
  expect(JSON.parse(fetchApi.mock.calls[2][1].body)).toMatchObject({
    language_code: null,
    question: 'Show total expenses',
  });
});
