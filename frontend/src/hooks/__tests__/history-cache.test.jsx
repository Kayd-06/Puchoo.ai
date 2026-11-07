import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import {
  startContinuation,
  chatScope,
  scopeKey,
  useChatState,
  clearChatSessions,
  invalidateHistory,
  historyToken,
  tokenCurrent,
  clearVersion,
  filterHistory,
  makeContinuation,
  consumeContinuation,
  continuationMatches,
} from '../useChatState';

let sequence = 0;
const scope = () =>
  chatScope(
    { id: `cache-owner-${++sequence}`, tenant_id: `tenant-${sequence}`, role: 'owner' },
    'a',
  );
const answer = (id) => ({
  record: { id, columns: ['amount'], rows: [{ amount: 20 }] },
  presentation: { headline: id },
});
const key = (s) => `puchoo:chat:v2:${scopeKey(s)}`;
const seed = (s, values, version = clearVersion(s)) =>
  sessionStorage.setItem(key(s), JSON.stringify({ version, values }));
afterEach(() => {
  clearChatSessions();
  sessionStorage.clear();
  localStorage.clear();
  vi.restoreAllMocks();
});

it('isolates actor, tenant, role and workspace and rejects legacy unscoped caches', () => {
  const s = scope();
  sessionStorage.setItem('puchoo:chat:v1:old:a:question', JSON.stringify('legacy'));
  const h = renderHook(({ identity }) => useChatState(identity, 'a', 'question', ''), {
    initialProps: { identity: s },
  });
  act(() => h.result.current[1]('private draft'));
  for (const other of [
    { ...s, role: 'viewer' },
    { ...s, userId: 'other' },
    { ...s, tenantId: 'other' },
    { ...s, workspaceId: 'b' },
  ]) {
    h.rerender({ identity: other });
    expect(h.result.current[0]).toBe('');
  }
  h.rerender({ identity: s });
  expect(h.result.current[0]).toBe('private draft');
  expect(sessionStorage.getItem('puchoo:chat:v1:old:a:question')).toBeNull();
});

it('retires late captured writers on single deletion while new setters remain usable', () => {
  const s = scope();
  const h = renderHook(() => useChatState(s, 'a', 'result', null));
  act(() => h.result.current[1](answer('old')));
  const late = h.result.current[1];
  act(() => invalidateHistory(s, 'old'));
  expect(h.result.current[0]).toBeNull();
  act(() => late(answer('old')));
  expect(h.result.current[0]).toBeNull();
  act(() => h.result.current[1](answer('new')));
  expect(h.result.current[0].record.id).toBe('new');
});

it('selecting a new conversation retires previous same-scope requests and result writers', () => {
  const s = scope(),
    token = historyToken(s);
  const h = renderHook(() => useChatState(s, 'a', 'result', null));
  const late = h.result.current[1];
  const ticket = consumeContinuation(
    s,
    makeContinuation(s, { id: 'chosen', question: 'original' }),
  );
  act(() => startContinuation(s, ticket));
  expect(tokenCurrent(token)).toBe(false);
  act(() => late(answer('old')));
  expect(h.result.current[0]).toBeNull();
});

it('evicts inactive account snapshots and continuation tickets but not unrelated views', () => {
  const s = scope(),
    other = { ...s, workspaceId: 'b' },
    member = { ...s, userId: 'member', role: 'viewer' };
  seed(member, { question: 'deleted', result: answer('old') });
  seed(other, { question: 'keep', result: answer('old') });
  const ticket = makeContinuation(s, { id: 'old', question: 'original' });
  invalidateHistory(s, 'old');
  expect(sessionStorage.getItem(key(member))).toBeNull();
  expect(JSON.parse(sessionStorage.getItem(key(other))).values.question).toBe('keep');
  expect(consumeContinuation(s, ticket)).toBeNull();
});

it('preserves a different record while canceling pre-deletion requests in that scope only', () => {
  const s = scope(),
    other = { ...s, workspaceId: 'b' };
  const h = renderHook(() => useChatState(s, 'a', 'result', null));
  act(() => h.result.current[1](answer('keep')));
  const old = historyToken(s),
    independent = historyToken(other);
  act(() => invalidateHistory(s, 'deleted'));
  expect(h.result.current[0].record.id).toBe('keep');
  expect(tokenCurrent(old)).toBe(false);
  expect(tokenCurrent(independent)).toBe(true);
});

it('bulk deletion invalidates old snapshots and delayed history while allowing new records', () => {
  const s = scope(),
    version = clearVersion(s);
  invalidateHistory(s);
  seed(s, { question: 'stale', result: answer('old') }, version);
  const h = renderHook(() => useChatState(s, 'a', 'result', null));
  expect(h.result.current[0]).toBeNull();
  expect(sessionStorage.getItem(key(s))).toBeNull();
  expect(filterHistory(s, [{ id: 'old' }], version)).toEqual([]);
  expect(filterHistory(s, [{ id: 'new' }], clearVersion(s))).toEqual([{ id: 'new' }]);
});

