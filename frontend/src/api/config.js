// Resolved once, at build time, from VITE_API_URL.
//
// Web builds leave it unset and fall back to the same-origin "/api" path, which
// nginx (prod) or the Vite dev proxy (dev) forwards to FastAPI. The APK has no
// meaningful origin of its own — it runs from https://localhost — so its build
// must bake in an absolute URL.
const RAW_BASE = import.meta.env.VITE_API_URL || '/api'

export const API_BASE = RAW_BASE.replace(/\/+$/, '')

export const IS_ABSOLUTE_BASE = /^https?:\/\//i.test(API_BASE)

/** Absolute ws:// or wss:// URL for the live recipe feed. */
export function websocketUrl() {
  if (IS_ABSOLUTE_BASE) {
    return `${API_BASE.replace(/^http/i, 'ws')}/ws`
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${API_BASE}/ws`
}
