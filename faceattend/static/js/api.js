const TOKEN_KEY = 'faceattend.token';

export class AuthError extends Error {}
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

/** The admin token lives in sessionStorage, so it is forgotten when the tab closes. */
export const auth = {
  get token() {
    try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
  },
  set token(value) {
    try {
      if (value) sessionStorage.setItem(TOKEN_KEY, value);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch { /* storage unavailable: the token just won't be remembered */ }
  },
};

async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join('; ');
  } catch { /* not JSON */ }
  return `Request failed (${response.status}).`;
}

export async function request(path, { admin = false, ...options } = {}) {
  const headers = new Headers(options.headers || {});
  if (admin && auth.token) headers.set('X-Admin-Token', auth.token);
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch {
    throw new ApiError('Cannot reach the server.', 0);
  }
  if (response.status === 401) {
    auth.token = '';
    throw new AuthError('Admin token required.');
  }
  if (!response.ok) throw new ApiError(await errorMessage(response), response.status);
  return response;
}

export async function getJson(path, options) {
  return (await request(path, options)).json();
}
