import { websocketUrl } from './config'

const INITIAL_RETRY_MS = 1000
const MAX_RETRY_MS = 20000
const PING_INTERVAL_MS = 25000

/**
 * Self-reconnecting WebSocket to the live recipe feed.
 *
 * Reconnection matters more than usual here: an APK is backgrounded and
 * resumed constantly, and each resume drops the socket. On every (re)connect
 * the server replays the full list in a `hello` event, so a reconnect doubles
 * as a resync — the client never has to reason about what it missed.
 */
export function createLiveFeed({ onEvent, onStatus }) {
  let socket = null
  let retryDelay = INITIAL_RETRY_MS
  let retryTimer = null
  let pingTimer = null
  let closedByUs = false

  let lastStatus = null

  function setStatus(status) {
    // Once offline, stay offline until a connection actually succeeds. Each
    // backoff tick would otherwise flip the indicator back to "connexion…",
    // so a user with no connection sees it flickering instead of a steady
    // "dispo hors-ligne".
    if (status === 'connecting' && lastStatus === 'offline') return
    if (status === lastStatus) return
    lastStatus = status
    onStatus?.(status)
  }

  function clearTimers() {
    if (retryTimer) clearTimeout(retryTimer)
    if (pingTimer) clearInterval(pingTimer)
    retryTimer = null
    pingTimer = null
  }

  function scheduleReconnect() {
    if (closedByUs || retryTimer) return
    retryTimer = setTimeout(() => {
      retryTimer = null
      connect()
    }, retryDelay)
    retryDelay = Math.min(retryDelay * 2, MAX_RETRY_MS)
  }

  function connect() {
    if (closedByUs || socket) return
    setStatus('connecting')

    try {
      socket = new WebSocket(websocketUrl())
    } catch {
      setStatus('offline')
      scheduleReconnect()
      return
    }

    socket.onopen = () => {
      retryDelay = INITIAL_RETRY_MS
      setStatus('live')
      pingTimer = setInterval(() => {
        if (socket?.readyState === WebSocket.OPEN) socket.send('ping')
      }, PING_INTERVAL_MS)
    }

    socket.onmessage = (message) => {
      let payload
      try {
        payload = JSON.parse(message.data)
      } catch {
        return
      }
      if (payload?.type === 'pong') return
      onEvent?.(payload)
    }

    socket.onerror = () => {
      // `onclose` always follows, which is where reconnection is handled.
    }

    socket.onclose = () => {
      if (pingTimer) clearInterval(pingTimer)
      pingTimer = null
      socket = null
      if (!closedByUs) {
        setStatus('offline')
        scheduleReconnect()
      }
    }
  }

  function start() {
    closedByUs = false
    connect()
  }

  function stop() {
    closedByUs = true
    clearTimers()
    socket?.close()
    socket = null
    setStatus('offline')
  }

  /** Force an immediate reconnect, e.g. when the OS reports the network is back.
   *
   * Skipped while a socket is open *or still connecting*: on Android this is
   * called on every resume, and starting a second socket over an in-flight one
   * would orphan the first, whose later `onclose` would queue yet another
   * reconnect. */
  function reconnectNow() {
    if (
      socket &&
      (socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    clearTimers()
    retryDelay = INITIAL_RETRY_MS
    connect()
  }

  return { start, stop, reconnectNow }
}
