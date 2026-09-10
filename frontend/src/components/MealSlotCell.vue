<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import Sortable from 'sortablejs'

import { SLOT_ICONS, SLOT_LABELS, usePlanStore } from '@/stores/plan'
import { accentColor } from '@/utils/gradient'

const props = defineProps({
  eventId: { type: String, required: true },
  day: { type: String, required: true },
  slot: { type: String, required: true },
  meal: { type: Object, required: true },
  /** Compact rendering for the desktop month grid. */
  dense: { type: Boolean, default: false },
})

const emit = defineEmits(['open'])

const plan = usePlanStore()
const listEl = ref(null)
let sortable = null

const meals = computed(() => props.meal.recipes ?? [])

/**
 * Drag & drop between any two slots.
 *
 * Every slot in the calendar joins one Sortable group, so a meal can be
 * dragged from Saturday lunch to Sunday dinner directly. `delayOnTouchOnly`
 * keeps a plain tap working on a phone — without the delay, scrolling the
 * calendar with a finger would pick meals up instead.
 */
watch(listEl, (element) => {
  sortable?.destroy()
  sortable = null
  if (!element) return

  sortable = Sortable.create(element, {
    group: 'pp-meals',
    draggable: '.pp-meal',
    animation: 150,
    delay: 180,
    delayOnTouchOnly: true,
    fallbackOnBody: true,
    ghostClass: 'pp-meal--ghost',
    onEnd: (evt) => {
      const { item, from, to, oldIndex } = evt

      // Put the DOM back the way Vue rendered it. The plan the server returns
      // is the source of truth, and letting Sortable's move stand as well
      // would show the meal in both slots until the next render.
      from.insertBefore(item, from.children[oldIndex] ?? null)

      const toDay = to.dataset.day
      const toSlot = to.dataset.slot
      if (!toDay || !toSlot) return
      // Reordering inside a slot is not persisted: nothing downstream — the
      // calendar, the shopping list — depends on the order of a slot's meals.
      if (toDay === props.day && toSlot === props.slot) return

      const uid = item.dataset.uid
      if (!uid) return

      // Dragging one meal of a ctrl-clicked set moves the whole set; dragging
      // an unselected meal moves only it, and leaves the selection alone.
      const items = plan.isSelected(props.day, props.slot, uid)
        ? plan.selectedItems
        : [{ day: props.day, slot: props.slot, uid }]

      plan.move(props.eventId, items, toDay, toSlot)
    },
  })
})

onBeforeUnmount(() => {
  sortable?.destroy()
  sortable = null
})

function onMealClick(event, uid) {
  // Ctrl/⌘-click builds a selection to drag as one; a plain click opens the
  // slot, which is where a meal is actually edited.
  if (event.ctrlKey || event.metaKey) {
    event.stopPropagation()
    plan.toggleSelected(props.day, props.slot, uid)
    return
  }
  emit('open')
}
</script>

<template>
  <div class="pp-slot" :class="dense ? 'pp-slot--dense' : ''" @click="emit('open')">
    <div class="d-flex align-center ga-1 pp-slot-title">
      <v-icon :icon="SLOT_ICONS[slot]" size="12" />
      <span class="text-caption em-muted">{{ SLOT_LABELS[slot] }}</span>
      <v-spacer />
      <span
        v-if="!meal.skipped && meal.people !== null && meal.people !== undefined"
        class="text-caption em-muted em-mono"
      >
        {{ meal.people }}p
      </span>
    </div>

    <div v-if="meal.skipped" class="pp-skipped text-caption">
      <v-icon icon="mdi-silverware-off" size="12" class="me-1" />
      Rien à cuisiner
    </div>

    <!-- The drop target has to exist even when the slot is empty, or there
         would be nowhere to drag the first meal of a day to. -->
    <div ref="listEl" class="pp-meals" :data-day="day" :data-slot="slot">
      <div
        v-for="planned in meals"
        :key="planned.uid"
        class="pp-meal"
        :class="plan.isSelected(day, slot, planned.uid) ? 'pp-meal--selected' : ''"
        :data-uid="planned.uid"
        :style="{ '--pp-accent': accentColor(planned.recipe_id) }"
        @click.stop="onMealClick($event, planned.uid)"
      >
        <span class="pp-meal-name">{{ planned.name }}</span>
        <span class="pp-meal-servings em-mono">{{ planned.servings }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pp-slot {
  padding: 4px 6px;
  border-radius: 6px;
  cursor: pointer;
}

.pp-slot:hover {
  background: rgba(0, 0, 0, 0.03);
}

.pp-slot-title {
  line-height: 1.4;
}

.pp-skipped {
  color: var(--em-muted);
  font-style: italic;
  padding: 1px 2px;
}

/* Keeps an empty slot droppable: with no height there is nothing to aim at. */
.pp-meals {
  min-height: 14px;
}

/* The Google-Tasks-style line: one row, a coloured stripe, name then count. */
.pp-meal {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  line-height: 1.5;
  padding: 1px 4px 1px 6px;
  margin-bottom: 2px;
  border-left: 3px solid var(--pp-accent, #999);
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.04);
  cursor: grab;
}

.pp-meal--selected {
  outline: 2px solid var(--pp-accent, #999);
  background: rgba(0, 0, 0, 0.09);
}

.pp-meal--ghost {
  opacity: 0.4;
}

.pp-meal-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pp-meal-servings {
  flex: none;
  color: var(--em-muted);
}

/* The month grid gives each day a fixed box; the mobile day list does not. */
.pp-slot--dense .pp-meal {
  font-size: 0.7rem;
}
</style>
