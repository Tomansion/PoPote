<script setup>
import { computed } from 'vue'
import { useDisplay } from 'vuetify'

import MealSlotCell from '@/components/MealSlotCell.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { SLOTS, daysBetween, emptySlot, fromISODate, toISODate, usePlanStore } from '@/stores/plan'

const props = defineProps({
  event: { type: Object, required: true },
})

const emit = defineEmits(['open-slot', 'open-day'])

const plan = usePlanStore()
const { mdAndUp } = useDisplay()

const WEEKDAYS = ['lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.', 'dim.']

/** Monday-first index, which is how a French calendar is read. */
const mondayIndex = (date) => (date.getDay() + 6) % 7

const eventDays = computed(() => daysBetween(props.event.starts_on, props.event.ends_on))

/**
 * The month grid: whole weeks, from the Monday before the event starts to the
 * Sunday after it ends.
 *
 * Showing the surrounding days — greyed and inert — is what makes it read as
 * a calendar rather than as a list of boxes. They are never clickable: the
 * event is the only thing there is to plan.
 */
const weeks = computed(() => {
  const gridStart = fromISODate(props.event.starts_on)
  gridStart.setDate(gridStart.getDate() - mondayIndex(gridStart))

  const gridEnd = fromISODate(props.event.ends_on)
  gridEnd.setDate(gridEnd.getDate() + (6 - mondayIndex(gridEnd)))

  const cells = []
  const cursor = new Date(gridStart)
  while (cursor <= gridEnd) {
    const iso = toISODate(cursor)
    cells.push({
      iso,
      dayNumber: cursor.getDate(),
      // Only the 1st carries its month, which is enough to orient an event
      // that straddles two of them without a heading row per month.
      monthLabel:
        cursor.getDate() === 1
          ? cursor.toLocaleDateString('fr-FR', { month: 'short' })
          : '',
      inRange: iso >= props.event.starts_on && iso <= props.event.ends_on,
    })
    cursor.setDate(cursor.getDate() + 1)
  }

  const rows = []
  for (let index = 0; index < cells.length; index += 7) {
    rows.push(cells.slice(index, index + 7))
  }
  return rows
})

const mobileDays = computed(() =>
  eventDays.value.map((iso) => {
    const date = fromISODate(iso)
    return {
      iso,
      label: date.toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
      }),
    }
  }),
)

const slotFor = (day, slot) =>
  plan.planFor(props.event.id).days?.[day]?.[slot] ?? emptySlot()

const members = computed(() => props.event.members ?? [])

/** Whoever is on duty that day, as members rather than as ids. */
const cooksOn = (day) =>
  plan
    .dayCooksFor(props.event.id, day)
    .map((id) => members.value.find((member) => member.id === id))
    .filter(Boolean)

const open = (day, slot) => emit('open-slot', { day, slot })
const openDay = (day) => emit('open-day', day)
</script>

<template>
  <!-- ===================== Desktop: a real month grid ===================== -->
  <div v-if="mdAndUp" class="pp-calendar" @click="plan.clearSelection()">
    <div class="pp-grid pp-grid-head">
      <div v-for="weekday in WEEKDAYS" :key="weekday" class="text-caption em-muted pa-1">
        {{ weekday }}
      </div>
    </div>

    <div v-for="(week, index) in weeks" :key="index" class="pp-grid">
      <div
        v-for="cell in week"
        :key="cell.iso"
        class="pp-day em-outline"
        :class="cell.inRange ? '' : 'pp-day--outside'"
      >
        <div
          class="d-flex align-center ga-1 px-1 pt-1"
          :class="cell.inRange ? 'pp-day-head' : ''"
          @click.stop="cell.inRange && openDay(cell.iso)"
        >
          <span class="text-caption font-weight-medium">{{ cell.dayNumber }}</span>
          <span v-if="cell.monthLabel" class="text-caption em-muted">
            {{ cell.monthLabel }}
          </span>
          <v-spacer />
          <UserAvatar
            v-for="cook in cooksOn(cell.iso)"
            :key="cook.id"
            :seed="cook.avatar_seed"
            :size="15"
            :title="`Responsable : ${cook.display_name}`"
          />
        </div>

        <template v-if="cell.inRange">
          <MealSlotCell
            v-for="slot in SLOTS"
            :key="slot"
            dense
            :event-id="event.id"
            :day="cell.iso"
            :slot="slot"
            :meal="slotFor(cell.iso, slot)"
            :members="members"
            @open="open(cell.iso, slot)"
          />
        </template>
      </div>
    </div>

    <p class="text-caption em-muted mt-3">
      Clic sur une date ou un moment de la journée pour ouvrir la journée ·
      glisser-déposer pour déplacer un repas · Ctrl+clic pour en sélectionner
      plusieurs
    </p>
  </div>

  <!-- ============ Mobile: the event's days, one card each ============ -->
  <div v-else class="d-flex flex-column ga-3">
    <v-card
      v-for="day in mobileDays"
      :key="day.iso"
      variant="outlined"
      rounded="lg"
      class="pa-2"
    >
      <div
        class="d-flex align-center ga-1 px-1 mb-1 pp-day-head"
        @click="openDay(day.iso)"
      >
        <span class="text-body-2 font-weight-medium text-capitalize">
          {{ day.label }}
        </span>
        <v-spacer />
        <UserAvatar
          v-for="cook in cooksOn(day.iso)"
          :key="cook.id"
          :seed="cook.avatar_seed"
          :size="18"
          :title="`Responsable : ${cook.display_name}`"
        />
        <v-icon icon="mdi-chevron-right" size="18" class="em-muted" />
      </div>
      <MealSlotCell
        v-for="slot in SLOTS"
        :key="slot"
        :event-id="event.id"
        :day="day.iso"
        :slot="slot"
        :meal="slotFor(day.iso, slot)"
        :members="members"
        @open="open(day.iso, slot)"
      />
    </v-card>

    <p class="text-caption em-muted">
      Touchez une journée pour l’ouvrir. Maintenez un repas appuyé pour le
      déplacer.
    </p>
  </div>
</template>

<style scoped>
.pp-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 6px;
}

.pp-grid-head {
  margin-bottom: 2px;
}

.pp-day {
  background: rgb(var(--v-theme-surface));
  border-radius: 8px;
  min-height: 132px;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding-bottom: 4px;
  overflow: hidden;
}

.pp-day-head {
  cursor: pointer;
  border-radius: 4px;
}

.pp-day-head:hover {
  background: rgba(0, 0, 0, 0.04);
}

/* Outside the event: visible for context, but nothing to plan there. */
.pp-day--outside {
  background: transparent;
  opacity: 0.35;
  pointer-events: none;
}
</style>
