import { ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError } from '@/api/client'
import { groceryWebsocketUrl, shareLink } from '@/api/config'
import { createLiveFeed } from '@/api/ws'
import { AISLE_LABELS } from '@/utils/aisles'

/** The page anyone can open with the code, signed in or not. */
export function groceryLink(shareCode) {
  return shareLink(`/courses/${shareCode}`)
}

export const useGroceryStore = defineStore('grocery', () => {
  /** eventId -> list, for the members' view inside an event. */
  const lists = ref({})
  /** Rows for the "Liste de courses" section. */
  const summaries = ref([])
  /** The list the shared page is showing, which may have no event behind it. */
  const shared = ref(null)
  const loading = ref(false)
  const busy = ref(false)
  const toast = ref(null)

  let feed = null

  function notify(message, color = 'error') {
    toast.value = { message, color, at: Date.now() }
  }

  function listFor(eventId) {
    return lists.value[eventId] ?? null
  }

  function remember(list) {
    if (!list) return
    lists.value[list.event_id] = list
    if (shared.value?.share_code === list.share_code) shared.value = list
  }

  /**
   * Apply a list pushed over the signed-in feed.
   *
   * Called by the recipes store, which owns that connection. The shared page
   * has its own socket instead — it has no session to attach this one to.
   */
  function handleEvent(message) {
    if (message.type !== 'grocery.updated' || !message.grocery) return
    remember(message.grocery)
    // Keep the index consistent without a round-trip: only the counters and
    // the timestamp can have changed.
    const row = summaries.value.find((s) => s.event_id === message.grocery.event_id)
    if (row) {
      row.item_count = message.grocery.items.length
      row.checked_count = message.grocery.items.filter((i) => i.checked).length
      row.total_price = message.grocery.total_price
      row.updated_at = message.grocery.updated_at
    }
  }

  async function loadSummaries() {
    loading.value = true
    try {
      summaries.value = await api.listGroceryLists()
    } catch (error) {
      notify(errorMessage(error, 'Impossible de charger les listes'))
    } finally {
      loading.value = false
    }
  }

  /**
   * Whether this event already has a list, and its share code if so.
   *
   * Read from the index rather than by fetching the list itself: an event
   * with no list yet is the common case, and asking for one directly answers
   * 404 — a real error in the console on almost every visit to a planner.
   */
  function summaryFor(eventId) {
    return summaries.value.find((row) => row.event_id === eventId) ?? null
  }

  async function generate(eventId) {
    busy.value = true
    try {
      const list = await api.generateGroceryList(eventId)
      remember(list)
      notify('Liste de courses générée', 'success')
      return list
    } catch (error) {
      notify(errorMessage(error, 'Impossible de générer la liste'))
      throw error
    } finally {
      busy.value = false
    }
  }

  async function estimatePrices(eventId) {
    busy.value = true
    try {
      const list = await api.priceGroceryList(eventId)
      remember(list)
      return list
    } catch (error) {
      notify(errorMessage(error, "L'estimation a échoué"))
      throw error
    } finally {
      busy.value = false
    }
  }

  /**
   * Tick or untick a line.
   *
   * Applied locally first: at the shop this is the one interaction that has to
   * feel instant, and the round-trip only corrects it if the server disagrees.
   */
  async function toggleItem(shareCode, itemKey, checked) {
    const before = shared.value
    if (before?.share_code === shareCode) {
      shared.value = {
        ...before,
        items: before.items.map((item) =>
          item.key === itemKey ? { ...item, checked } : item,
        ),
      }
    }
    try {
      remember(await api.checkGroceryItem(shareCode, itemKey, checked))
    } catch (error) {
      if (before?.share_code === shareCode) shared.value = before
      notify(errorMessage(error, 'Impossible de cocher cet article'))
    }
  }

  /**
   * Open a shared list and keep it live.
   *
   * Its own socket, keyed by the share code: whoever is looking at this page
   * may be signed out entirely, and the ticks have to reach everyone else
   * holding the same link.
   */
  async function openShared(shareCode) {
    loading.value = true
    stopShared()
    try {
      shared.value = await api.publicGroceryList(shareCode)
    } catch (error) {
      shared.value = null
      throw error
    } finally {
      loading.value = false
    }

    feed = createLiveFeed({
      resolveUrl: () => groceryWebsocketUrl(shareCode),
      onEvent: (message) => {
        if (message.type === 'grocery.updated' && message.grocery) remember(message.grocery)
      },
      onStatus: () => {},
    })
    feed.start()
    return shared.value
  }

  function stopShared() {
    feed?.stop()
    feed = null
  }

  function reset() {
    stopShared()
    lists.value = {}
    summaries.value = []
    shared.value = null
    loading.value = false
  }

  function errorMessage(error, fallback) {
    if (error instanceof ApiError && error.status === 0) {
      return 'Hors ligne : action impossible pour le moment'
    }
    return error instanceof ApiError ? error.message : fallback
  }

  return {
    lists,
    summaries,
    shared,
    loading,
    busy,
    toast,
    listFor,
    handleEvent,
    loadSummaries,
    summaryFor,
    generate,
    estimatePrices,
    toggleItem,
    openShared,
    stopShared,
    reset,
  }
})

/**
 * Group a list's items for display.
 *
 * Two shapes from the same items: by aisle, which is how you walk a shop, and
 * by recipe, which is how you check you have not forgotten a dish. The second
 * is why every item carries its sources.
 */
export function groupItems(items, mode) {
  const groups = new Map()

  if (mode === 'recipe') {
    for (const item of items) {
      for (const source of item.sources ?? []) {
        const key = source.recipe_name || 'Autres'
        if (!groups.has(key)) groups.set(key, [])
        // The same ingredient in two recipes appears under both, with the
        // share that recipe actually calls for.
        groups.get(key).push({ ...item, quantity: source.quantity })
      }
    }
  } else {
    for (const item of items) {
      const key = item.aisle || 'autre'
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key).push(item)
    }
  }

  return [...groups.entries()].map(([key, groupItemsList]) => ({
    key,
    title: mode === 'recipe' ? key : (AISLE_LABELS[key] ?? key),
    items: groupItemsList,
  }))
}
