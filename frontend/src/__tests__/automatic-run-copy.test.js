import { readFileSync } from 'node:fs';
import { expect, it } from 'vitest';
it('current landing/legal/setup copy never promises mandatory manual SQL approval', () => {
  const files = [
    'src/components/landing/Sections.jsx',
    'src/pages/Landing.jsx',
    'src/pages/Legal.jsx',
    'index.html',
    '../README.md',
    '../.env.example',
    '../docs/permissions.md',
  ];
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    expect(text, file).not.toMatch(
      /nothing runs (?:until|without)|waits for your approval|only after you\s+approve|approval required|approve before execute|explicit human approval step/i,
    );
  }
  expect(readFileSync('src/pages/Legal.jsx', 'utf8')).toContain(
    'automatically runs it after server-side validation',
  );
  expect(readFileSync('../README.md', 'utf8')).toContain(
    'No mandatory Run/Cancel or second approval UI',
  );
});
