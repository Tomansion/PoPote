import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError } from '@/api/client'
import { PUBLIC_WEB_ORIGIN } from '@/api/config'
import {
  readCachedEvents,
  removeCachedEvent,
  replaceEventCache,
  upsertCachedEvent,
} from '@/db/cache'

/**
 * Build the link that gets shared.
 *
 * Always against the public web origin, never `window.location.origin`: inside
 * the APK the latter is `https://localhost`, so the recipient would get a link
 * that resolves to their own device and goes nowhere.
 */
export function inviteLink(code) {
  return `${PUBLIC_WEB_ORIGIN}/join/${code}`
}

function startOfToday() {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

export const useEventsStore = defineStore('events', () => {
  const events = ref([])
  const loading = ref(true)
  const toast = ref(null)

  const formOpen = ref(false)
  const editingEvent = ref(null)

  function notify(message, color = 'error') {
    toast.value = { message, color, at: Date.now() }
  }

  const sorted = computed(() =>
    [...events.value].sort(
      (a, b) =>
        a.starts_on.localeCompare(b.starts_on) ||
        a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' }),
    ),
  )

  /** Anything not finished yet, including one running right now. */
  const upcoming = computed(() => {
    const today = startOfToday()
    return sorted.value.filter((event) => new Date(event.ends_on) >= today)
  })

  const past = computed(() => {
    const today = startOfToday()
    return sorted.value.filter((event) => new Date(event.ends_on) < today).reverse()
  })

  function byId(id) {
    return events.value.find((event) => event.id === id) ?? null
  }

  function upsertLocal(event) {
    const index = events.value.findIndex((e) => e.id === event.id)
    if (index === -1) events.value.push(event)
    else events.value[index] = event
  }

  function removeLocal(id) {
    events.value = events.value.filter((event) => event.id !== id)
  }

  /**
   * Apply an event that arrived over the WebSocket.
   *
   * Called by the recipes store, which owns the single socket: one connection
   * carries both recipes and events, so there is one `hello` to resync from.
   */
  function handleEvent(message) {
    switch (message.type) {
      case 'hello':
        events.value = message.events ?? []
        loading.value = false
        replaceEventCache(events.value)
        break
      case 'event.created':
      case 'event.updated':
        if (message.event) {
          upsertLocal(message.event)
          upsertCachedEvent(message.event)
        }
        break
      case 'event.deleted':
        if (message.event_id) {
          removeLocal(message.event_id)
          removeCachedEvent(message.event_id)
        }
        break
    }
  }

  /** Paint from cache, so the planner is readable with no connection. */
  async function initFromCache() {
    const cached = await readCachedEvents()
    if (cached.length && !events.value.length) {
      events.value = cached
      loading.value = false
    }
  }

  /** REST fallback for when the WebSocket never comes up. */
  async function refresh() {
    try {
      events.value = await api.listEvents()
      loading.value = false
      await replaceEventCache(events.value)
      return true
    } catch {
      return false
    }
  }

  function reset() {
    events.value = []
    loading.value = true
    formOpen.value = false
    editingEvent.value = null
  }

  async function createEvent(payload) {
    try {
      const created = await api.createEvent(payload)
      upsertLocal(created)
      await upsertCachedEvent(created)
      notify('Événement créé', 'success')
      return created
    } catch (error) {
      notify(errorMessage(error, "Impossible de créer l'événement"))
      throw error
    }
  }

  async function updateEvent(id, payload) {
    try {
      const updated = await api.updateEvent(id, payload)
      upsertLocal(updated)
      await upsertCachedEvent(updated)
      notify('Événement enregistré', 'success')
      return updated
    } catch (error) {
      notify(errorMessage(error, "Impossible d'enregistrer l'événement"))
      throw error
    }
  }

  async function deleteEvent(id) {
    try {
      await api.deleteEvent(id)
      removeLocal(id)
      await removeCachedEvent(id)
      notify('Événement supprimé', 'success')
    } catch (error) {
      notify(errorMessage(error, "Impossible de supprimer l'événement"))
      throw error
    }
  }

  async function leaveEvent(id) {
    try {
      await api.leaveEvent(id)
      removeLocal(id)
      await removeCachedEvent(id)
      notify('Vous avez quitté l’événement', 'success')
    } catch (error) {
      notify(errorMessage(error, 'Impossible de quitter l’événement'))
      throw error
    }
  }

  async function joinByCode(code) {
    const joined = await api.joinInvite(code)
    upsertLocal(joined)
    await upsertCachedEvent(joined)
    return joined
  }

  function errorMessage(error, fallback) {
    if (error instanceof ApiError && error.status === 0) {
      return 'Hors ligne : modification impossible pour le moment'
    }
    return error instanceof ApiError ? error.message : fallback
  }

  function openCreateForm() {
    editingEvent.value = null
    formOpen.value = true
  }

  function openEditForm(event) {
    editingEvent.value = event
    formOpen.value = true
  }

  return {
    events,
    sorted,
    upcoming,
    past,
    loading,
    toast,
    formOpen,
    editingEvent,
    byId,
    handleEvent,
    initFromCache,
    refresh,
    reset,
    createEvent,
    updateEvent,
    deleteEvent,
    leaveEvent,
    joinByCode,
    openCreateForm,
    openEditForm,
  }
})
