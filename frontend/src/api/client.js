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
  // A file upload must be left alone: the browser sets `multipart/form-data`
  // *plus the boundary* itself, and a hand-written Content-Type header has no
  // boundary in it, so the server sees a body it cannot parse.
  const isUpload = options.body instanceof FormData

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      signal: AbortSignal.timeout(timeoutMs),
      ...options,
      // Merged after the spread so a caller's headers cannot drop the token.
      headers: {
        ...(isUpload ? {} : { 'Content-Type': 'application/json' }),
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
  // Someone else's page. 404 unless you share an event with them, which is
  // the same rule their recipes follow.
  userProfile: (id) => request(`/users/${id}`),

  // --- events
  listEvents: () => request('/events'),
  createEvent: (payload) =>
    request('/events', { method: 'POST', body: JSON.stringify(payload) }),
  updateEvent: (id, payload) =>
    request(`/events/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteEvent: (id) => request(`/events/${id}`, { method: 'DELETE' }),
  leaveEvent: (id) => request(`/events/${id}/leave`, { method: 'POST' }),

  // --- planner. Every member may write, so each call returns the whole plan
  // and the same plan is pushed to the other members over the socket.
  eventRecipes: (id) => request(`/events/${id}/recipes`),
  getPlan: (id) => request(`/events/${id}/plan`),
  setPlanSlot: (id, day, slot, payload) =>
    request(`/events/${id}/plan/${day}/${slot}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  movePlanMeals: (id, payload) =>
    request(`/events/${id}/plan/move`, { method: 'POST', body: JSON.stringify(payload) }),
  // Who is on duty for a whole day, as opposed to who cooks one dish — that
  // one rides along inside the slot itself.
  setPlanDayCooks: (id, day, cooks) =>
    request(`/events/${id}/plan/${day}/cooks`, {
      method: 'PUT',
      body: JSON.stringify({ cooks }),
    }),

  // --- grocery lists
  listGroceryLists: () => request('/grocery-lists'),
  // Generation now includes one LLM pass that merges the lines naming the same
  // ingredient, so this is no longer a purely local computation — the deadline
  // is the model's, not the database's.
  generateGroceryList: (eventId) =>
    request(`/events/${eventId}/grocery-list`, { method: 'POST', timeoutMs: 60000 }),
  // One call for one line, one rayon or one recipe: the page knows which keys
  // each of those covers. Members only — ticking is public, deciding who goes
  // and gets it is not.
  assignGroceryItems: (eventId, keys, assignees) =>
    request(`/events/${eventId}/grocery-list/assign`, {
      method: 'POST',
      body: JSON.stringify({ keys, assignees }),
    }),
  // One LLM call over the whole list, which is well past the default deadline.
  priceGroceryList: (eventId) =>
    request(`/events/${eventId}/grocery-list/prices`, { method: 'POST', timeoutMs: 90000 }),
  // The shared link: no token, and none needed — whoever holds the code reads
  // the list and ticks its boxes.
  publicGroceryList: (code) =>
    request(`/public/grocery-lists/${encodeURIComponent(code)}`, { auth: false }),
  checkGroceryItem: (code, key, checked) =>
    request(`/public/grocery-lists/${encodeURIComponent(code)}/items/${key}`, {
      method: 'PATCH',
      body: JSON.stringify({ checked }),
      auth: false,
    }),

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
  // A photo off a phone is megabytes over whatever connection is to hand, and
  // the server resizes it before answering — well past the 8s default, which
  // is meant for a slow network rather than a request still doing real work.
  uploadRecipeImage: (id, file) => {
    const body = new FormData()
    body.append('file', file)
    return request(`/recipes/${id}/image`, { method: 'POST', body, timeoutMs: 60000 })
  },
  deleteRecipeImage: (id) => request(`/recipes/${id}/image`, { method: 'DELETE' }),
  listAisles: () => request('/aisles'),
  detectAisle: (name) => request(`/aisles/detect?name=${encodeURIComponent(name)}`),
  health: () => request('/health'),
}
