<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

import EventFormDialog from '@/components/EventFormDialog.vue'
import MealSlotDialog from '@/components/MealSlotDialog.vue'
import PlannerCalendar from '@/components/PlannerCalendar.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import { useEventsStore } from '@/stores/events'
import { useGroceryStore } from '@/stores/grocery'
import { usePlanStore } from '@/stores/plan'

const route = useRoute()
const router = useRouter()

const auth = useAuthStore()
const events = useEventsStore()
const plan = usePlanStore()
const grocery = useGroceryStore()
const { loading: eventsLoading } = storeToRefs(events)

const eventId = computed(() => route.params.id)
const event = computed(() => events.byId(eventId.value))
const isOwner = computed(() => event.value?.owner_id === auth.user?.id)

const editingSlot = ref(null)
const slotDialogOpen = ref(false)
const generating = ref(false)

const dateLabel = computed(() => {
  if (!event.value) return ''
  const options = { day: 'numeric', month: 'long' }
  const start = new Date(event.value.starts_on)
  const end = new Date(event.value.ends_on)
  if (event.value.starts_on === event.value.ends_on) {
    return start.toLocaleDateString('fr-FR', { ...options, weekday: 'long' })
  }
  return `du ${start.toLocaleDateString('fr-FR', options)} au ${end.toLocaleDateString('fr-FR', options)}`
})

/**
 * The event's shopping list, if it has one.
 *
 * Either one we have loaded or generated in this session, or the index row
 * that says one exists — both carry the share code, which is all the button
 * needs to navigate.
 */
const existingList = computed(
  () => grocery.listFor(eventId.value) ?? grocery.summaryFor(eventId.value),
)

/**
 * Load the plan for whichever event is on screen.
 *
 * Keyed on the id rather than done once on mount: the desktop drawer can
 * navigate straight from one event to another without unmounting this view.
 */
watch(
  eventId,
  (id) => {
    if (!id) return
    plan.load(id).catch(() => {})
    grocery.loadSummaries()
  },
  { immediate: true },
)

// Leaving the calendar drops the selection, which only ever means "these are
// the meals I am about to drag".
onMounted(() => plan.clearSelection())

function openSlot({ day, slot }) {
  editingSlot.value = { day, slot }
  slotDialogOpen.value = true
}

function openMember(member) {
  // Your own name goes to the editable profile, not to a read-only copy of it.
  if (member.id === auth.user?.id) router.push({ name: 'profile' })
  else router.push({ name: 'user', params: { id: member.id } })
}

/**
 * Open the shopping list, building it first if there is not one yet.
 *
 * Generating is idempotent and preserves ticks, so the button never has to
 * ask which of the two it is about to do.
 */
async function openGroceryList() {
  generating.value = true
  try {
    const list = existingList.value ?? (await grocery.generate(eventId.value))
    if (list) router.push({ name: 'grocery', params: { code: list.share_code } })
  } catch {
    // The store raised the toast.
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <div class="em-scroll flex-grow-1">
      <v-container class="pa-4" style="max-width: 1200px">
        <div class="d-flex align-center ga-2 mb-3">
          <v-btn
            variant="text"
            size="small"
            prepend-icon="mdi-arrow-left"
            @click="router.push({ name: 'planner' })"
          >
            événements
          </v-btn>
        </div>

        <v-skeleton-loader v-if="!event && eventsLoading" type="article" />

        <div v-else-if="!event" class="text-center em-muted py-12">
          <v-icon icon="mdi-calendar-remove-outline" size="48" class="mb-4" />
          <p class="text-body-2">Cet événement n’existe plus.</p>
        </div>

        <template v-else>
          <div class="d-flex align-start flex-wrap ga-3 mb-4">
            <div class="flex-grow-1" style="min-width: 0">
              <h2 class="text-h6 font-weight-medium">{{ event.name }}</h2>
              <p class="text-body-2 em-muted mb-0">
                {{ dateLabel }} · {{ event.default_people }} personnes attendues
              </p>
            </div>

            <div class="d-flex align-center ga-1">
              <v-btn
                size="small"
                variant="tonal"
                prepend-icon="mdi-cart-outline"
                :loading="generating"
                @click="openGroceryList"
              >
                {{ existingList ? 'Liste de courses' : 'Générer la liste' }}
              </v-btn>
              <v-btn
                v-if="isOwner"
                size="small"
                variant="text"
                icon="mdi-pencil-outline"
                aria-label="Modifier l’événement"
                @click="events.openEditForm(event)"
              />
            </div>
          </div>

          <!-- Members: a way into each other's pages, which is the only place
               you can see what someone eats or what they cook. -->
          <div class="d-flex align-center flex-wrap ga-2 mb-6">
            <v-chip
              v-for="member in event.members"
              :key="member.id"
              size="small"
              variant="outlined"
              @click="openMember(member)"
            >
              <UserAvatar :seed="member.avatar_seed" :size="18" class="me-2" />
              {{ member.display_name }}
            </v-chip>
          </div>

          <v-progress-linear v-if="plan.loading" indeterminate class="mb-3" />

          <PlannerCalendar :event="event" @open-slot="openSlot" />
        </template>
      </v-container>
    </div>

    <MealSlotDialog
      v-if="event && editingSlot"
      v-model="slotDialogOpen"
      :event="event"
      :day="editingSlot.day"
      :slot="editingSlot.slot"
    />

    <EventFormDialog />
  </div>
</template>
