<script setup>
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'

import RecipePickerDialog from '@/components/RecipePickerDialog.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { emptySlot, newMealId, SLOT_ICONS, SLOT_LABELS, usePlanStore } from '@/stores/plan'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  event: { type: Object, required: true },
  day: { type: String, default: '' },
  slot: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

const plan = usePlanStore()
const { mdAndUp } = useDisplay()

/**
 * A local copy, saved in one write.
 *
 * The alternative — a request per keystroke on a servings field — would put
 * three people's half-typed numbers on each other's screens. One "Enregistrer"
 * per visit to a slot is both calmer and a single broadcast to the others.
 */
const draft = ref(emptySlot())
const saving = ref(false)
const picking = ref(false)

watch(
  () => [props.modelValue, props.day, props.slot],
  ([open]) => {
    if (!open || !props.day) return
    const current = plan.slotFor(props.event.id, props.day, props.slot)
    draft.value = {
      skipped: current.skipped,
      people: current.people,
      recipes: current.recipes.map((meal) => ({ ...meal })),
    }
    picking.value = false
  },
  { immediate: true },
)

const dayLabel = computed(() => {
  if (!props.day) return ''
  const [y, m, d] = props.day.split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString('fr-FR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })
})

/** How many people this slot expects, falling back to the event's number. */
const effectivePeople = computed(() =>
  draft.value.people ?? props.event.default_people ?? 4,
)

const memberName = (id) =>
  props.event.members?.find((m) => m.id === id)?.display_name ?? ''
const memberSeed = (id) => props.event.members?.find((m) => m.id === id)?.avatar_seed ?? 0

function addRecipe(recipe) {
  picking.value = false
  draft.value.skipped = false
  draft.value.recipes.push({
    uid: newMealId(),
    recipe_id: recipe.id,
    owner_id: recipe.owner_id ?? '',
    name: recipe.name,
    // Everyone at the table eats it unless told otherwise.
    servings: effectivePeople.value,
  })
}

function removeRecipe(uid) {
  draft.value.recipes = draft.value.recipes.filter((meal) => meal.uid !== uid)
}

async function save() {
  saving.value = true
  try {
    await plan.setSlot(props.event.id, props.day, props.slot, {
      skipped: draft.value.skipped,
      people:
        draft.value.people === '' || draft.value.people === null
          ? null
          : Number(draft.value.people),
      // Marking a slot "rien à cuisiner" keeps whatever was planned, so
      // un-ticking it brings the meals back rather than losing them.
      recipes: draft.value.recipes.map((meal) => ({
        ...meal,
        servings: Number(meal.servings) || 1,
      })),
    })
    emit('update:modelValue', false)
  } catch {
    // The store raised the toast; leave the dialog open with the input intact.
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    :fullscreen="!mdAndUp"
    :max-width="mdAndUp ? 560 : undefined"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card flat>
      <v-card-title class="d-flex align-center ga-2 pa-4">
        <v-btn
          variant="text"
          size="small"
          icon="mdi-close"
          aria-label="Fermer"
          @click="emit('update:modelValue', false)"
        />
        <div class="flex-grow-1 text-center">
          <div class="text-subtitle-1 text-capitalize">{{ dayLabel }}</div>
          <div class="text-caption em-muted d-flex align-center justify-center ga-1">
            <v-icon :icon="SLOT_ICONS[slot]" size="14" />
            {{ SLOT_LABELS[slot] }}
          </div>
        </div>
        <v-btn variant="text" size="small" :loading="saving" @click="save">OK</v-btn>
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <v-switch
          v-model="draft.skipped"
          color="primary"
          density="compact"
          hide-details
          label="Rien à cuisiner"
          class="mb-2"
        />
        <p class="text-caption em-muted mb-5">
          Pour les repas pris dehors, sautés, ou déjà réglés autrement. Ce qui
          est planifié ici est conservé et ne compte pas dans les courses.
        </p>

        <template v-if="!draft.skipped">
          <SectionHeader icon="mdi-account-group-outline" title="À table" />
          <v-text-field
            v-model="draft.people"
            type="number"
            min="0"
            max="500"
            label="Personnes"
            :placeholder="String(event.default_people ?? 4)"
            persistent-placeholder
            :hint="
              draft.people === null || draft.people === ''
                ? `Par défaut : ${event.default_people ?? 4} personnes pour cet événement`
                : 'Valeur propre à ce repas'
            "
            persistent-hint
            clearable
            class="mb-6"
          />

          <SectionHeader icon="mdi-silverware-fork-knife" title="Au menu">
            <template #action>
              <v-btn
                icon="mdi-plus"
                variant="text"
                size="small"
                aria-label="Ajouter une recette"
                @click="picking = true"
              />
            </template>
          </SectionHeader>

          <div v-if="draft.recipes.length" class="d-flex flex-column ga-3 mb-4">
            <v-sheet
              v-for="meal in draft.recipes"
              :key="meal.uid"
              class="em-outline pa-3"
              rounded="lg"
            >
              <div class="d-flex align-center ga-2 mb-2">
                <div class="flex-grow-1" style="min-width: 0">
                  <div class="text-body-2 font-weight-medium text-truncate">
                    {{ meal.name }}
                  </div>
                  <div
                    v-if="memberName(meal.owner_id)"
                    class="text-caption em-muted d-flex align-center ga-1"
                  >
                    <UserAvatar :seed="memberSeed(meal.owner_id)" :size="14" />
                    {{ memberName(meal.owner_id) }}
                  </div>
                </div>
                <v-btn
                  icon="mdi-close"
                  variant="text"
                  size="x-small"
                  aria-label="Retirer du menu"
                  @click="removeRecipe(meal.uid)"
                />
              </div>
              <v-text-field
                v-model.number="meal.servings"
                type="number"
                min="1"
                max="500"
                label="Portions à préparer"
                density="compact"
                hide-details
              />
            </v-sheet>
          </div>

          <p v-else class="text-body-2 em-muted mb-4">
            Rien de prévu pour l’instant.
          </p>
        </template>
      </v-card-text>
    </v-card>
  </v-dialog>

  <RecipePickerDialog
    v-model="picking"
    :event-id="event.id"
    :members="event.members ?? []"
    @pick="addRecipe"
  />
</template>
