import { afterEach, expect, it, vi } from 'vitest';
import { playAnswerAudio, requestMicrophone } from '../voice';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('times out unanswered microphone permission and stops a late stream', async () => {
  vi.useFakeTimers();
  let grant;
  const stop = vi.fn();
  vi.stubGlobal('navigator', {
    mediaDevices: {
      getUserMedia: () =>
        new Promise((resolve) => {
          grant = resolve;
        }),
    },
  });
  const pending = requestMicrophone(100);
  const rejected = expect(pending).rejects.toThrow('Microphone permission is still pending');
  await vi.advanceTimersByTimeAsync(100);
  await rejected;
  grant({ getTracks: () => [{ stop }] });
  await Promise.resolve();
  expect(stop).toHaveBeenCalledOnce();
});

it('returns a granted microphone stream', async () => {
  const stream = { getTracks: () => [] };
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } });
  expect(await requestMicrophone()).toBe(stream);
});

it('keeps blocked answer playback resumable after a user tap', async () => {
  const audio = {
    play: vi
      .fn()
      .mockRejectedValueOnce(new DOMException('Tap required', 'NotAllowedError'))
      .mockResolvedValueOnce(),
  };
  expect(await playAnswerAudio(audio)).toBe('paused');
  expect(await playAnswerAudio(audio)).toBe('playing');
});

it('reports audio decode errors instead of treating them as paused', async () => {
  const error = new DOMException('Invalid audio', 'NotSupportedError');
  await expect(playAnswerAudio({ play: () => Promise.reject(error) })).rejects.toBe(error);
});
