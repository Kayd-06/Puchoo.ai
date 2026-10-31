import { useCallback, useId, useSyncExternalStore } from 'react';

const prefix = 'puchoo:chat:v1:';
const cells = new Map();

function valid(field, value) {
  if (field === 'question') return typeof value === 'string';
  if (field === 'questionLanguage') return value === null || typeof value === 'string';
  if (field === 'loading') return typeof value === 'boolean';
  if (value === null) return true;
  if (field === 'result') {
    return (
      value &&
      typeof value === 'object' &&
      value.record &&
      Array.isArray(value.record.columns) &&
      Array.isArray(value.record.rows) &&
      value.presentation &&
      typeof value.presentation === 'object'
    );
  }
  return value && typeof value === 'object' && !Array.isArray(value);
}

function getCell(key, field, initial, persistent) {
  if (!cells.has(key)) {
    let value = initial;
    if (persistent) {
      try {
        const saved = JSON.parse(window.sessionStorage.getItem(key));
        if (saved && valid(field, saved.value)) value = saved.value;
      } catch {
        // A corrupt entry or restricted storage must not block the workspace.
      }
    }
    cells.set(key, { value, initial, persistent, active: true, listeners: new Set() });
  }
  return cells.get(key);
}

export function clearChatSessions() {
  for (const cell of cells.values()) {
    cell.active = false;
    cell.value = cell.initial;
    cell.listeners.forEach((notify) => notify());
  }
  cells.clear();
  try {
    const keys = Object.keys(window.sessionStorage).filter((key) => key.startsWith(prefix));
    keys.forEach((key) => window.sessionStorage.removeItem(key));
  } catch {
    // Memory is still cleared when storage is restricted.
  }
}

function updateCell(cell, key, update) {
  // A request completing after logout must never recreate cleared data.
  if (!cell.active) return;
  cell.value = typeof update === 'function' ? update(cell.value) : update;
  if (cell.persistent) {
    try {
      window.sessionStorage.setItem(key, JSON.stringify({ value: cell.value }));
    } catch {
      // In-memory state survives navigation even when storage is full.
    }
  }
  cell.listeners.forEach((notify) => notify());
}

export function useChatState(userId, workspaceId, field, initial, persist = true) {
  const fallbackId = useId();
  const persistent = Boolean(userId && workspaceId && persist);
  const key =
    userId && workspaceId
      ? `${prefix}${encodeURIComponent(userId)}:${encodeURIComponent(workspaceId)}:${field}`
      : `memory:${fallbackId}:${field}`;
  const cell = getCell(key, field, initial, persistent);
  const subscribe = useCallback(
    (notify) => {
      cell.listeners.add(notify);
      return () => cell.listeners.delete(notify);
    },
    [cell],
  );
  const getSnapshot = useCallback(() => cell.value, [cell]);
  const value = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  const setValue = useCallback((update) => updateCell(cell, key, update), [cell, key]);
  return [value, setValue];
}
