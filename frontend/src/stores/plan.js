import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { api, ApiError } from '@/api/client'

/** The three parts of a day, in the order they are cooked and displayed. */
export const SLOTS = ['matin', 'midi', 'soir']

export const SLOT_LABELS = {
  matin: 'Matin',
  midi: 'Midi',
  soir: 'Soir',
}

export const SLOT_ICONS = {
  matin: 'mdi-weather-sunset-up',
  midi: 'mdi-white-balance-sunny',
  soir: 'mdi-weather-night',
}

/** A blank slot: nothing decided, inheriting the event's headcount. */
export function emptySlot() {
  return { skipped: false, people: null, recipes: [] }
}

/**
 * A fresh id for one planned meal.
 *
 * Per *planned meal*, not per recipe: the same dish can be planned twice in
 * one slot, and drag & drop has to be able to tell those two apart.
 */
export function newMealId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().slice(0, 36)
  return `m${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
}

/** Local YYYY-MM-DD, never toISOString() — that shifts the day east of UTC. */
export function toISODate(date) {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function fromISODate(value) {
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** Every day of an event, inclusive, as YYYY-MM-DD. */
export function daysBetween(startISO, endISO) {
  const days = []
  const cursor = fromISODate(startISO)
  const end = fromISODate(endISO)
  while (cursor <= end) {
    days.push(toISODate(cursor))
    cursor.setDate(cursor.getDate() + 1)
  }
  return days
}

export const usePlanStore = defineStore('plan', () => {
  /** eventId -> plan, so switching between two events keeps both loaded. */
  const plans = ref({})
  /** eventId -> every member's recipes, for the picker. */
  const eventRecipes = ref({})
  const loading = ref(false)
  const toast = ref(null)

  /**
   * Meals the user ctrl-clicked, as `${day}|${slot}|${uid}`.
   *
   * Held here rather than in the view so that dragging one member of a
   * selection can move the whole set — the drag handler needs to know what
   * else was picked, and the calendar is rebuilt on every plan update.
   */
  const selected = ref(new Set())

  function notify(message, color = 'error') {
    toast.value = { message, color, at: Date.now() }
  }

  const selectionKey = (day, slot, uid) => `${day}|${slot}|${uid}`

  function isSelected(day, slot, uid) {
    return selected.value.has(selectionKey(day, slot, uid))
  }

  function toggleSelected(day, slot, uid) {
    const key = selectionKey(day, slot, uid)
    const next = new Set(selected.value)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    selected.value = next
  }

  function clearSelection() {
    if (selected.value.size) selected.value = new Set()
  }

  const selectedItems = computed(() =>
    [...selected.value].map((key) => {
      const [day, slot, uid] = key.split('|')
      return { day, slot, uid }
    }),
  )

  function planFor(eventId) {
    return plans.value[eventId] ?? { event_id: eventId, days: {} }
  }

  function slotFor(eventId, day, slot) {
    return planFor(eventId).days?.[day]?.[slot] ?? emptySlot()
  }

  /** The members on duty for a whole day — cooking, shopping, washing up. */
  function dayCooksFor(eventId, day) {
    return planFor(eventId).day_cooks?.[day] ?? []
  }

  /**
   * Apply a plan pushed over the socket.
   *
   * Called by the recipes store, which owns the single connection. Only
   * events already open are stored: a plan for an event the user is not
   * looking at would sit in memory until sign-out for no benefit.
   */
  function handleEvent(message) {
    if (message.type !== 'plan.updated' || !message.event_id) return
    if (!(message.event_id in plans.value)) return
    plans.value[message.event_id] = message.plan
  }

  async function load(eventId) {
    loading.value = true
    try {
      const [plan, recipes] = await Promise.all([
        api.getPlan(eventId),
        api.eventRecipes(eventId),
      ])
      plans.value[eventId] = plan
      eventRecipes.value[eventId] = recipes
      return plan
    } catch (error) {
      notify(errorMessage(error, 'Impossible de charger le planning'))
      throw error
    } finally {
      loading.value = false
    }
  }

  async function setSlot(eventId, day, slot, payload) {
    try {
      plans.value[eventId] = await api.setPlanSlot(eventId, day, slot, payload)
    } catch (error) {
      notify(errorMessage(error, "Impossible d'enregistrer ce repas"))
      throw error
    }
  }

  async function setDayCooks(eventId, day, cooks) {
    try {
      plans.value[eventId] = await api.setPlanDayCooks(eventId, day, cooks)
    } catch (error) {
      notify(errorMessage(error, 'Impossible d’enregistrer les responsables'))
      throw error
    }
  }

  /**
   * Move planned meals into one slot.
   *
   * The server returns the whole plan, so the calendar is redrawn from the
   * authoritative version rather than from whatever the drag left in the DOM.
   */
  async function move(eventId, items, toDay, toSlot) {
    if (!items.length) return
    try {
      plans.value[eventId] = await api.movePlanMeals(eventId, {
        items,
        to_day: toDay,
        to_slot: toSlot,
      })
      clearSelection()
    } catch (error) {
      notify(errorMessage(error, 'Impossible de déplacer ce repas'))
      throw error
    }
  }

  /** Add a recipe to a slot, keeping whatever is already planned there. */
  async function addRecipe(eventId, day, slot, recipe, servings) {
    const current = slotFor(eventId, day, slot)
    return setSlot(eventId, day, slot, {
      ...current,
      // Planning something into a slot marked "rien à cuisiner" is a change
      // of mind: the meal wins.
      skipped: false,
      recipes: [
        ...current.recipes,
        {
          uid: newMealId(),
          recipe_id: recipe.id,
          owner_id: recipe.owner_id ?? '',
          name: recipe.name,
          servings,
          cooks: [],
        },
      ],
    })
  }

  async function removeRecipe(eventId, day, slot, uid) {
    const current = slotFor(eventId, day, slot)
    return setSlot(eventId, day, slot, {
      ...current,
      recipes: current.recipes.filter((meal) => meal.uid !== uid),
    })
  }

  function errorMessage(error, fallback) {
    if (error instanceof ApiError && error.status === 0) {
      return 'Hors ligne : modification impossible pour le moment'
    }
    return error instanceof ApiError ? error.message : fallback
  }

  function reset() {
    plans.value = {}
    eventRecipes.value = {}
    loading.value = false
    clearSelection()
  }

  return {
    plans,
    eventRecipes,
    loading,
    toast,
    selected,
    selectedItems,
    isSelected,
    toggleSelected,
    clearSelection,
    planFor,
    slotFor,
    dayCooksFor,
    handleEvent,
    load,
    setSlot,
    setDayCooks,
    move,
    addRecipe,
    removeRecipe,
    reset,
  }
})
