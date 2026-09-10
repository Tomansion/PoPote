<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MemberAssign from '@/components/MemberAssign.vue'
import RecipePickerDialog from '@/components/RecipePickerDialog.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import { useEventsStore } from '@/stores/events'
import {
  SLOTS,
  SLOT_ICONS,
  SLOT_LABELS,
  daysBetween,
  emptySlot,
  fromISODate,
  newMealId,
  usePlanStore,
} from '@/stores/plan'

/**
 * One day of an event: its three parts, open at once.
 *
 * This used to be a dialog per part of the day, which meant three round trips
 * through a modal to plan a Saturday. As a page it holds the whole day, it
 * survives a reload, and Back leaves it — including Android's, inside the APK.
 *
 * Everything saves as it is changed rather than behind an "Enregistrer": the
 * page is shared by every member live, and a draft nobody else can see is the
 * wrong model for a kitchen table. Numbers commit on blur, which is the one
 * place a keystroke-by-keystroke save would be wrong.
 */
const route = useRoute()
const router = useRouter()

const auth = useAuthStore()
const events = useEventsStore()
const plan = usePlanStore()

const eventId = computed(() => route.params.id)
const day = computed(() => route.params.day)
const event = computed(() => events.byId(eventId.value))
const members = computed(() => event.value?.members ?? [])

const picking = ref(null)
const drafts = ref({})
const slotRefs = ref({})

const eventDays = computed(() =>
  event.value ? daysBetween(event.value.starts_on, event.value.ends_on) : [],
)
const dayIndex = computed(() => eventDays.value.indexOf(day.value))
const inEvent = computed(() => dayIndex.value >= 0)

const dayLabel = computed(() =>
  day.value
    ? fromISODate(day.value).toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
      })
    : '',
)

const defaultPeople = computed(() => event.value?.default_people ?? 4)

const dayCooks = computed(() => plan.dayCooksFor(eventId.value, day.value))

function goToDay(offset) {
  const target = eventDays.value[dayIndex.value + offset]
  if (target) router.push({ name: 'eventDay', params: { id: eventId.value, day: target } })
}

/**
 * Mirror the stored plan into editable copies.
 *
 * Re-run whenever the plan changes, including after our own save and after
 * another member's — so a headcount someone else corrected appears here
 * rather than being overwritten by a stale copy on the next edit.
 */
watch(
  () => [eventId.value, day.value, plan.planFor(eventId.value).days?.[day.value]],
  () => {
    const stored = plan.planFor(eventId.value).days?.[day.value] ?? {}
    drafts.value = Object.fromEntries(
      SLOTS.map((slot) => {
        const current = stored[slot] ?? emptySlot()
        return [
          slot,
          {
            skipped: Boolean(current.skipped),
            people: current.people ?? null,
            recipes: (current.recipes ?? []).map((meal) => ({
              ...meal,
              cooks: [...(meal.cooks ?? [])],
            })),
          },
        ]
      }),
    )
  },
  { immediate: true, deep: true },
)

// The plan is what every slot on this page reads from, and a day can be
// opened cold — from a bookmark, or a reload. The event itself arrives with
// the app's own startup load, which is where every other view gets it too.
watch(
  eventId,
  (id) => {
    if (id) plan.load(id).catch(() => {})
  },
  { immediate: true },
)

// Arriving from a click on one part of the day in the calendar: put that part
// on screen rather than the top of the page.
watch(
  () => route.query.slot,
  async (slot) => {
    if (!slot || !SLOTS.includes(slot)) return
    await nextTick()
    slotRefs.value[slot]?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  },
  { immediate: true },
)

/** How many people this part of the day expects, event default included. */
const peopleFor = (slot) => drafts.value[slot]?.people ?? defaultPeople.value

async function save(slot) {
  const draft = drafts.value[slot]
  if (!draft) return
  try {
    await plan.setSlot(eventId.value, day.value, slot, {
      skipped: draft.skipped,
      people:
        draft.people === '' || draft.people === null || draft.people === undefined
          ? null
          : Number(draft.people),
      recipes: draft.recipes.map((meal) => ({
        ...meal,
        servings: Number(meal.servings) || 1,
      })),
    })
  } catch {
    // The store raised the toast, and the watcher above puts the page back to
    // whatever the server still holds.
  }
}

function setSkipped(slot, value) {
  drafts.value[slot].skipped = value
  save(slot)
}

