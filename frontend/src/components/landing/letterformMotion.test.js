import { expect, it } from 'vitest';
import { footerLetters } from './footerLetterforms';
import { parseLetterPath, pointTarget, writeLetterPath } from './letterformMotion';

it('keeps every contour dot attached to a real path endpoint', () => {
  for (const glyph of footerLetters) {
    const geometry = parseLetterPath(glyph.path);
    for (const [x, y] of glyph.nodes) {
      expect(geometry.points.some((p) => Math.hypot(p.x - x, p.y - y) < 0.02)).toBe(true);
    }
    expect(writeLetterPath(geometry.commands, geometry.points)).not.toMatch(/NaN|undefined/);
  }
});

it('moves nearby outline points away from the cursor while distant points stay still', () => {
  expect(pointTarget({ x: 20, y: 20 }, { x: 18, y: 20 }, null).x).toBeGreaterThan(20);
  expect(pointTarget({ x: 200, y: 200 }, { x: 18, y: 20 }, null)).toEqual({ x: 200, y: 200 });
});

it('pulls the selected anchor and surrounding curve points together', () => {
  const drag = { origin: { x: 10, y: 10 }, x: 35, y: 25 };
  expect(pointTarget({ x: 10, y: 10 }, null, drag)).toEqual({ x: 35, y: 25 });
  expect(pointTarget({ x: 20, y: 10 }, null, drag).x).toBeGreaterThan(20);
  expect(pointTarget({ x: 150, y: 150 }, null, drag)).toEqual({ x: 150, y: 150 });
});
