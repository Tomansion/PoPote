/**
 * Where the session token lives.
 *
 * localStorage, deliberately: it is the one store that behaves identically in
 * the browser and in the Android WebView, survives an app restart, and needs
 * no plugin. The token is long-lived (years) precisely so that this is all the
 * persistence the app needs — there is no refresh flow to run on startup.
 *
 * Kept in a module rather than in the Pinia store because api/client.js needs
 * it on every request, and importing the store there would make the two
 * modules import each other.
 */
const TOKEN_KEY = 'popote.token'
const USER_KEY = 'popote.user'

// Private browsing and locked-down WebViews can throw on access rather than
// simply returning null, which would take the whole app down on startup.
function safeGet(key) {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key)
    else window.localStorage.setItem(key, value)
  } catch {
    // A session that cannot be persisted still works for this run.
  }
}

export function readToken() {
  return safeGet(TOKEN_KEY)
}

export function writeToken(token) {
  safeSet(TOKEN_KEY, token)
}

/**
 * The last known profile, so the app can paint a signed-in shell before
 * `/auth/me` answers — or with no connection at all.
 */
export function readUser() {
  const raw = safeGet(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function writeUser(user) {
  safeSet(USER_KEY, user ? JSON.stringify(user) : null)
}

export function clearSession() {
  safeSet(TOKEN_KEY, null)
  safeSet(USER_KEY, null)
}
