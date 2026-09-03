<script setup>
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useEventsStore } from '@/stores/events'

const store = useEventsStore()
const { formOpen, editingEvent } = storeToRefs(store)

const name = ref('')
const startsOn = ref(null)
const endsOn = ref(null)
const saving = ref(false)
/** Which calendar is open, if any: 'start' | 'end' | null. */
const picking = ref(null)

const isEdit = computed(() => Boolean(editingEvent.value))

/** Vuetify's date picker works in Date objects; the API speaks YYYY-MM-DD. */
function toISODate(value) {
  if (!value) return null
  const d = value instanceof Date ? value : new Date(value)
  // Built from local parts, not toISOString(), which would shift the day back
  // for anyone east of UTC — an event on the 1st saved as the 31st.
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

function fromISODate(value) {
  if (!value) return null
  const [y, m, d] = value.split('-').map(Number)
  return new Date(y, m - 1, d)
}

const formatted = (value) =>
  value
    ? value.toLocaleDateString('fr-FR', {
        weekday: 'short',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : ''

const startLabel = computed(() => formatted(startsOn.value))
const endLabel = computed(() => formatted(endsOn.value))

const rangeInvalid = computed(
  () => Boolean(startsOn.value && endsOn.value && endsOn.value < startsOn.value),
)

const valid = computed(
  () => name.value.trim().length > 0 && startsOn.value && endsOn.value && !rangeInvalid.value,
)

// Reset the fields each time the dialog opens, from the event being edited or
// from sensible defaults for a new one.
watch(formOpen, (open) => {
  if (!open) return
  picking.value = null
  if (editingEvent.value) {
    name.value = editingEvent.value.name
    startsOn.value = fromISODate(editingEvent.value.starts_on)
    endsOn.value = fromISODate(editingEvent.value.ends_on)
  } else {
    const today = new Date()
    name.value = ''
    startsOn.value = new Date(today.getFullYear(), today.getMonth(), today.getDate())
    endsOn.value = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  }
})

// Picking a start after the current end drags the end along, which is almost
// always what was meant and avoids a validation error the user has to fix.
watch(startsOn, (value) => {
  if (value && endsOn.value && endsOn.value < value) endsOn.value = value
})

async function save() {
  if (!valid.value || saving.value) return
  saving.value = true
  const payload = {
    name: name.value.trim(),
    starts_on: toISODate(startsOn.value),
    ends_on: toISODate(endsOn.value),
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
          class="mb-2"
        />

        <v-list class="pa-0 bg-transparent">
          <v-list-item
            class="px-0"
            prepend-icon="mdi-calendar-start-outline"
            :title="startLabel || 'Choisir une date'"
            subtitle="Début"
            rounded="lg"
            @click="picking = picking === 'start' ? null : 'start'"
          />
          <v-expand-transition>
            <v-date-picker
              v-if="picking === 'start'"
              v-model="startsOn"
              show-adjacent-months
              hide-header
              width="100%"
              @update:model-value="picking = null"
            />
          </v-expand-transition>

          <v-list-item
            class="px-0"
            prepend-icon="mdi-calendar-end-outline"
            :title="endLabel || 'Choisir une date'"
            subtitle="Fin"
            rounded="lg"
            @click="picking = picking === 'end' ? null : 'end'"
          />
          <v-expand-transition>
            <v-date-picker
              v-if="picking === 'end'"
              v-model="endsOn"
              :min="startsOn"
              show-adjacent-months
              hide-header
              width="100%"
              @update:model-value="picking = null"
            />
          </v-expand-transition>
        </v-list>

        <v-alert
          v-if="rangeInvalid"
          type="warning"
          variant="tonal"
          density="compact"
          class="mt-2"
        >
          La fin doit être après le début.
        </v-alert>
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
