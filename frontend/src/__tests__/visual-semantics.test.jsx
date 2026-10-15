import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';
import { expect, it } from 'vitest';

const source = (path) => readFileSync(resolve(process.cwd(), path), 'utf8');

it('omits decorative security claims from authenticated screens', () => {
  const markup = [
    source('src/components/layout/TopBar.jsx'),
    source('src/components/workspace/WorkspaceInvitePanel.jsx'),
    source('src/pages/Settings.jsx'),
    source('src/pages/ConnectData.jsx'),
  ].join('\n');
  expect(markup).not.toMatch(/Tenant isolated|HttpOnly session|Guardrails active|Secure ingestion|Encrypted in transit/);
});

it('removes authenticated scan and glow animation treatments', () => {
  const css = source('src/index.css');
  expect(css).not.toMatch(/history-(?:border|metal)-beam|ask-query-perimeter|query-glow-angle|is-illuminated/);
  expect(css).toMatch(/\.settings-section::before,\.settings-email-dialog::before\{display:none!important/);
});
