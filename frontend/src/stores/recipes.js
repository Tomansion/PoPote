import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError } from '@/api/client'
import { createLiveFeed } from '@/api/ws'
import { useAuthStore } from '@/stores/auth'
import { useEventsStore } from '@/stores/events'
import {
  readCachedRecipes,
  readLastSync,
  removeCached,
  replaceCache,
  upsertCached,
} from '@/db/cache'

export const RECIPE_TYPES = [
  'Entrée',
  'Plat',
  'Dessert',
  'Petit-déj.',
  'Apéritif',
  'Sauce/Base',
]

export const useRecipesStore = defineStore('recipes', () => {
  const recipes = ref([])
  const loading = ref(true)
  /** 'connecting' | 'live' | 'offline' */
  const connection = ref('connecting')
  const lastSync = ref(null)
  /** True while the list on screen came from the cache rather than the server. */
  const servedFromCache = ref(false)
  /** Whether the server has delivered a snapshot yet, by WebSocket or REST. */
  const hasServerData = ref(false)
  const toast = ref(null)

  // Form state lives here so the desktop drawer's "+ Nouvelle recette" button
  // and the detail panel's "Modifier" action drive the same dialog.
  const formOpen = ref(false)
  const editingRecipe = ref(null)

  const search = ref('')
  const sortDesc = ref(false)
  const filters = ref({
    type: null,
    temperature: null,
    maxMinutes: null,
    favoritesOnly: false,
  })

  let feed = null
  let fallbackTimer = null

  const handleOnline = () => feed?.reconnectNow()
  const handleVisibility = () => {
    if (document.visibilityState === 'visible') feed?.reconnectNow()
  }

  const isLive = computed(() => connection.value === 'live')

  const totalMinutes = (recipe) =>
    (recipe.prep_minutes || 0) + (recipe.cook_minutes || 0)

  const filteredRecipes = computed(() => {
    const term = search.value.trim().toLowerCase()
    const { type, temperature, maxMinutes, favoritesOnly } = filters.value

    return recipes.value
      .filter((recipe) => {
        if (type && recipe.type !== type) return false
        if (temperature && recipe.temperature !== temperature) return false
        if (maxMinutes && totalMinutes(recipe) > maxMinutes) return false
        if (favoritesOnly && !recipe.favorite) return false
        if (!term) return true

        const haystack = [
          recipe.name,
          recipe.type,
          recipe.notes,
          ...(recipe.ingredients || []).map((i) => i.name),
        ]
          .join(' ')
          .toLowerCase()
        return haystack.includes(term)
      })
      .sort((a, b) => {
        const order = a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' })
        return sortDesc.value ? -order : order
      })
  })

  const activeFilterCount = computed(() => {
    const { type, temperature, maxMinutes, favoritesOnly } = filters.value
    return [type, temperature, maxMinutes, favoritesOnly || null].filter(Boolean).length
  })

  function byId(id) {
    return recipes.value.find((recipe) => recipe.id === id) ?? null
  }

  function notify(message, color = 'error') {
    toast.value = { message, color, at: Date.now() }
  }

  function upsertLocal(recipe) {
    const index = recipes.value.findIndex((r) => r.id === recipe.id)
    if (index === -1) {
      recipes.value.push(recipe)
    } else {
      recipes.value[index] = recipe
    }
  }

  function removeLocal(id) {
    recipes.value = recipes.value.filter((recipe) => recipe.id !== id)
  }

  function handleEvent(event) {
    // One socket carries both streams. Events are handed to their own store,
    // so there is a single connection and a single `hello` to resync from.
    if (event.type === 'hello' || event.type.startsWith('event.')) {
      useEventsStore().handleEvent(event)
      if (event.type !== 'hello') return
    }

    switch (event.type) {
      case 'hello':
        // Sent on every (re)connect: a full snapshot, so it is also the resync.
        recipes.value = event.recipes ?? []
        servedFromCache.value = false
        hasServerData.value = true
        loading.value = false
        lastSync.value = new Date().toISOString()
        replaceCache(recipes.value)
        break
      case 'recipe.created':
      case 'recipe.updated':
        if (event.recipe) {
          upsertLocal(event.recipe)
          lastSync.value = new Date().toISOString()
          upsertCached(event.recipe)
        }
        break
      case 'recipe.deleted':
        if (event.recipe_id) {
          removeLocal(event.recipe_id)
          lastSync.value = new Date().toISOString()
          removeCached(event.recipe_id)
        }
        break
    }
  }

  /** REST fallback, used when the WebSocket cannot be established. */
  async function refresh() {
    try {
      const fresh = await api.listRecipes()
      recipes.value = fresh
      servedFromCache.value = false
      hasServerData.value = true
      lastSync.value = new Date().toISOString()
      await replaceCache(fresh)
      return true
    } catch {
      return false
    }
  }

  async function init() {
    const events = useEventsStore()

    // 1. Paint from cache first so the list is usable before any network I/O.
    const [cached, cachedSync] = await Promise.all([
      readCachedRecipes(),
      readLastSync(),
      events.initFromCache(),
    ])
    if (cached.length) {
      recipes.value = cached
      servedFromCache.value = true
      lastSync.value = cachedSync
      loading.value = false
    }

    // 2. Then open the live feed, whose `hello` event replaces the snapshot.
    feed = createLiveFeed({
      onEvent: handleEvent,
      onStatus: (status) => {
        connection.value = status
        if (status === 'offline') loading.value = false
      },
      // The server refused the token on the handshake. Reconnecting cannot
      // help, so end the session instead of retrying behind the backoff.
      onUnauthorized: () => useAuthStore().signOut(),
    })
    feed.start()

    // 3. If the socket has not delivered a snapshot shortly, try plain HTTP —
    //    some proxies allow REST while blocking WebSocket upgrades.
    fallbackTimer = setTimeout(async () => {
      if (!hasServerData.value) {
        const [reached] = await Promise.all([refresh(), events.refresh()])
        // A failed HTTP call is a much faster offline signal than waiting for
        // the WebSocket to give up, which can take ~10s behind a proxy whose
        // upstream is down. If the socket does come up later it corrects this.
        if (!reached && connection.value !== 'live') connection.value = 'offline'
      }
      loading.value = false
    }, 3000)

    window.addEventListener('online', handleOnline)
    document.addEventListener('visibilitychange', handleVisibility)
  }

  /** Drop everything held in memory. Called when signing out. */
  function reset() {
    stop()
    recipes.value = []
    loading.value = true
    connection.value = 'connecting'
    lastSync.value = null
    servedFromCache.value = false
    hasServerData.value = false
    formOpen.value = false
    editingRecipe.value = null
    resetFilters()
    useEventsStore().reset()
  }

  function stop() {
    if (fallbackTimer) clearTimeout(fallbackTimer)
    fallbackTimer = null
    window.removeEventListener('online', handleOnline)
    document.removeEventListener('visibilitychange', handleVisibility)
    feed?.stop()
    feed = null
  }

  async function createRecipe(payload) {
    try {
      const created = await api.createRecipe(payload)
      // The broadcast normally arrives first; upserting is idempotent.
      upsertLocal(created)
      await upsertCached(created)
      notify('Recette ajoutée', 'success')
      return created
    } catch (error) {
      notify(errorMessage(error, "Impossible d'ajouter la recette"))
      throw error
    }
  }

  async function updateRecipe(id, payload) {
    try {
      const updated = await api.updateRecipe(id, payload)
      upsertLocal(updated)
      await upsertCached(updated)
      notify('Recette enregistrée', 'success')
      return updated
    } catch (error) {
      notify(errorMessage(error, 'Impossible d’enregistrer la recette'))
      throw error
    }
  }

  async function deleteRecipe(id) {
    try {
      await api.deleteRecipe(id)
      removeLocal(id)
      await removeCached(id)
      notify('Recette supprimée', 'success')
    } catch (error) {
      notify(errorMessage(error, 'Impossible de supprimer la recette'))
      throw error
    }
  }

  async function toggleFavorite(recipe) {
    const { id, created_at, updated_at, ...rest } = recipe
    return updateRecipe(id, { ...rest, favorite: !recipe.favorite })
  }

  function errorMessage(error, fallback) {
    if (error instanceof ApiError && error.status === 0) {
      return 'Hors ligne : modification impossible pour le moment'
    }
    return error instanceof ApiError ? error.message : fallback
  }

  function openCreateForm() {
    editingRecipe.value = null
    formOpen.value = true
  }

  function openEditForm(recipe) {
    editingRecipe.value = recipe
    formOpen.value = true
  }

  function resetFilters() {
    search.value = ''
    sortDesc.value = false
    filters.value = {
      type: null,
      temperature: null,
      maxMinutes: null,
      favoritesOnly: false,
    }
  }

  return {
    recipes,
    loading,
    connection,
    isLive,
    lastSync,
    servedFromCache,
    toast,
    formOpen,
    editingRecipe,
    openCreateForm,
    openEditForm,
    search,
    sortDesc,
    filters,
    filteredRecipes,
    activeFilterCount,
    byId,
    totalMinutes,
    init,
    stop,
    reset,
    refresh,
    createRecipe,
    updateRecipe,
    deleteRecipe,
    toggleFavorite,
    resetFilters,
  }
})
