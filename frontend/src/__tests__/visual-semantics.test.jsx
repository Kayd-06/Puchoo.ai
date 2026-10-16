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

it('keeps narrow account and member controls compact without orphaned text', () => {
  const css = source('src/index.css');
  expect(css).toMatch(/\.workspace-member\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+88px\s+34px/s);
  expect(css).toMatch(/\.settings-workspace-badge\s*\{[^}]*white-space:\s*nowrap/s);
  expect(css).toMatch(/\.topbar-account-copy\s*\{[^}]*min-width:\s*0/s);
  expect(css).toMatch(/\.topbar-account-email\s*\{[^}]*text-overflow:\s*ellipsis[^}]*white-space:\s*nowrap/s);
  expect(css).toMatch(/\.topbar-account-panel\s*\{[^}]*width:\s*min\(284px,\s*calc\(100vw\s*-\s*24px\)\)/s);
});

it('runs a generated read-only query directly without a second confirmation panel', () => {
  const markup = source('src/pages/AskData.jsx');
  expect(markup).toMatch(/const executeProposal = async \(proposal\)/);
  expect(markup).toMatch(/await executeProposal\(proposal\)/);
  expect(markup).not.toMatch(/query-approval-panel/);
  expect(markup).not.toMatch(/Ready to run this query\?/);
});

it('renders query errors as a compact dark-theme alert', () => {
  const markup = source('src/pages/AskData.jsx');
  const css = source('src/index.css');
  expect(markup).toMatch(/className="ask-error" role="alert"/);
  expect(css).toMatch(/\.ask-error\s*\{[^}]*background:\s*#[0-9a-f]{6}/s);
});

it('defines separate authenticated palettes for both theme states', () => {
  const css = source('src/index.css');
  expect(css).toMatch(/html\[data-theme="dark"\]\s*\.app-container/s);
  expect(css).toMatch(/html\[data-theme="light"\]\s*\.app-container/s);
  expect(css).toMatch(/\.theme-toggle\s*\{/);
});

it('keeps the data-source background word outline-only and highlights it only on direct hover', () => {
  const markup = source('src/pages/ConnectData.jsx');
  const css = source('src/index.css');
  expect(markup).toMatch(/<svg className="connect-word"[\s\S]*pointerEvents="stroke"/);
  expect(css).not.toMatch(/\.connect-stage:has\(\.connect-tablist button:hover\) \.connect-word/s);
  expect(css).toMatch(/\.connect-word:hover/s);
  expect(css).toMatch(/\.connect-word text\s*\{[^}]*pointer-events:\s*stroke/s);
  expect(css).toMatch(/html\[data-theme="dark"\][^{]*\{[^}]*stroke:\s*#fff/s);
  expect(css).toMatch(/html\[data-theme="light"\][^{]*\{[^}]*stroke:\s*#111/s);
  expect(css).toMatch(/\.connect-word\s*\{[^}]*color:\s*transparent/s);
  expect(css).toMatch(/\.connect-stage-content\s*\{[^}]*z-index:\s*5[^}]*pointer-events:\s*none/s);
  expect(css).toMatch(/\.connect-tablist,[\s\S]*?\.connect-submit,[\s\S]*?\{[^}]*pointer-events:\s*auto/s);
});
