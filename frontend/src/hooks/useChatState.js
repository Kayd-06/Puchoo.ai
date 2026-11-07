import { useCallback, useId, useSyncExternalStore } from 'react';

const prefix = 'puchoo:chat:v2:';
const journalPrefix = 'puchoo:history:v1:';
const ticketPrefix = 'puchoo:continuation:v1:';
const views = new Map();
const listeners = new Map();
const fallbackJournal = new Map();
const revision = new Map();
const conversations = new Map();
const subscribers = new Set();
const defaults = {
  question: '',
  questionLanguage: null,
  continuation: null,
  result: null,
  clarification: null,
  loading: false,
};
let persistenceBlocked = false;
let authEpoch = 0;

export function chatScope(user, workspaceId) {
  if (!user?.id || !workspaceId) return null;
  return {
    userId: user.id,
    tenantId: user.tenant_id || user.workspace_owner_id || user.institute_owner_id || user.id,
    role: user.role || user.workspace_role || 'owner',
    workspaceId,
  };
}
export function scopeKey(scope) {
  return scope
    ? [scope.userId, scope.tenantId, scope.role, scope.workspaceId]
        .map(encodeURIComponent)
        .join(':')
    : '';
}
const boundary = (scope) => [scope.tenantId, scope.workspaceId].map(encodeURIComponent).join(':');
const journalKey = (scope, recordId) =>
  `${journalPrefix}${boundary(scope)}:${recordId == null ? 'clear' : 'record:' + encodeURIComponent(recordId)}`;
function marker(key) {
  try {
    return localStorage.getItem(key) || fallbackJournal.get(key) || '';
  } catch {
    persistenceBlocked = true;
    return fallbackJournal.get(key) || '';
  }
}
export const clearVersion = (scope) => (scope ? marker(journalKey(scope, null)) : '');
export const recordDeleted = (scope, id) =>
  Boolean(scope && id && marker(journalKey(scope, String(id))));
