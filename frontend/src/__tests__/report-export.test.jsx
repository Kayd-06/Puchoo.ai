import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';
import { expect, it } from 'vitest';

const source = () => readFileSync(resolve(process.cwd(), 'src/pages/AskData.jsx'), 'utf8');

it('offers CSV and PDF downloads for generated result tables', () => {
  const markup = source();
  expect(markup).toMatch(/downloadReportCsv/);
  expect(markup).toMatch(/downloadReportPdf/);
  expect(markup).toMatch(/Download CSV/);
  expect(markup).toMatch(/Download PDF/);
  expect(markup).toMatch(/result-export-actions/);
});
