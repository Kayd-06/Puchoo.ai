import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { QueryUniverse } from '../pages/AskData';
import { universePolicy } from '../utils/universePolicy';
let media, mediaChange, hidden, frames, index, context, intersection, resize, disconnect;
beforeEach(() => {
  vi.useFakeTimers();
  hidden = false;
  frames = new Map();
  index = 0;
  disconnect = vi.fn();
  media = {
    matches: false,
    addEventListener: vi.fn((_type, callback) => {
      mediaChange = callback;
    }),
    removeEventListener: vi.fn(),
  };
  vi.stubGlobal('matchMedia', () => media);
  vi.stubGlobal('navigator', { hardwareConcurrency: 8, deviceMemory: 8 });
  vi.stubGlobal('devicePixelRatio', 4);
  vi.spyOn(document, 'hidden', 'get').mockImplementation(() => hidden);
  vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockReturnValue({
    width: 4096,
    height: 2048,
    left: 0,
    top: 0,
  });
  context = new Proxy(
    { createRadialGradient: () => ({ addColorStop() {} }) },
    {
      get(target, key) {
        return target[key] ?? (target[key] = vi.fn());
      },
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
  vi.stubGlobal(
    'requestAnimationFrame',
    vi.fn((callback) => {
      frames.set(++index, callback);
      return index;
    }),
  );
  vi.stubGlobal(
    'cancelAnimationFrame',
    vi.fn((id) => frames.delete(id)),
  );
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(callback) {
        intersection = callback;
      }
      observe() {}
      disconnect = disconnect;
    },
  );
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
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function frame(time) {
  act(() => {
    const [id, callback] = frames.entries().next().value;
    frames.delete(id);
    callback(time);
  });
}
it('caps real scheduled paint and raster; visibility/offscreen/unmount release and cancel', () => {
  const view = render(<QueryUniverse />),
    canvas = view.container.querySelector('canvas');
  expect(canvas.width * canvas.height).toBeLessThanOrEqual(1500000);
  expect(Math.max(canvas.width, canvas.height)).toBeLessThanOrEqual(4096);
  frame(0);
  expect(context.clearRect).toHaveBeenCalledOnce();
  frame(10);
  expect(context.clearRect).toHaveBeenCalledOnce();
  frame(50);
  expect(context.clearRect).toHaveBeenCalledTimes(2);
  act(() => {
    hidden = true;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(frames.size).toBe(0);
  expect(canvas.width * canvas.height).toBe(0);
  act(() => {
    hidden = false;
    document.dispatchEvent(new Event('visibilitychange'));
  });
  expect(frames.size).toBe(1);
  act(() => intersection([{ isIntersecting: false }]));
  expect(frames.size).toBe(0);
  expect(canvas.width).toBe(0);
  act(() => intersection([{ isIntersecting: true }]));
  expect(frames.size).toBe(1);
  act(() => resize());
  expect(vi.getTimerCount()).toBeGreaterThan(0);
  view.unmount();
  expect(frames.size).toBe(0);
  expect(canvas.width).toBe(0);
  expect(vi.getTimerCount()).toBe(0);
  expect(disconnect).toHaveBeenCalledTimes(2);
});
it('honors initial and changing reduced-motion preference without acquiring a context', () => {
  media.matches = true;
  const view = render(<QueryUniverse />),
    canvas = view.container.querySelector('canvas');
  expect(HTMLCanvasElement.prototype.getContext).not.toHaveBeenCalled();
  expect(frames.size).toBe(0);
  act(() => {
    media.matches = false;
    mediaChange();
  });
  expect(frames.size).toBe(1);
  act(() => {
    media.matches = true;
    mediaChange();
  });
  expect(frames.size).toBe(0);
  expect(canvas.width).toBe(0);
  view.unmount();
  expect(media.removeEventListener).toHaveBeenCalledWith('change', mediaChange);
});
it('uses static low-resource mode and does not run an animation loop', () => {
  vi.stubGlobal('navigator', { hardwareConcurrency: 1, deviceMemory: 1 });
  const view = render(<QueryUniverse />),
    canvas = view.container.querySelector('canvas');
  expect(context.clearRect).toHaveBeenCalledOnce();
  expect(canvas.width * canvas.height).toBeLessThanOrEqual(500000);
  expect(frames.size).toBe(0);
  view.unmount();
  expect(canvas.width).toBe(0);
});
it('decorative context failure never prevents mounting the interface', () => {
  HTMLCanvasElement.prototype.getContext.mockImplementation(() => {
    throw new Error('synthetic unavailable canvas');
  });
  const view = render(<QueryUniverse />);
  expect(frames.size).toBe(0);
  expect(view.container.querySelector('canvas').width).toBe(0);
});
it('enforces policy count/pixel bounds across synthetic viewports and device hints', () => {
  for (const width of [1, 360, 719, 720, 1920, 4096, 10000])
    for (const height of [1, 720, 2160, 10000])
      for (const dpr of [1, 2, 4]) {
        const p = universePolicy({ width, height, dpr });
        expect(p.pixelWidth * p.pixelHeight).toBeLessThanOrEqual(1500000);
        expect(p.clusters + p.dust + p.still + p.streams).toBeLessThanOrEqual(
          width < 720 ? 900 : 2400,
        );
      }
  for (const hint of [{ saveData: true }, { hardwareConcurrency: 2 }, { deviceMemory: 2 }])
    expect(universePolicy({ width: 1200, height: 800, ...hint }).mode).toBe('static');
  expect(universePolicy({ width: 1e100, height: 1e100 }).mode).toBe('off');
});
