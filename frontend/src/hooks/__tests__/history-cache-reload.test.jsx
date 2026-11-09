import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

let current;
const scope = {
  userId: 'reload-owner',
  tenantId: 'reload-tenant',
  role: 'owner',
  workspaceId: 'a',
};
const answer = {
  record: { id: 'old', columns: [], rows: [] },
  presentation: { headline: 'old answer' },
};
afterEach(() => {
  current?.clearChatSessions();
  sessionStorage.clear();
  localStorage.clear();
});

it.each(['single', 'all'])(
  'a fresh module rejects stale persisted results and tickets after %s deletion',
  async (mode) => {
    current = await import('../useChatState');
    const h = renderHook(() => current.useChatState(scope, 'a', 'result', null));
    act(() => h.result.current[1](answer));
    const oldSnapshot = sessionStorage.getItem(`puchoo:chat:v2:${current.scopeKey(scope)}`);
    const ticket = current.makeContinuation(scope, { id: 'old', question: 'previous' });
    h.unmount();
    current.invalidateHistory(scope, mode === 'all' ? null : 'old');
    // Model a stale session snapshot surviving in another tab before its event arrives.
    sessionStorage.setItem(`puchoo:chat:v2:${current.scopeKey(scope)}`, oldSnapshot);
    vi.resetModules();
    current = await import('../useChatState');
    const reloaded = renderHook(() => current.useChatState(scope, 'a', 'result', null));
    expect(reloaded.result.current[0]).toBeNull();
    expect(current.consumeContinuation(scope, ticket)).toBeNull();
    reloaded.unmount();
  },
);

it('a fresh module restores legitimate scoped context without reopening the one-use route ticket', async () => {
  vi.resetModules();
  current = await import('../useChatState');
  const ticket = current.makeContinuation(scope, { id: 'legitimate', question: 'previous' });
  current.startContinuation(scope, current.consumeContinuation(scope, ticket));
  vi.resetModules();
  current = await import('../useChatState');
  const h = renderHook(() => current.useChatState(scope, 'a', 'continuation', null));
  expect(h.result.current[0].recordId).toBe('legitimate');
  expect(current.consumeContinuation(scope, ticket)).toBeNull();
  h.unmount();
});
