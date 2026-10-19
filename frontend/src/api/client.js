/**
 * API Client wrapper to handle CSRF tokens and common fetch patterns.
 */

// Basic cookie parser to get the CSRF token
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

export async function fetchApi(endpoint, options = {}) {
  const url = `/api${endpoint}`;
  const isFormData = options.body instanceof FormData;
  const headers = { ...options.headers };
  if (!isFormData) headers['Content-Type'] = 'application/json';

  // Attach CSRF token for mutating requests
  if (options.method && options.method !== 'GET') {
    const csrfToken = getCookie('csrf_token');
    if (csrfToken) {
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  const config = {
    ...options,
    headers,
    credentials: 'include',
  };

  try {
    const response = await fetch(url, config);

    // Handle no content
    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json')
      ? await response.json()
      : { detail: (await response.text()).trim() };

    if (!response.ok) {
      if (response.status === 401) {
        window.dispatchEvent(new Event('puchoo:unauthorized'));
      }
      throw new Error(data.detail || data.message || `API request failed (${response.status})`);
    }

    return data;
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}

export async function fetchApiBlob(endpoint, options = {}) {
  const url = `/api${endpoint}`;
  const isFormData = options.body instanceof FormData;
  const headers = { ...options.headers };
  if (!isFormData) headers['Content-Type'] = 'application/json';

  if (options.method && options.method !== 'GET') {
    const csrfToken = getCookie('csrf_token');
    if (csrfToken) headers['X-CSRF-Token'] = csrfToken;
  }

  try {
    const response = await fetch(url, { ...options, headers, credentials: 'include' });
    const contentType = response.headers.get('content-type') || '';

    if (!response.ok) {
      const data = contentType.includes('application/json')
        ? await response.json()
        : { detail: (await response.text()).trim() };
      if (response.status === 401) window.dispatchEvent(new Event('puchoo:unauthorized'));
      throw new Error(data.detail || data.message || `API request failed (${response.status})`);
    }

    if (!contentType.toLowerCase().startsWith('audio/wav')) {
      throw new Error('Speech service returned an invalid audio response.');
    }
    const audio = await response.blob();
    if (!audio.size) throw new Error('Speech service returned an invalid audio response.');
    return audio;
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}
