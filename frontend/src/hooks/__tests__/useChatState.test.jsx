import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { clearChatSessions, useChatState } from '../useChatState';

afterEach(() => {
  clearChatSessions();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

it('restores a draft and result across route unmounts', () => {
  const first = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  act(() => first.result.current[1]('मेरे खर्चे'));
  first.unmount();
  const second = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  expect(second.result.current[0]).toBe('मेरे खर्चे');
  expect(Object.values(sessionStorage)).toContain(JSON.stringify({ value: 'मेरे खर्चे' }));
});

it('loads persisted state after a fresh module load, as on refresh', async () => {
  const first = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  act(() => first.result.current[1]('Show expenses'));
  first.unmount();
  vi.resetModules();
  const fresh = await import('../useChatState');
  const second = renderHook(() => fresh.useChatState('ada', 'sales', 'question', ''));
  expect(second.result.current[0]).toBe('Show expenses');
  second.unmount();
  fresh.clearChatSessions();
});

it('isolates accounts and workspaces and switches back to the saved draft', () => {
  const hook = renderHook(({ user, workspace }) => useChatState(user, workspace, 'question', ''), {
    initialProps: { user: 'ada', workspace: 'sales' },
  });
  act(() => hook.result.current[1]('Sales question'));
  hook.rerender({ user: 'ada', workspace: 'costs' });
  expect(hook.result.current[0]).toBe('');
  hook.rerender({ user: 'bob', workspace: 'sales' });
  expect(hook.result.current[0]).toBe('');
  hook.rerender({ user: 'ada', workspace: 'sales' });
  expect(hook.result.current[0]).toBe('Sales question');
});

it('saves a completed request after leaving the route and ignores callbacks after logout', () => {
  const first = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  const finish = first.result.current[1];
  first.unmount();
  act(() => finish('Finished while away'));
  const second = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  expect(second.result.current[0]).toBe('Finished while away');
  act(() => clearChatSessions());
  act(() => finish('Late response after logout'));
  expect(sessionStorage.length).toBe(0);
  expect(second.result.current[0]).toBe('');
});

it('retains navigation state when browser storage is unavailable', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('quota');
  });
  const first = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  act(() => first.result.current[1]('Still here'));
  first.unmount();
  const second = renderHook(() => useChatState('ada', 'sales', 'question', ''));
  expect(second.result.current[0]).toBe('Still here');
});

it('restores complete result tables and ignores malformed saved results', () => {
  const answer = {
    record: { columns: ['amount'], rows: [{ amount: 0 }, { amount: 200 }] },
    presentation: { headline: 'कुल खर्च', language_code: 'hi-IN' },
  };
  const first = renderHook(() => useChatState('ada', 'sales', 'result', null));
  act(() => first.result.current[1](answer));
  first.unmount();
  const second = renderHook(() => useChatState('ada', 'sales', 'result', null));
  expect(second.result.current[0]).toEqual(answer);
  sessionStorage.setItem('puchoo:chat:v1:ada:bad:result', '{"value":{"record":{}}}');
  const bad = renderHook(() => useChatState('ada', 'bad', 'result', null));
  expect(bad.result.current[0]).toBeNull();
});