const nonce = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
function valid(field, value) {
  if (field === 'question') return typeof value === 'string';
  if (field === 'questionLanguage') return value === null || typeof value === 'string';
  if (field === 'loading') return typeof value === 'boolean';
  if (value === null) return true;
  if (field === 'result')
    return (
      value &&
      typeof value.record?.id === 'string' &&
      Array.isArray(value.record?.columns) &&
      Array.isArray(value.record?.rows) &&
      value.presentation &&
      typeof value.presentation === 'object'
    );
  return value && typeof value === 'object' && !Array.isArray(value);
}
function removeKeys(test) {
  try {
    Object.keys(sessionStorage)
      .filter(test)
      .forEach((key) => sessionStorage.removeItem(key));
  } catch {
    persistenceBlocked = true;
  }
}
function sanitized(scope, values, savedVersion) {
  if (
    savedVersion !== clearVersion(scope) ||
    recordDeleted(scope, values.result?.record?.id) ||
    recordDeleted(scope, values.continuation?.recordId) ||
    (values.continuation && !continuationMatches(scope, values.continuation))
  )
    return { ...defaults };
  return values;
}
function view(key, scope) {
  if (!views.has(key)) {
    removeKeys((name) => name.startsWith('puchoo:chat:v1:'));
    let values = { ...defaults };
    const version = clearVersion(scope);
    if (scope && !persistenceBlocked) {
      try {
        const saved = JSON.parse(sessionStorage.getItem(prefix + key));
        if (saved?.version === version && saved.values) {
          for (const field of Object.keys(defaults))
            if (field !== 'loading' && valid(field, saved.values[field]))
              values[field] = saved.values[field];
          const clean = sanitized(scope, values, saved.version);
          if (clean !== values) sessionStorage.removeItem(prefix + key);
          values = clean;
        } else if (saved) {
          sessionStorage.removeItem(prefix + key);
        }
      } catch {
        /* Corrupt/blocked caches cannot block the workspace. */
      }
    }
    views.set(key, { key, scope, values, version, active: true });
  }
  return views.get(key);
}
function notify(key) {
  listeners.get(key)?.forEach((callback) => callback());
}
function persist(current) {
  if (!current.scope || persistenceBlocked) return;
  try {
    sessionStorage.setItem(
      prefix + current.key,
      JSON.stringify({ version: current.version, values: { ...current.values, loading: false } }),
    );
  } catch {
    /* Memory navigation still works without browser persistence. */
  }
}
function update(current, field, value, persistent) {
  if (!current.active) return;
  current.values = {
    ...current.values,
    [field]: typeof value === 'function' ? value(current.values[field]) : value,
  };
  if (persistent) persist(current);
  notify(current.key);
}
function applyInvalidation(scope, recordId) {
  const name = boundary(scope);
  revision.set(name, (revision.get(name) || 0) + 1);
  for (const [key, current] of views) {
    if (!current.scope || boundary(current.scope) !== name) continue;
    current.active = false; // Retire closures captured by requests before deletion.
    const affected =
      recordId == null ||
      current.values.result?.record?.id === recordId ||
      current.values.continuation?.recordId === recordId;
    const values = affected ? { ...defaults } : { ...current.values, loading: false };
    const next = { ...current, active: true, values, version: clearVersion(scope) };
    views.set(key, next);
    if (affected) removeKeys((item) => item === prefix + key);
    else persist(next);
    notify(key);
  }
  // Evict other role/account snapshots in this tab too, not just mounted stores.
  try {
    for (const key of Object.keys(sessionStorage).filter((item) => item.startsWith(prefix))) {
      const bits = key.slice(prefix.length).split(':').map(decodeURIComponent);
      if (bits[1] !== scope.tenantId || bits[3] !== scope.workspaceId) continue;
      const saved = JSON.parse(sessionStorage.getItem(key));
      if (
        recordId == null ||
        saved?.values?.result?.record?.id === recordId ||
        saved?.values?.continuation?.recordId === recordId
      )
        sessionStorage.removeItem(key);
    }
  } catch {
    persistenceBlocked = true;
  }
  try {
    for (const key of Object.keys(sessionStorage).filter((item) => item.startsWith(ticketPrefix))) {
      const ticket = JSON.parse(sessionStorage.getItem(key));
      const bits = ticket?.scope?.split(':').map(decodeURIComponent);
      if (
        bits?.[1] === scope.tenantId &&
        bits?.[3] === scope.workspaceId &&
        (recordId == null || ticket.recordId === recordId)
      )
        sessionStorage.removeItem(key);
    }
  } catch {
    persistenceBlocked = true;
  }
  subscribers.forEach((callback) => callback({ ...scope, recordId }));
}
export function invalidateHistory(scope, recordId = null) {
  if (!scope) return;
  const key = journalKey(scope, recordId),
    value = nonce();
  fallbackJournal.set(key, value);
  try {
    localStorage.setItem(key, value);
  } catch {
    persistenceBlocked = true;
  }
  applyInvalidation(scope, recordId);
}
const storageChanged = (event) => {
  if (!event.key?.startsWith(journalPrefix)) return;
  try {
    const [tenantId, workspaceId, kind, recordId] = event.key
      .slice(journalPrefix.length)
      .split(':')
      .map(decodeURIComponent);
    if (!tenantId || !workspaceId || !['clear', 'record'].includes(kind)) return;
    if (kind === 'record' && !recordId) return;
    if (event.newValue) fallbackJournal.set(event.key, event.newValue);
    applyInvalidation({ tenantId, workspaceId }, kind === 'clear' ? null : recordId);
  } catch {
    // Ignore malformed keys written by extensions or older clients.
  }
};
if (typeof window !== 'undefined') window.addEventListener('storage', storageChanged);
if (import.meta.hot)
  import.meta.hot.dispose(() => window.removeEventListener('storage', storageChanged));