function addRecipe(recipe) {
  const slot = picking.value
  picking.value = null
  if (!slot) return

  const draft = drafts.value[slot]
  draft.skipped = false
  draft.recipes.push({
    uid: newMealId(),
    recipe_id: recipe.id,
    owner_id: recipe.owner_id ?? '',
    name: recipe.name,
    // Everyone at the table eats it unless told otherwise.
    servings: peopleFor(slot),
    cooks: [],
  })
  save(slot)
}

function removeRecipe(slot, uid) {
  drafts.value[slot].recipes = drafts.value[slot].recipes.filter((m) => m.uid !== uid)
  save(slot)
}

function setMealCooks(slot, uid, cooks) {
  const meal = drafts.value[slot].recipes.find((m) => m.uid === uid)
  if (!meal) return
  meal.cooks = cooks
  save(slot)
}

function setDayCooks(cooks) {
  plan.setDayCooks(eventId.value, day.value, cooks).catch(() => {})
}

/** "Je m'en occupe" for the whole day — one press instead of two. */
function takeDay() {
  const me = auth.user?.id
  if (!me) return
  setDayCooks(dayCooks.value.includes(me) ? dayCooks.value.filter((id) => id !== me) : [...dayCooks.value, me])
}

const memberName = (id) => members.value.find((m) => m.id === id)?.display_name ?? ''
const memberSeed = (id) => members.value.find((m) => m.id === id)?.avatar_seed ?? 0

