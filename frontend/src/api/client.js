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
      throw new Error(data.detail || data.message || `API request failed (${response.status})`);
    }

    return data;
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}