it('checks durable per-record tombstones during fresh hydration', () => {
  const s = scope();
  localStorage.setItem(`puchoo:history:v1:${s.tenantId}:a:record:old`, 'remote');
  seed(s, { question: 'old text', result: answer('old') });
  const h = renderHook(() => useChatState(s, 'a', 'question', ''));
  expect(h.result.current[0]).toBe('');
  expect(sessionStorage.getItem(key(s))).toBeNull();
});

it('consumes continuation once, requires full canonical scope and rejects deleted or cleared records', () => {
  const s = scope(),
    record = { id: 'old', question: 'original' };
  const ticket = makeContinuation(s, record);
  expect(consumeContinuation({ ...s, workspaceId: 'b' }, ticket)).toBeNull();
  expect(consumeContinuation({ ...s, userId: 'other' }, ticket)).toBeNull();
  expect(consumeContinuation({ ...s, role: 'viewer' }, ticket)).toBeNull();
  expect(consumeContinuation(s, ticket)).toEqual(ticket);
  expect(consumeContinuation(s, ticket)).toBeNull();
  const deleted = makeContinuation(s, record);
  invalidateHistory(s, 'old');
  expect(continuationMatches(s, deleted)).toBe(false);
  expect(makeContinuation(s, record)).toBeNull();
  const cleared = makeContinuation(s, { id: 'new', question: 'new' });
  invalidateHistory(s);
  expect(consumeContinuation(s, cleared)).toBeNull();
});

it('retains legitimate cached continuation on remount but not route-entry replay', () => {
  const s = scope(),
    ticket = makeContinuation(s, { id: 'old', question: 'original' });
  const first = renderHook(() => useChatState(s, 'a', 'continuation', null));
  act(() => first.result.current[1](consumeContinuation(s, ticket)));
  first.unmount();
  const next = renderHook(() => useChatState(s, 'a', 'continuation', null));
  expect(next.result.current[0].recordId).toBe('old');
  expect(consumeContinuation(s, ticket)).toBeNull();
});

it('handles cross-tab deletion events with the same tenant/workspace boundary', () => {
  const s = scope(),
    other = { ...s, workspaceId: 'b' };
  const h = renderHook(() => [
    useChatState(s, 'a', 'result', null),
    useChatState(other, 'b', 'result', null),
  ]);
  act(() => {
    h.result.current[0][1](answer('old'));
    h.result.current[1][1](answer('old'));
  });
  const journal = `puchoo:history:v1:${s.tenantId}:a:record:old`;
  act(() => {
    localStorage.setItem(journal, 'other-tab');
    window.dispatchEvent(new StorageEvent('storage', { key: journal, newValue: 'other-tab' }));
  });
  expect(h.result.current[0][0]).toBeNull();
  expect(h.result.current[1][0].record.id).toBe('old');
  expect(() =>
    window.dispatchEvent(
      new StorageEvent('storage', { key: 'puchoo:history:v1:%invalid:a:clear', newValue: 'x' }),
    ),
  ).not.toThrow();
});

it('logout invalidates in-flight tokens and old writers without deleting durable tombstones', () => {
  const s = scope(),
    token = historyToken(s);
  const h = renderHook(() => useChatState(s, 'a', 'question', ''));
  const late = h.result.current[1];
  act(() => clearChatSessions());
  act(() => late('stale'));
  expect(h.result.current[0]).toBe('');
  expect(tokenCurrent(token)).toBe(false);
});

it('fails closed for corrupt persisted results and untracked continuation payloads', () => {
  const s = scope();
  seed(s, { result: { record: { columns: [], rows: [] }, presentation: {} } });
  const h = renderHook(() => useChatState(s, 'a', 'result', null));
  expect(h.result.current[0]).toBeNull();
  expect(consumeContinuation(s, { scope: s, recordId: 'forged', version: '' })).toBeNull();
});

it('continues in memory if deletion journal writes fail and removes local old snapshots', () => {
  const s = scope();
  const h = renderHook(() => useChatState(s, 'a', 'result', null));
  act(() => h.result.current[1](answer('old')));
  const original = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (key, value) {
    if (this === localStorage) throw new DOMException('Full', 'QuotaExceededError');
    return original.call(this, key, value);
  });
  act(() => invalidateHistory(s, 'old'));
  expect(h.result.current[0]).toBeNull();
  expect(sessionStorage.getItem(key(s))).toBeNull();
  act(() => h.result.current[1](answer('new')));
  expect(h.result.current[0].record.id).toBe('new');
  expect(sessionStorage.getItem(key(s))).toBeNull();
});