export function subscribeHistoryInvalidation(callback) {
  subscribers.add(callback);
  return () => subscribers.delete(callback);
}
export function historyToken(scope) {
  return {
    scope,
    authEpoch,
    conversation: conversations.get(scopeKey(scope)) || 0,
    version: clearVersion(scope),
    revision: revision.get(boundary(scope)) || 0,
  };
}
export function tokenCurrent(token) {
  return (
    token &&
    token.authEpoch === authEpoch &&
    token.conversation === (conversations.get(scopeKey(token.scope)) || 0) &&
    token.version === clearVersion(token.scope) &&
    token.revision === (revision.get(boundary(token.scope)) || 0)
  );
}
export function filterHistory(scope, records, version) {
  return version !== clearVersion(scope)
    ? []
    : records.filter((record) => !recordDeleted(scope, record.id));
}

export function continuationMatches(scope, continuation) {
  return Boolean(
    scope &&
    continuation?.recordId &&
    scopeKey(scope) === scopeKey(continuation.scope) &&
    continuation.version === clearVersion(scope) &&
    !recordDeleted(scope, continuation.recordId),
  );
}
export function makeContinuation(scope, record) {
  if (!scope || !record?.id || recordDeleted(scope, record.id)) return null;
  const continuation = {
    scope,
    recordId: record.id,
    question: record.question,
    interpretedRequest: record.interpreted_request,
    rowCount: record.row_count,
    languageCode: record.language_code,
    version: clearVersion(scope),
    ticket: nonce(),
  };
  try {
    sessionStorage.setItem(
      ticketPrefix + continuation.ticket,
      JSON.stringify({ scope: scopeKey(scope), recordId: record.id }),
    );
  } catch {
    return null;
  } // No untracked history-entry replay if ticket storage is unavailable.
  return continuation;
}
export function consumeContinuation(scope, continuation) {
  if (!continuationMatches(scope, continuation)) return null;
  try {
    const key = ticketPrefix + continuation.ticket;
    const ticket = JSON.parse(sessionStorage.getItem(key));
    sessionStorage.removeItem(key); // One navigation ticket; cached scoped context may survive reload.
    return ticket?.scope === scopeKey(scope) && ticket.recordId === continuation.recordId
      ? continuation
      : null;
  } catch {
    return null;
  }
}
// A newly selected history conversation also retires older same-scope requests.
export function startContinuation(scope, continuation) {
  if (!continuationMatches(scope, continuation)) return;
  const key = scopeKey(scope),
    current = view(key, scope);
  conversations.set(key, (conversations.get(key) || 0) + 1);
  current.active = false;
  const next = {
    ...current,
    active: true,
    values: { ...defaults, continuation, questionLanguage: continuation.languageCode || null },
  };
  views.set(key, next);
  persist(next);
  notify(key);
}
export function clearChatSessions() {
  authEpoch += 1;
  for (const current of views.values()) current.active = false;
  views.clear();
  conversations.clear();
  removeKeys((key) => key.startsWith('puchoo:chat:') || key.startsWith(ticketPrefix));
  listeners.forEach((callbacks) => callbacks.forEach((callback) => callback()));
}

// String user IDs remain supported for isolated hook callers; production passes canonical scope.
export function useChatState(userOrScope, workspaceId, field, initial, persistValue = true) {
  const fallbackId = useId();
  const scope =
    typeof userOrScope === 'string' ? chatScope({ id: userOrScope }, workspaceId) : userOrScope;
  const key = scopeKey(scope) || `memory:${fallbackId}`;
  const current = view(key, scope);
  if (!(field in current.values)) current.values[field] = initial;
  const subscribe = useCallback(
    (callback) => {
      if (!listeners.has(key)) listeners.set(key, new Set());
      listeners.get(key).add(callback);
      return () => listeners.get(key)?.delete(callback);
    },
    [key],
  );
  const getSnapshot = useCallback(() => view(key, scope).values, [key, scope]);
  const snapshot = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const value = snapshot[field];
  const setter = useCallback(
    (next) => update(current, field, next, persistValue),
    [current, field, persistValue],
  );
  return [value, setter];
}
