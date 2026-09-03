import { API_BASE } from './config'
import { readToken } from './session'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Called whenever the API rejects the stored token.
 *
 * The auth store registers itself here at startup. It is a callback rather
 * than a direct import because the store imports this module, and having the
 * two import each other would be a cycle.
 */
let onUnauthorized = null

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler
}

// Without a deadline a request can hang for as long as the OS and any proxy in
// front of the API allow — a reverse proxy whose upstream is down will happily
// hold the connection. On a phone that shows up as a spinner that never ends.
const DEFAULT_TIMEOUT_MS = 8000

async function request(path, { timeoutMs = DEFAULT_TIMEOUT_MS, auth = true, ...options } = {}) {
  const token = auth ? readToken() : null

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      signal: AbortSignal.timeout(timeoutMs),
      ...options,
      // Merged after the spread so a caller's headers cannot drop the token.
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    })
  } catch (cause) {
    // Unreachable, timed out, DNS failure, backend down, or CORS refusal.
    throw new ApiError('Serveur injoignable', 0)
  }

  // An expired or revoked token: drop the session and send the user to the
  // login screen rather than letting every subsequent call fail silently.
  if (response.status === 401 && auth) {
    onUnauthorized?.()
  }

  if (!response.ok) {
    let detail = `Erreur ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // Response had no JSON body; the status-based message is good enough.
    }
    throw new ApiError(detail, response.status)
  }

  if (response.status === 204) return null
  return response.json()
}

export const api = {
  // --- auth. `auth: false` on the two endpoints that run without a token.
  register: (payload) =>
    request('/auth/register', { method: 'POST', body: JSON.stringify(payload), auth: false }),
  login: (payload) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify(payload), auth: false }),
  me: () => request('/auth/me'),
  updateProfile: (payload) =>
    request('/auth/me', { method: 'PUT', body: JSON.stringify(payload) }),

  // --- events
  listEvents: () => request('/events'),
  createEvent: (payload) =>
    request('/events', { method: 'POST', body: JSON.stringify(payload) }),
  updateEvent: (id, payload) =>
    request(`/events/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteEvent: (id) => request(`/events/${id}`, { method: 'DELETE' }),
  leaveEvent: (id) => request(`/events/${id}/leave`, { method: 'POST' }),

  // --- invites
  previewInvite: (code) => request(`/invites/${encodeURIComponent(code)}`),
  joinInvite: (code) =>
    request(`/invites/${encodeURIComponent(code)}/join`, { method: 'POST' }),

  // --- recipes
  listRecipes: () => request('/recipes'),
  getRecipe: (id) => request(`/recipes/${id}`),
  createRecipe: (recipe) =>
    request('/recipes', { method: 'POST', body: JSON.stringify(recipe) }),
  updateRecipe: (id, recipe) =>
    request(`/recipes/${id}`, { method: 'PUT', body: JSON.stringify(recipe) }),
  deleteRecipe: (id) => request(`/recipes/${id}`, { method: 'DELETE' }),
  listAisles: () => request('/aisles'),
  detectAisle: (name) => request(`/aisles/detect?name=${encodeURIComponent(name)}`),
  health: () => request('/health'),
}
