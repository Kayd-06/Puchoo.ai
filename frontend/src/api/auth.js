function getCookie(name) {
  const prefix = `${name}=`;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function messageFrom(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === 'string') return data.detail;
  if (Array.isArray(data.detail)) {
    const text = data.detail
      .map((item) =>
        typeof item?.msg === 'string' ? item.msg.replace(/^Value error,\s*/, '') : '',
      )
      .filter(Boolean)
      .join(' ');
    if (text) return text;
  }
  return fallback;
}

export async function ensureCsrf() {
  const existing = getCookie('csrf_token');
  if (existing) return existing;
  await fetch('/api/v1/auth/csrf', { credentials: 'include' });
  return getCookie('csrf_token');
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && method !== 'HEAD') {
    const token = await ensureCsrf();
    if (token) headers['X-CSRF-Token'] = token;
  }

  let response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError('Unable to reach the server.', 0);
  }

  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  const data = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    throw new ApiError(messageFrom(data, 'Something went wrong.'), response.status);
  }
  return data;
}

export function login(payload) {
  return api('/api/v1/auth/login', { method: 'POST', body: payload });
}

export function verifyLogin(payload) {
  return api('/api/v1/auth/login/verify', { method: 'POST', body: payload });
}

export function signup(payload) {
  return api('/api/v1/auth/signup', { method: 'POST', body: payload });
}

export function logout() {
  return api('/api/v1/auth/logout', { method: 'POST' });
}
