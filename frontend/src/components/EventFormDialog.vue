<script setup>
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import SectionHeader from '@/components/SectionHeader.vue'
import { useEventsStore } from '@/stores/events'
import { fromISODate, toISODate } from '@/stores/plan'

const store = useEventsStore()
const { formOpen, editingEvent } = storeToRefs(store)

const name = ref('')
/**
 * The picker's model: `[]`, `[day]`, or `[start, end]`.
 *
 * Vuetify's `multiple="range"` fills the days in between visually and hands
 * back only the two ends, which is exactly the shape the API wants. A single
 * click is a one-day event rather than an unfinished range — asking for a
 * second click on the same square to confirm "just Saturday" would be worse.
 */
const range = ref([])
const people = ref(4)
const saving = ref(false)

const isEdit = computed(() => Boolean(editingEvent.value))

// Vuetify's date picker works in Date objects; the API speaks YYYY-MM-DD.
// Both helpers live with the planner, which reads the same dates back — and
// both build from local parts rather than toISOString(), which would shift the
// day back for anyone east of UTC (an event on the 1st saved as the 31st).

const startsOn = computed(() => range.value[0] ?? null)
const endsOn = computed(() => range.value[range.value.length - 1] ?? null)

const formatted = (value) =>
  value
    ? value.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'long' })
    : ''

const dayCount = computed(() => {
  if (!startsOn.value || !endsOn.value) return 0
  const ms = endsOn.value.getTime() - startsOn.value.getTime()
  return Math.round(ms / 86400000) + 1
})

const rangeLabel = computed(() => {
  if (!startsOn.value) return 'Choisissez le premier jour'
  if (!range.value[1]) return `${formatted(startsOn.value)} — choisissez le dernier jour`
  const days = dayCount.value
  return `Du ${formatted(startsOn.value)} au ${formatted(endsOn.value)} · ${days} jour${days > 1 ? 's' : ''}`
})

const valid = computed(() => name.value.trim().length > 0 && Boolean(startsOn.value))

// Reset the fields each time the dialog opens, from the event being edited or
// from sensible defaults for a new one.
watch(formOpen, (open) => {
  if (!open) return
  if (editingEvent.value) {
    name.value = editingEvent.value.name
    range.value = [
      fromISODate(editingEvent.value.starts_on),
      fromISODate(editingEvent.value.ends_on),
    ]
    people.value = editingEvent.value.default_people ?? 4
  } else {
    name.value = ''
    // Deliberately empty. Pre-selecting today would leave a half-open range,
    // so the user's first click — the day they mean to start on — would be
    // read as the *end* of a range beginning today.
    range.value = []
    people.value = 4
  }
})

async function save() {
  if (!valid.value || saving.value) return
  saving.value = true
  const payload = {
    name: name.value.trim(),
    starts_on: toISODate(startsOn.value),
    // A one-day event: both ends are the same day.
    ends_on: toISODate(endsOn.value ?? startsOn.value),
    default_people: Number(people.value) || 1,
  }
  try {
    if (isEdit.value) await store.updateEvent(editingEvent.value.id, payload)
    else await store.createEvent(payload)
    formOpen.value = false
  } catch {
    // The store has already raised a toast.
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog v-model="formOpen" max-width="480" scrollable>
    <v-card rounded="xl">
      <v-card-title class="text-subtitle-1 font-weight-medium pt-5 px-5">
        {{ isEdit ? 'Modifier l’événement' : 'Nouvel événement' }}
      </v-card-title>

      <v-card-text class="px-5">
        <v-text-field
          v-model="name"
          label="Nom"
          placeholder="Noël chez mamie, Week-end à la mer…"
          prepend-inner-icon="mdi-tag-outline"
          autofocus
          class="mb-4"
        />

        <SectionHeader icon="mdi-calendar-range" title="Quand ?" />
        <p class="text-body-2 em-muted mb-2">
          Les repas se planifieront sur ces jours-là. Cliquez le premier puis le
          dernier jour.
        </p>

        <!-- One calendar for both ends rather than two collapsible pickers:
             the days in between are what the event actually is, and they were
             invisible when the start and the end were chosen separately. -->
        <v-date-picker
          v-model="range"
          multiple="range"
          show-adjacent-months
          hide-header
          width="100%"
          class="em-outline mb-2"
          rounded="lg"
        />

        <p class="text-body-2 text-center mb-6" :class="range[1] ? '' : 'em-muted'">
          {{ rangeLabel }}
        </p>

        <SectionHeader icon="mdi-account-group-outline" title="Combien ?" />
        <p class="text-body-2 em-muted mb-3">
          Le nombre de personnes attendues à table chaque jour. Il sert de valeur
          par défaut pour chaque repas, et reste modifiable repas par repas.
        </p>
        <v-text-field
          v-model.number="people"
          label="Personnes"
          type="number"
          min="1"
          max="200"
          prepend-inner-icon="mdi-silverware-fork-knife"
        />
      </v-card-text>

      <v-card-actions class="px-5 pb-5">
        <v-spacer />
        <v-btn variant="text" @click="formOpen = false">Annuler</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="save">
          {{ isEdit ? 'Enregistrer' : 'Créer' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
