/**
 * Single HTTP boundary for the app.
 *
 * Responsibilities:
 *   - inject the bearer token
 *   - unwrap the API's error envelope into a typed ApiError carrying `code`
 *   - sign the user out on an expired/invalid session
 *
 * The `code` matters: pages branch on SLOT_ALREADY_BOOKED to explain a lost booking
 * race specifically, rather than showing a generic failure.
 */

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1'

const TOKEN_KEY = 'abs.token'

export class ApiError extends Error {
  constructor(message, { code = 'UNKNOWN', status = 0, details = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.details = details
  }
}

export const tokenStore = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY)
    } catch {
      return null
    }
  },
  set(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token)
    } catch {
      /* private mode — the session just will not persist across reloads */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY)
    } catch {
      /* ignore */
    }
  },
}

let unauthorizedHandler = null

/** Registered by AuthContext so a 401 anywhere logs the user out once, centrally. */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

function buildUrl(path, params) {
  const url = `${BASE_URL}${path}`
  if (!params) return url
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.append(key, String(value))
  }
  const query = search.toString()
  return query ? `${url}?${query}` : url
}

export async function apiFetch(
  path,
  { method = 'GET', body, params, auth = true, form = false } = {},
) {
  const headers = {}
  if (auth) {
    const token = tokenStore.get()
    if (token) headers.Authorization = `Bearer ${token}`
  }

  let payload
  if (form) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded'
    payload = new URLSearchParams(body).toString()
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(buildUrl(path, params), { method, headers, body: payload })
  } catch (cause) {
    // fetch only rejects on network-level failure, so this is genuinely "no server".
    throw new ApiError(
      'Could not reach the server. Is the API running on port 8000?',
      { code: 'NETWORK_ERROR', status: 0 },
    )
  }

  if (response.status === 204) return null

  const raw = await response.text()
  let parsed = null
  if (raw) {
    try {
      parsed = JSON.parse(raw)
    } catch {
      parsed = null
    }
  }

  if (response.ok) return parsed

  const envelope = parsed?.error ?? {}
  const error = new ApiError(
    envelope.message || `Request failed (${response.status}).`,
    {
      code: envelope.code || 'UNKNOWN',
      status: response.status,
      details: envelope.details ?? null,
    },
  )

  // An invalid or expired session is not a page-level problem — drop it globally.
  if (
    response.status === 401 &&
    ['TOKEN_INVALID', 'NOT_AUTHENTICATED'].includes(error.code)
  ) {
    tokenStore.clear()
    if (unauthorizedHandler) unauthorizedHandler(error)
  }

  throw error
}

export const api = {
  get: (path, params) => apiFetch(path, { params }),
  post: (path, body, params) => apiFetch(path, { method: 'POST', body, params }),
  patch: (path, body) => apiFetch(path, { method: 'PATCH', body }),
  delete: (path) => apiFetch(path, { method: 'DELETE' }),
}
