/**
 * A stable colour for a recipe with no photo.
 *
 * Recipes used to fall back to a blurred stock image, which read as a broken
 * photo rather than as a deliberate absence. A flat tint keyed to the recipe's
 * own id looks intentional, costs nothing to render, needs no network, and —
 * because it is derived rather than random — never changes between visits or
 * between devices.
 */

/**
 * FNV-1a, folded into a hue.
 *
 * Any hash would do; what matters is that neighbouring ids ("6551", "6552")
 * land far apart, so a freshly seeded recipe book is not three shades of the
 * same green.
 */
function hashHue(seed) {
  let hash = 0x811c9dc5
  const text = String(seed ?? '')
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return Math.abs(hash) % 360
}

/**
 * A light two-stop gradient, as a ready-to-use CSS value.
 *
 * Kept pale on purpose: the card's title sits on the tile below it and the
 * favourite heart sits on top of it, and both have to stay readable whatever
 * hue comes out of the hash.
 */
export function placeholderGradient(seed) {
  const hue = hashHue(seed)
  const partner = (hue + 34) % 360
  return `linear-gradient(135deg, hsl(${hue} 44% 90%) 0%, hsl(${partner} 50% 81%) 100%)`
}

/**
 * A saturated version of the same hue, for a thin accent.
 *
 * Used on the planner's meal lines, where a full gradient would fight with
 * the text next to it but a 3px stripe makes the same dish recognisable
 * across the days it is cooked on.
 */
export function accentColor(seed) {
  return `hsl(${hashHue(seed)} 55% 55%)`
}
