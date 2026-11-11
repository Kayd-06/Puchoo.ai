import { expect, it } from 'vitest';

import { queryUniversePalette } from '../AskData';

it('uses visible black moving particles against the light app theme', () => {
  expect(queryUniversePalette('light')).toMatchObject({
    composite: 'source-over',
    motion: 1.45,
    dust: '22, 19, 16',
    stream: '35, 32, 29',
    star: '21, 18, 15',
  });
  expect(queryUniversePalette('dark').composite).toBe('source-over');
});

it('shows the advisory scope warning as plain text and hides it when absent', async () => {
  const { render, screen } = await import('@testing-library/react');
  const { ScopeWarning } = await import('../AskData');
  const { container, rerender } = render(<ScopeWarning message="<b>Check the SQL</b>" />);
  expect(screen.getByRole('status')).toHaveTextContent('<b>Check the SQL</b>');
  expect(container.querySelector('b')).toBeNull();
  rerender(<ScopeWarning message={undefined} />);
  expect(screen.queryByRole('status')).toBeNull();
});

it('distinguishes mismatched, unavailable, and verified answers', async () => {
  const { answerVerification } = await import('../AskData');
  expect(answerVerification('VERIFICATION_MISMATCH').label).toBe('Verification failed');
  expect(answerVerification('UNAVAILABLE').label).toBe('Not independently verified');
  expect(answerVerification('VERIFIED').verified).toBe(true);
  expect(answerVerification('unknown').verified).toBe(false);
});

it('resizes the particle bitmap when a hidden canvas becomes visible', async () => {
  const { act, render } = await import('@testing-library/react');
  const { vi } = await import('vitest');
  const { QueryUniverse } = await import('../AskData');
  let width = 0;
  let resize;
  const disconnect = vi.fn();
  const context = { setTransform: vi.fn(), clearRect: vi.fn() };
  const canvasContext = vi
    .spyOn(HTMLCanvasElement.prototype, 'getContext')
    .mockReturnValue(context);
  const bounds = vi
    .spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect')
    .mockImplementation(() => ({ width, height: width ? 400 : 0, left: 0, top: 0 }));
  vi.useFakeTimers();
  vi.stubGlobal('matchMedia', () => ({ matches: false }));
  vi.stubGlobal('devicePixelRatio', 1);
  vi.stubGlobal('requestAnimationFrame', vi.fn().mockReturnValue(1));
  vi.stubGlobal('cancelAnimationFrame', vi.fn());
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback) {
        resize = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
  try {
    const { container, unmount } = render(<QueryUniverse />);
    const canvas = container.querySelector('canvas');
    // A hidden (zero-size) canvas must not keep a stretched bitmap.
    expect(canvas.width).toBe(0);
    width = 800;
    act(() => {
      resize();
      // Resizes are debounced so layout bursts repaint once.
      vi.advanceTimersByTime(100);
    });
    expect(canvas.width).toBe(800);
    expect(canvas.height).toBe(400);
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  } finally {
    vi.useRealTimers();
    canvasContext.mockRestore();
    bounds.mockRestore();
    vi.unstubAllGlobals();
  }
});

it('uses neutral white particles in the pitch-black theme', () => {
  const palette = queryUniversePalette('dark');
  for (const key of ['dust', 'stream', 'star', 'cluster', 'orbit']) {
    const channels = palette[key].split(',').map(Number);
    expect(channels[0]).toBe(channels[1]);
    expect(channels[1]).toBe(channels[2]);
  }
});