const openRecipe = (meal) => router.push({ name: 'recipe', params: { id: meal.recipe_id } })
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <div class="em-scroll flex-grow-1">
      <v-container class="pa-4" style="max-width: 820px">
        <div class="d-flex align-center ga-1 mb-3">
          <v-btn
            variant="text"
            size="small"
            prepend-icon="mdi-arrow-left"
            @click="router.push({ name: 'event', params: { id: eventId } })"
          >
            {{ event?.name ?? 'événement' }}
          </v-btn>
          <v-spacer />
          <v-btn
            variant="text"
            size="small"
            icon="mdi-chevron-left"
            aria-label="Jour précédent"
            :disabled="dayIndex <= 0"
            @click="goToDay(-1)"
          />
          <v-btn
            variant="text"
            size="small"
            icon="mdi-chevron-right"
            aria-label="Jour suivant"
            :disabled="dayIndex < 0 || dayIndex >= eventDays.length - 1"
            @click="goToDay(1)"
          />
        </div>

        <div v-if="event && !inEvent" class="text-center em-muted py-12">
          <v-icon icon="mdi-calendar-alert" size="48" class="mb-4" />
          <p class="text-body-2">Ce jour ne fait pas partie de l’événement.</p>
        </div>

        <template v-else>
          <h2 class="text-h6 font-weight-medium text-capitalize mb-1">{{ dayLabel }}</h2>
          <p class="text-body-2 em-muted mb-4">
            {{ defaultPeople }} personnes attendues sur l’événement
          </p>

          <!-- Responsible for the day as a whole: shopping, cooking, or just
               keeping an eye on it. Separate from who makes each dish. -->
          <v-sheet class="em-outline pa-3 mb-6" rounded="lg">
            <div class="d-flex align-center ga-2 flex-wrap">
              <v-icon icon="mdi-account-star-outline" size="20" class="text-primary" />
              <span class="text-body-2 font-weight-medium">Responsables du jour</span>
              <v-spacer />
              <v-btn
                size="small"
                variant="text"
                :prepend-icon="
                  dayCooks.includes(auth.user?.id)
                    ? 'mdi-account-check'
                    : 'mdi-hand-back-right-outline'
                "
                @click="takeDay"
              >
                {{ dayCooks.includes(auth.user?.id) ? 'Je me retire' : 'Je m’en occupe' }}
              </v-btn>
              <MemberAssign
                :members="members"
                :model-value="dayCooks"
                :size="26"
                label="Responsables du jour"
                placeholder="Assigner"
                @update:model-value="setDayCooks"
              />
            </div>
          </v-sheet>

          <!-- ================== The three parts of the day ================== -->
          <section
            v-for="slot in SLOTS"
            :key="slot"
            :ref="(el) => (slotRefs[slot] = el)"
            class="mb-6"
          >
            <SectionHeader :icon="SLOT_ICONS[slot]" :title="SLOT_LABELS[slot]">
              <template #action>
                <v-btn
                  v-if="!drafts[slot]?.skipped"
                  icon="mdi-plus"
                  variant="text"
                  size="small"
                  :aria-label="`Ajouter une recette — ${SLOT_LABELS[slot]}`"
                  @click="picking = slot"
                />
              </template>
            </SectionHeader>

            <v-sheet class="em-outline pa-3" rounded="lg">
              <div class="d-flex align-center flex-wrap ga-4">
                <v-switch
                  :model-value="drafts[slot]?.skipped ?? false"
                  color="primary"
                  density="compact"
                  hide-details
                  label="Rien à cuisiner"
                  @update:model-value="setSkipped(slot, $event)"
                />
                <v-text-field
                  v-if="!drafts[slot]?.skipped"
                  v-model="drafts[slot].people"
                  type="number"
                  min="0"
                  max="500"
                  label="À table"
                  density="compact"
                  variant="outlined"
                  hide-details
                  clearable
                  :placeholder="String(defaultPeople)"
                  persistent-placeholder
                  style="max-width: 150px"
                  @change="save(slot)"
                  @click:clear="save(slot)"
                />
              </div>

              <p v-if="drafts[slot]?.skipped" class="text-caption em-muted mb-0 mt-2">
                Repas pris dehors, sauté, ou déjà réglé autrement. Ce qui est
                planifié ici est conservé et ne compte pas dans les courses.
              </p>

              <template v-else>
                <v-divider class="my-3" />

                <div v-if="drafts[slot]?.recipes.length" class="d-flex flex-column ga-2">
                  <v-sheet
                    v-for="meal in drafts[slot].recipes"
                    :key="meal.uid"
                    class="em-outline pa-3"
                    rounded="lg"
                  >
                    <div class="d-flex align-center ga-2 mb-2">
                      <div class="flex-grow-1" style="min-width: 0">
                        <button
                          type="button"
                          class="text-body-2 font-weight-medium text-truncate pp-link"
                          @click="openRecipe(meal)"
                        >
                          {{ meal.name }}
                        </button>
                        <div
                          v-if="memberName(meal.owner_id)"
                          class="text-caption em-muted d-flex align-center ga-1"
                        >
                          <UserAvatar :seed="memberSeed(meal.owner_id)" :size="14" />
                          recette de {{ memberName(meal.owner_id) }}
                        </div>
                      </div>
                      <v-btn
                        icon="mdi-close"
                        variant="text"
                        size="x-small"
                        aria-label="Retirer du menu"
                        @click="removeRecipe(slot, meal.uid)"
                      />
                    </div>

                    <div class="d-flex align-center flex-wrap ga-3">
                      <v-text-field
                        v-model.number="meal.servings"
                        type="number"
                        min="1"
                        max="500"
                        label="Portions"
                        density="compact"
                        variant="outlined"
                        hide-details
                        style="max-width: 130px"
                        @change="save(slot)"
                      />
                      <v-spacer />
                      <div class="d-flex align-center ga-1">
                        <span class="text-caption em-muted">aux fourneaux</span>
                        <MemberAssign
                          :members="members"
                          :model-value="meal.cooks ?? []"
                          label="Qui cuisine ce plat ?"
                          @update:model-value="setMealCooks(slot, meal.uid, $event)"
                        />
                      </div>
                    </div>
                  </v-sheet>
                </div>

                <div v-else class="d-flex align-center ga-2">
                  <p class="text-body-2 em-muted mb-0 flex-grow-1">
                    Rien de prévu pour l’instant.
                  </p>
                  <v-btn
                    size="small"
                    variant="tonal"
                    prepend-icon="mdi-plus"
                    @click="picking = slot"
                  >
                    Ajouter une recette
                  </v-btn>
                </div>
              </template>
            </v-sheet>
          </section>
        </template>
      </v-container>
    </div>

    <RecipePickerDialog
      :model-value="Boolean(picking)"
      :event-id="eventId"
      :members="members"
      @update:model-value="picking = $event ? picking : null"
      @pick="addRecipe"
    />
  </div>
</template>

<style scoped>
/* A recipe name that is also a way into the recipe, without looking like a
   button in the middle of a form. */
.pp-link {
  background: none;
  border: 0;
  padding: 0;
  max-width: 100%;
  text-align: start;
  cursor: pointer;
  color: inherit;
}

.pp-link:hover {
  text-decoration: underline;
}
</style>
