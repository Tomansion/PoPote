<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

import { placeholderGradient } from '@/utils/gradient'

const props = defineProps({
  recipe: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

const emit = defineEmits(['select', 'toggle-favorite', 'menu'])

const totalMinutes = computed(
  () => (props.recipe.prep_minutes || 0) + (props.recipe.cook_minutes || 0),
)

const durationLabel = computed(() =>
  totalMinutes.value ? `${totalMinutes.value} min` : null,
)

// The thumbnail, not the full picture: a screen of these is a dozen images at
// once, and the big one is only ever needed on the detail page.
const imageUrl = computed(
  () => props.recipe.image_thumb_url || props.recipe.image_url || '',
)

const gradient = computed(() => placeholderGradient(props.recipe.id))

// ------------------------------------------------------------- the menu
//
// Right-click on a desktop, long-press on a phone: the same menu, opened at
// the point the user actually pressed. The card only reports where and when;
// the list owns the single menu instance, rather than one per card.

const LONG_PRESS_MS = 500
let pressTimer = null
// A long press fires while the finger is still down, so the touchend that
// follows would arrive as an ordinary tap and open the recipe behind the menu.
const suppressClick = ref(false)

function openMenu(x, y) {
  emit('menu', { recipe: props.recipe, x, y })
}

function onContextMenu(event) {
  event.preventDefault()
  openMenu(event.clientX, event.clientY)
}

function cancelPress() {
  if (pressTimer) clearTimeout(pressTimer)
  pressTimer = null
}

function onTouchStart(event) {
  const touch = event.touches[0]
  if (!touch) return
  cancelPress()
  pressTimer = setTimeout(() => {
    pressTimer = null
    suppressClick.value = true
    openMenu(touch.clientX, touch.clientY)
  }, LONG_PRESS_MS)
}

function onClick() {
  if (suppressClick.value) {
    suppressClick.value = false
    return
  }
  emit('select', props.recipe)
}

// A card can be unmounted mid-press — by a filter change, or by the list
// reloading — and a timer left running would open a menu over whatever
// replaced it.
onBeforeUnmount(cancelPress)
</script>

<template>
  <v-card
    :class="['em-outline pp-card', selected ? 'em-selected' : '']"
    flat
    @click="onClick"
    @contextmenu="onContextMenu"
    @touchstart.passive="onTouchStart"
    @touchend="cancelPress"
    @touchmove.passive="cancelPress"
    @touchcancel="cancelPress"
  >
    <div class="pp-card-image">
      <v-img v-if="imageUrl" :src="imageUrl" height="84" cover />
      <!-- No photo: a tint derived from the recipe's id, so the card still
           has a face and two recipes never share one by accident. -->
      <div v-else class="pp-card-placeholder" :style="{ background: gradient }" />
      <v-btn
        :icon="recipe.favorite ? 'mdi-heart' : 'mdi-heart-outline'"
        :color="recipe.favorite ? 'error' : 'white'"
        variant="text"
        size="small"
        density="comfortable"
        class="pp-card-favorite"
        :aria-label="recipe.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
        @click.stop="emit('toggle-favorite', recipe)"
      />
    </div>

    <div class="pp-card-body">
      <div class="text-body-2 font-weight-medium text-truncate">
        {{ recipe.name }}
      </div>

      <div class="text-caption em-muted text-truncate">
        {{ recipe.type }}<template v-if="durationLabel"> · {{ durationLabel }}</template>
      </div>
    </div>
  </v-card>
</template>

<style scoped>
/* Fixed size so every card lines up regardless of name length or how many
   details it has — a mix of short and long recipe names otherwise produces
   ragged rows of unequal height. */
.pp-card {
  width: 184px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  /* The long-press menu is the point; the OS text-selection popup that a long
     press otherwise triggers would land on top of it. */
  -webkit-touch-callout: none;
  user-select: none;
}

.pp-card-image {
  position: relative;
}

.pp-card-placeholder {
  height: 84px;
}

.pp-card-favorite {
  position: absolute;
  top: 4px;
  right: 4px;
  /* A plain white icon can vanish against a light patch of the photo — or of
     the gradient — so the shadow keeps its outline (and the filled red heart)
     readable anywhere. */
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.7));
}

.pp-card-body {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  height: 68px;
  padding: 8px;
}
</style>
