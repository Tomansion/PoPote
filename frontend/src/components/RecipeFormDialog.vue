<script setup>
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { api } from '@/api/client'
import { RECIPE_TYPES, useRecipesStore } from '@/stores/recipes'

const { categories } = storeToRefs(useRecipesStore())

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  recipe: { type: Object, default: null },
  fullscreen: { type: Boolean, default: false },
  // Async; rejecting keeps the dialog open so the user does not lose their input
  // (a failed save is usually "you are offline", which is worth retrying).
  onSubmit: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue'])

const UNITS = ['g', 'kg', 'ml', 'cl', 'l', 'u.', 'c.à.s', 'c.à.c', 'pincée', 'tranches']

// An AI-generated draft is passed in via `recipe` too, so it can prefill the
// form, but it has no `id` yet — only a real edit should say so, or read the
// aisle already picked for each ingredient as final (see the watcher below).
const isEdit = computed(() => Boolean(props.recipe?.id))
const saving = ref(false)
const nameError = ref('')
const aisles = ref([])

function blankIngredient() {
  // `aisleOverridden` is UI-only state: once the user picks an aisle by hand we
  // stop overwriting it with the server's guess. It is stripped before saving.
  return { name: '', quantity: null, unit: 'g', aisle: '', aisleOverridden: false }
}

function blankForm() {
  return {
    name: '',
    type: 'Plat',
    category: '',
    servings: 4,
    prep_minutes: null,
    cook_minutes: null,
    temperature: 'Chaud',
    favorite: false,
    ingredients: [blankIngredient(), blankIngredient()],
    steps: ['', ''],
    notes: '',
  }
}

const form = ref(blankForm())

watch(
  () => [props.modelValue, props.recipe],
  ([open]) => {
    if (!open) return
    nameError.value = ''

    if (props.recipe) {
      // A real edit carries aisles already picked for this recipe, which
      // must not be silently overwritten. An AI draft's ingredients are new
      // to the form, exactly like ones just typed in — let detection run.
      const keepAisles = isEdit.value
      form.value = {
        ...JSON.parse(JSON.stringify(props.recipe)),
        ingredients: props.recipe.ingredients.length
          ? props.recipe.ingredients.map((i) => ({ ...i, aisleOverridden: keepAisles }))
          : [blankIngredient()],
        steps: props.recipe.steps.length ? [...props.recipe.steps] : [''],
      }
    } else {
      form.value = blankForm()
    }
  },
  { immediate: true },
)

// Aisle vocabulary for the manual override dropdown.
watch(
  () => props.modelValue,
  async (open) => {
    if (!open || aisles.value.length) return
    try {
      const response = await api.listAisles()
      aisles.value = response.aisles
    } catch {
      // Offline: the override dropdown simply stays unavailable.
    }
  },
)

// "rayon détecté" — asked of the server so the keyword table has a single
// source of truth. Debounced per ingredient to avoid a call per keystroke.
const detectTimers = new Map()

function scheduleAisleDetection(index) {
  const ingredient = form.value.ingredients[index]
  if (!ingredient || ingredient.aisleOverridden) return

  clearTimeout(detectTimers.get(index))
  const name = ingredient.name

  if (!name.trim()) {
    ingredient.aisle = ''
    return
  }

  detectTimers.set(
    index,
    setTimeout(async () => {
      try {
        const { aisle } = await api.detectAisle(name)
        const current = form.value.ingredients[index]
        // The row may have been removed or retyped while the call was in flight.
        if (current && current.name === name && !current.aisleOverridden) {
          current.aisle = aisle
        }
      } catch {
        // Offline: the server fills the aisle in on save anyway.
      }
    }, 400),
  )
}

function overrideAisle(index, aisle) {
  form.value.ingredients[index].aisle = aisle
  form.value.ingredients[index].aisleOverridden = true
}

function addIngredient() {
  form.value.ingredients.push(blankIngredient())
}

function removeIngredient(index) {
  form.value.ingredients.splice(index, 1)
  if (!form.value.ingredients.length) addIngredient()
}

function addStep() {
  form.value.steps.push('')
}

function removeStep(index) {
  form.value.steps.splice(index, 1)
  if (!form.value.steps.length) addStep()
}

function close() {
  emit('update:modelValue', false)
}

