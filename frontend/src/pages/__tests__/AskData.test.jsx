import { expect, it } from 'vitest';

import { queryUniversePalette } from '../AskData';

it('uses visible black moving particles against the light app theme', () => {
  expect(queryUniversePalette('light')).toMatchObject({
    composite: 'source-over',
    dust: '16, 28, 35',
    stream: '29, 50, 64',
    star: '15, 28, 36',
  });
  expect(queryUniversePalette('dark').composite).toBe('lighter');
});
