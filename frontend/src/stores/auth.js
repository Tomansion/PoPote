import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError, setUnauthorizedHandler } from '@/api/client'
import { clearSession, readToken, readUser, writeToken, writeUser } from '@/api/session'
import { clearCache } from '@/db/cache'

/** A fresh avatar seed. The range keeps it well inside the backend's bound. */
export function randomAvatarSeed() {
  return Math.floor(Math.random() * 1_000_000_000)
}

export const useAuthStore = defineStore('auth', () => {
  // Seeded straight from localStorage so the very first render already knows
  // whether it is showing a signed-in app — no flash of the login screen on
  // every launch, which on a phone is the difference between "my app" and
  // "a website I have to log into".
  const user = ref(readUser())
  const token = ref(readToken())
  /** True until the stored token has been checked against the server. */
  const restoring = ref(Boolean(readToken()))
  const busy = ref(false)
  const error = ref(null)

  const isAuthenticated = computed(() => Boolean(token.value))

  function persist(payload) {
    token.value = payload.token
    user.value = payload.user
    writeToken(payload.token)
    writeUser(payload.user)
  }

  async function signOut() {
    token.value = null
    user.value = null
    clearSession()
    // Recipes are private, so the offline mirror must not outlive the session.
    await clearCache()
  }

  /**
   * Validate the stored token, if there is one.
   *
   * A rejected token is dropped. A network failure is *not*: the app stays
   * signed in and works from the cache, which is the whole point of a token
   * that does not need the server to stay valid.
   */
  async function restore() {
    if (!token.value) {
      restoring.value = false
      return
    }
    try {
      const fresh = await api.me()
      user.value = fresh
      writeUser(fresh)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await signOut()
      }
      // Offline: keep the cached profile and carry on.
    } finally {
      restoring.value = false
    }
  }

  async function login(email, password) {
    busy.value = true
    error.value = null
    try {
      persist(await api.login({ email, password }))
      return true
    } catch (err) {
      error.value = messageFor(err)
      return false
    } finally {
      busy.value = false
    }
  }

  async function register({ email, password, displayName, avatarSeed }) {
    busy.value = true
    error.value = null
    try {
      persist(
        await api.register({
          email,
          password,
          display_name: displayName,
          avatar_seed: avatarSeed,
        }),
      )
      return true
    } catch (err) {
      error.value = messageFor(err)
      return false
    } finally {
      busy.value = false
    }
  }

  /** Save a rerolled avatar seed, or a new display name. */
  async function updateProfile({ displayName, avatarSeed }) {
    const payload = {}
    if (displayName !== undefined) payload.display_name = displayName
    if (avatarSeed !== undefined) payload.avatar_seed = avatarSeed

    const previous = user.value
    // Applied locally first: rerolling an avatar should feel instant.
    user.value = {
      ...previous,
      ...(displayName !== undefined ? { display_name: displayName } : {}),
      ...(avatarSeed !== undefined ? { avatar_seed: avatarSeed } : {}),
    }
    try {
      const fresh = await api.updateProfile(payload)
      user.value = fresh
      writeUser(fresh)
      return true
    } catch {
      user.value = previous
      return false
    }
  }

  function messageFor(err) {
    if (err instanceof ApiError) {
      if (err.status === 0) return 'Serveur injoignable'
      if (err.status === 422) return 'Vérifiez les informations saisies'
      return err.message
    }
    return 'Une erreur est survenue'
  }

  return {
    user,
    token,
    isAuthenticated,
    restoring,
    busy,
    error,
    restore,
    login,
    register,
    updateProfile,
    signOut,
  }
})

/**
 * Wire the API client's 401 hook to the store.
 *
 * Lives outside the store so it runs once, at app startup, rather than on
 * every `useAuthStore()` call.
 */
export function installUnauthorizedHandler(router) {
  setUnauthorizedHandler(async () => {
    const store = useAuthStore()
    if (!store.isAuthenticated) return
    await store.signOut()
    router.push({ name: 'login' })
  })
}
