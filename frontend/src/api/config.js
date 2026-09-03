// Resolved once, at build time, from VITE_API_URL.
//
// Web builds leave it unset and fall back to the same-origin "/api" path, which
// nginx (prod) or the Vite dev proxy (dev) forwards to FastAPI. The APK has no
// meaningful origin of its own — it runs from https://localhost — so its build
// must bake in an absolute URL.
const RAW_BASE = import.meta.env.VITE_API_URL || '/api'

export const API_BASE = RAW_BASE.replace(/\/+$/, '')

export const IS_ABSOLUTE_BASE = /^https?:\/\//i.test(API_BASE)

/**
 * Absolute ws:// or wss:// URL for the live feed.
 *
 * The token goes in the query string because a browser cannot set an
 * Authorization header on a WebSocket handshake. It is the same token the REST
 * calls send as a bearer header; only the transport differs.
 */
export function websocketUrl(token) {
  const base = IS_ABSOLUTE_BASE
    ? `${API_BASE.replace(/^http/i, 'ws')}/ws`
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${API_BASE}/ws`

  return token ? `${base}?token=${encodeURIComponent(token)}` : base
}

/**
 * Origin to build shareable links against (invite links, above all).
 *
 * `window.location.origin` is right on the web but wrong in the APK, where it
 * is `https://localhost` — a link built from it would be dead for whoever
 * received it. The APK build therefore bakes in the public web address; the
 * web build has no need to and falls back to its own origin.
 */
const RAW_WEB_URL = import.meta.env.VITE_PUBLIC_WEB_URL || ''

export const PUBLIC_WEB_ORIGIN = RAW_WEB_URL
  ? RAW_WEB_URL.replace(/\/+$/, '')
  : window.location.origin
