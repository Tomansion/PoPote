import { API_BASE } from './config'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Without a deadline a request can hang for as long as the OS and any proxy in
// front of the API allow — a reverse proxy whose upstream is down will happily
// hold the connection. On a phone that shows up as a spinner that never ends.
const DEFAULT_TIMEOUT_MS = 8000

async function request(path, { timeoutMs = DEFAULT_TIMEOUT_MS, ...options } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(timeoutMs),
      ...options,
    })
  } catch (cause) {
    // Unreachable, timed out, DNS failure, backend down, or CORS refusal.
    throw new ApiError('Serveur injoignable', 0)
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
