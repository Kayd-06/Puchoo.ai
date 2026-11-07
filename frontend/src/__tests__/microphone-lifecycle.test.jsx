import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import AskData from '../pages/AskData';
import { fetchApi } from '../api/client';
const context = vi.hoisted(() => ({
  activeWorkspaceId: 'voice',
  activeWorkspace: { name: 'Voice' },
  refreshWorkspaces: vi.fn(),
}));
vi.mock('../context/AppContext', () => ({ useAppContext: () => context }));
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'mic-user', tenant_id: 'mic-user', workspace_role: 'owner' } }),
}));
vi.mock('../api/client', () => ({ fetchApi: vi.fn(), fetchApiBlob: vi.fn() }));
let sequence = 0;
let recorders;
let track;
let stream;
function deferred() {
  let resolve;
  const promise = new Promise((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function mount() {
  return render(
    <MemoryRouter>
      <AskData />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  context.activeWorkspaceId = `voice-${sequence++}`;
  sessionStorage.clear();
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  track = { stop: vi.fn() };
  stream = { getTracks: () => [track] };
  recorders = [];
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } });
  vi.stubGlobal(
    'MediaRecorder',
    class {
      static isTypeSupported() {
        return true;
      }
      constructor() {
        this.mimeType = 'audio/ogg';
        this.state = 'inactive';
        recorders.push(this);
      }
      start() {
        this.state = 'recording';
      }
      stop() {
        this.state = 'inactive';
        this.onstop?.();
      }
    },
  );
  fetchApi.mockReset();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
async function record() {
  fireEvent.click(screen.getByRole('button', { name: 'Speak your question' }));
  await screen.findByRole('button', { name: 'Stop recording' });
  act(() => recorders[0].ondataavailable({ data: new Blob(['audio'], { type: 'audio/ogg' }) }));
}
it('stops a stream granted after unmount without constructing a recorder', async () => {
  const permission = deferred();
  navigator.mediaDevices.getUserMedia.mockReturnValue(permission.promise);
  const view = mount();
  fireEvent.click(screen.getByRole('button', { name: 'Speak your question' }));
  view.unmount();
  await act(async () => permission.resolve(stream));
  expect(track.stop).toHaveBeenCalledOnce();
  expect(recorders).toHaveLength(0);
  expect(fetchApi).not.toHaveBeenCalled();
});
it('detaches recorder callbacks and stops every track on unmount', async () => {
  const view = mount();
  await record();
  const stop = recorders[0].onstop;
  view.unmount();
  expect(recorders[0].state).toBe('inactive');
  expect(recorders[0].onstop).toBeNull();
  expect(track.stop).toHaveBeenCalledOnce();
  await act(async () => stop());
  expect(fetchApi).not.toHaveBeenCalled();
});
it('aborts transcription and ignores a transport response arriving after workspace switch', async () => {
  const response = deferred();
  fetchApi.mockReturnValue(response.promise);
  const view = mount();
  await record();
  fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }));
  await waitFor(() => expect(fetchApi).toHaveBeenCalledOnce());
  const options = fetchApi.mock.calls[0][1];
  context.activeWorkspaceId = `voice-${sequence++}`;
  view.rerender(
    <MemoryRouter>
      <AskData />
    </MemoryRouter>,
  );
  expect(options.signal.aborted).toBe(true);
  expect(track.stop).toHaveBeenCalledOnce();
  await act(async () =>
    response.resolve({ transcript: 'OLD PRIVATE TRANSCRIPT', language_code: 'hi-IN' }),
  );
  expect(screen.getByRole('textbox')).toHaveValue('');
  expect(JSON.stringify({ ...sessionStorage })).not.toContain('OLD PRIVATE TRANSCRIPT');
});
it('cancels conversion resources and never starts transcription after unmount', async () => {
  const decode = deferred();
  const close = vi.fn().mockResolvedValue();
  vi.stubGlobal(
    'AudioContext',
    class {
      state = 'running';
      decodeAudioData = () => decode.promise;
      close = close;
    },
  );
  vi.spyOn(Blob.prototype, 'arrayBuffer').mockResolvedValue(new ArrayBuffer(1));
  const view = mount();
  await record();
  recorders[0].mimeType = 'audio/webm';
  fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }));
  await act(async () => {});
  view.unmount();
  expect(close).toHaveBeenCalled();
  await act(async () => decode.resolve({}));
  expect(fetchApi).not.toHaveBeenCalled();
});
it('accepts a current transcript and releases capture before sending it', async () => {
  fetchApi.mockResolvedValue({ transcript: 'sales total', language_code: 'en-IN' });
  mount();
  await record();
  fireEvent.click(screen.getByRole('button', { name: 'Stop recording' }));
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue('sales total'));
  expect(track.stop).toHaveBeenCalledOnce();
  expect(screen.getByRole('button', { name: 'Speak your question' })).toBeEnabled();
});