async function submit() {
  if (!form.value.name.trim()) {
    nameError.value = 'Le nom est obligatoire'
    return
  }
  nameError.value = ''

  const payload = {
    name: form.value.name.trim(),
    type: form.value.type,
    category: form.value.category?.trim() || '',
    servings: Number(form.value.servings) || 1,
    prep_minutes: Number(form.value.prep_minutes) || 0,
    cook_minutes: Number(form.value.cook_minutes) || 0,
    temperature: form.value.temperature,
    favorite: Boolean(form.value.favorite),
    ingredients: form.value.ingredients
      .filter((i) => i.name.trim())
      .map((i) => ({
        name: i.name.trim(),
        quantity: i.quantity === '' || i.quantity === null ? null : Number(i.quantity),
        unit: i.unit || '',
        aisle: i.aisle || '',
      })),
    steps: form.value.steps.map((s) => s.trim()).filter(Boolean),
    notes: form.value.notes?.trim() || '',
  }

  saving.value = true
  try {
    await props.onSubmit(payload)
    close()
  } catch {
    // The store already surfaced the reason in a snackbar; keep the form open.
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    :fullscreen="fullscreen"
    :max-width="fullscreen ? undefined : 720"
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card flat>
      <v-card-title class="d-flex align-center ga-2 pa-4">
        <v-btn variant="text" size="small" prepend-icon="mdi-close" @click="close">
          annuler
        </v-btn>
        <v-spacer />
        <span class="text-subtitle-1">
          {{ isEdit ? 'Modifier la recette' : 'Nouvelle recette' }}
        </span>
        <v-spacer />
        <v-btn variant="text" size="small" :loading="saving" @click="submit">OK</v-btn>
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <v-text-field
          v-model="form.name"
          label="Nom"
          class="mb-4"
          :error-messages="nameError"
          autofocus
        />

        <div class="d-flex ga-3 mb-3 flex-wrap">
          <v-select
            v-model="form.type"
            :items="RECIPE_TYPES"
            label="Type"
            class="flex-1-1"
            style="min-width: 140px"
          />
          <v-combobox
            v-model="form.category"
            :items="categories"
            label="Catégorie"
            hint="Ex. Asiatique, Hiver, Été…"
            persistent-hint
            clearable
            class="flex-1-1"
            style="min-width: 140px"
          />
          <v-text-field
            v-model.number="form.servings"
            label="Portions"
            type="number"
            min="1"
            class="flex-1-1"
            style="min-width: 100px"
          />
        </div>

        <!-- Wraps rather than squeezing: at phone widths the three fields do
             not fit on one line and the select becomes unreadable. -->
        <div class="d-flex ga-3 mb-6 flex-wrap">
          <v-text-field
            v-model.number="form.prep_minutes"
            label="Prép. (min)"
            type="number"
            min="0"
            class="flex-1-1"
            style="min-width: 130px"
          />
          <v-text-field
            v-model.number="form.cook_minutes"
            label="Cuisson (min)"
            type="number"
            min="0"
            class="flex-1-1"
            style="min-width: 130px"
          />
          <v-select
            v-model="form.temperature"
            :items="['Chaud', 'Froid']"
            label="Service"
            class="flex-1-1"
            style="min-width: 140px"
          />
        </div>

        <div class="text-subtitle-2 font-weight-medium mb-2">Ingrédients</div>

        <div
          v-for="(ingredient, index) in form.ingredients"
          :key="index"
          class="mb-3"
        >
          <div class="d-flex ga-2 align-center">
            <v-text-field
              v-model="ingredient.name"
              label="Ingrédient"
              class="flex-grow-1"
              @update:model-value="scheduleAisleDetection(index)"
            />
            <v-text-field
              v-model="ingredient.quantity"
              label="Qté"
              type="number"
              style="max-width: 96px"
            />
            <v-combobox
              v-model="ingredient.unit"
              :items="UNITS"
              label="Unité"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
              style="max-width: 110px"
            />
            <v-btn
              icon="mdi-close"
              variant="text"
              size="x-small"
              aria-label="Retirer l’ingrédient"
              @click="removeIngredient(index)"
            />
          </div>

          <div
            v-if="ingredient.aisle"
            class="d-flex align-center ga-1 text-caption mt-1 ms-1"
          >
            <span :class="ingredient.aisleOverridden ? 'em-muted' : 'text-info'">
              {{ ingredient.aisleOverridden ? 'rayon' : 'rayon détecté' }} :
              {{ ingredient.aisle }}
            </span>
            <v-menu v-if="aisles.length">
              <template #activator="{ props: menuProps }">
                <v-btn
                  v-bind="menuProps"
                  variant="text"
                  size="x-small"
                  class="text-info"
                >
                  modifier
                </v-btn>
              </template>
              <v-list density="compact">
                <v-list-item
                  v-for="aisle in aisles"
                  :key="aisle"
                  :title="aisle"
                  @click="overrideAisle(index, aisle)"
                />
              </v-list>
            </v-menu>
          </div>
        </div>

        <v-btn
          block
          size="small"
          class="mb-6"
          style="border-style: dashed"
          prepend-icon="mdi-plus"
          @click="addIngredient"
        >
          ingrédient
        </v-btn>

        <div class="text-subtitle-2 font-weight-medium mb-2">Étapes</div>

        <div
          v-for="(step, index) in form.steps"
          :key="index"
          class="d-flex ga-2 align-center mb-2"
        >
          <span class="em-muted em-mono" style="min-width: 1rem">{{ index + 1 }}</span>
          <v-text-field v-model="form.steps[index]" label="Étape" />
          <v-btn
            icon="mdi-close"
            variant="text"
            size="x-small"
            aria-label="Retirer l’étape"
            @click="removeStep(index)"
          />
        </div>

        <v-btn
          block
          size="small"
          class="mb-6"
          style="border-style: dashed"
          prepend-icon="mdi-plus"
          @click="addStep"
        >
          étape
        </v-btn>

        <v-textarea v-model="form.notes" label="Notes" rows="3" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>
