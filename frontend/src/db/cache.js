import Dexie from 'dexie'

/**
 * Read-only offline cache.
 *
 * The server stays the source of truth: every write goes over HTTP and comes
 * back as a WebSocket event, and only then is it mirrored here. The cache
 * exists so the app opens instantly and stays readable with no connection —
 * it never accumulates local changes, so there is nothing to reconcile.
 *
 * IndexedDB is used identically by the web build and by the Android WebView,
 * so this file is shared verbatim between both targets.
 */
const db = new Dexie('popote')

db.version(1).stores({
  recipes: 'id, name, type, updated_at',
  meta: 'key',
})

// v2 adds the events mirror. Dexie migrates an existing database in place, so
// an app that was already installed keeps its cached recipes.
db.version(2).stores({
  recipes: 'id, name, type, updated_at',
  events: 'id, starts_on, name',
  meta: 'key',
})

const LAST_SYNC_KEY = 'lastSync'

/**
 * Strip Vue reactivity before handing data to IndexedDB.
 *
 * Recipes reach this layer as reactive proxies, which the structured clone
 * algorithm rejects with a DataCloneError — silently leaving the cache empty
 * and the app unusable offline. `toRaw` only unwraps the outermost proxy, and
 * nested arrays (ingredients, steps) would still be proxied, so round-trip
 * through JSON: recipes are plain JSON data, so nothing is lost.
 */
function toPlain(value) {
  return JSON.parse(JSON.stringify(value))
}

export async function readCachedRecipes() {
  try {
    return await db.recipes.toArray()
  } catch (error) {
    console.warn('Cache unreadable, starting empty', error)
    return []
  }
}

export async function replaceCache(recipes) {
  try {
    const plain = toPlain(recipes)
    await db.transaction('rw', db.recipes, async () => {
      await db.recipes.clear()
      await db.recipes.bulkPut(plain)
    })
    await writeLastSync(new Date().toISOString())
  } catch (error) {
    console.warn('Could not write cache', error?.name, error?.message, error)
  }
}

export async function upsertCached(recipe) {
  try {
    await db.recipes.put(toPlain(recipe))
    await writeLastSync(new Date().toISOString())
  } catch (error) {
    console.warn('Could not cache recipe', error)
  }
}

export async function removeCached(id) {
  try {
    await db.recipes.delete(id)
    await writeLastSync(new Date().toISOString())
  } catch (error) {
    console.warn('Could not remove cached recipe', error)
  }
}

// ------------------------------------------------------------------ events

export async function readCachedEvents() {
  try {
    return await db.events.toArray()
  } catch (error) {
    console.warn('Event cache unreadable, starting empty', error)
    return []
  }
}

export async function replaceEventCache(events) {
  try {
    const plain = toPlain(events)
    await db.transaction('rw', db.events, async () => {
      await db.events.clear()
      await db.events.bulkPut(plain)
    })
  } catch (error) {
    console.warn('Could not write event cache', error)
  }
}

export async function upsertCachedEvent(event) {
  try {
    await db.events.put(toPlain(event))
  } catch (error) {
    console.warn('Could not cache event', error)
  }
}

export async function removeCachedEvent(id) {
  try {
    await db.events.delete(id)
  } catch (error) {
    console.warn('Could not remove cached event', error)
  }
}

/**
 * Wipe every cached row. Called on logout.
 *
 * The cache is per-browser, not per-account, and recipes are private now. If
 * it survived a logout, the next person to sign in on the same device — or on
 * the same phone — would be shown the previous user's recipes offline, before
 * any `hello` event arrived to replace them.
 */
export async function clearCache() {
  try {
    await db.transaction('rw', db.recipes, db.events, db.meta, async () => {
      await db.recipes.clear()
      await db.events.clear()
      await db.meta.clear()
    })
  } catch (error) {
    console.warn('Could not clear cache', error)
  }
}

export async function readLastSync() {
  try {
    const row = await db.meta.get(LAST_SYNC_KEY)
    return row?.value ?? null
  } catch {
    return null
  }
}

async function writeLastSync(isoString) {
  try {
    await db.meta.put({ key: LAST_SYNC_KEY, value: isoString })
  } catch {
    // Losing the sync timestamp is cosmetic; never fail a write over it.
  }
}
