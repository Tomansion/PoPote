<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { api } from '@/api/client'
import SectionHeader from '@/components/SectionHeader.vue'
import { RECIPE_TYPES, useRecipesStore } from '@/stores/recipes'
import { placeholderGradient } from '@/utils/gradient'

const { categories } = storeToRefs(useRecipesStore())

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  recipe: { type: Object, default: null },
  fullscreen: { type: Boolean, default: false },
  // Async; rejecting keeps the dialog open so the user does not lose their input
  // (a failed save is usually "you are offline", which is worth retrying).
  // Called with the recipe payload and whatever the user did to the photo,
  // since a new recipe has no id to upload against until it has been created.
  onSubmit: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue'])

const UNITS = [
  'g',
  'kg',
  'ml',
  'cl',
  'l',
  'u.',
  'c.à.s',
  'c.à.c',
  'pincée',
  'tranches',
]

const isEdit = computed(() => Boolean(props.recipe?.id))
const saving = ref(false)
const nameError = ref('')
const aisles = ref([])

function blankIngredient() {
  // `aisleOverridden` is UI-only state: once the user picks an aisle by hand we
  // stop overwriting it with the server's guess. It is stripped before saving.
  return {
    name: '',
    quantity: null,
    unit: 'g',
    aisle: '',
    aisleOverridden: false,
  }
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

// ------------------------------------------------------------------ photo
//
// The picture is not part of the recipe payload — it goes to its own endpoint,
// against an id that a *new* recipe does not have yet. So the form only
// records the intent, and hands it to the caller on submit to apply once the
// recipe certainly exists.

const fileInput = ref(null)
/** A File the user picked but that has not been uploaded yet. */
const pendingFile = ref(null)
/** Local blob URL for that file, so the preview is instant and offline. */
const pendingUrl = ref('')
/** True when the user removed an existing photo without picking a new one. */
const removingPhoto = ref(false)

function releasePreview() {
  if (pendingUrl.value) URL.revokeObjectURL(pendingUrl.value)
  pendingUrl.value = ''
}

const currentPhoto = computed(() => {
  if (pendingUrl.value) return pendingUrl.value
  if (removingPhoto.value) return ''
  return props.recipe?.image_url || ''
})

const gradient = computed(() => placeholderGradient(props.recipe?.id ?? form.value.name))

function pickPhoto() {
  fileInput.value?.click()
}

function onPhotoPicked(event) {
  const file = event.target.files?.[0]
  // Reset the input, or picking the same file twice in a row fires nothing.
  event.target.value = ''
  if (!file) return

  releasePreview()
  pendingFile.value = file
  pendingUrl.value = URL.createObjectURL(file)
  removingPhoto.value = false
}

function dropPhoto() {
  releasePreview()
  pendingFile.value = null
  removingPhoto.value = true
}

onBeforeUnmount(releasePreview)

watch(
  () => [props.modelValue, props.recipe],
  ([open]) => {
    if (!open) return
    nameError.value = ''
    releasePreview()
    pendingFile.value = null
    removingPhoto.value = false

    if (props.recipe) {
      // A real edit carries aisles already picked for this recipe, which must
      // not be silently overwritten by a fresh round of detection.
      form.value = {
        ...JSON.parse(JSON.stringify(props.recipe)),
        ingredients: props.recipe.ingredients.length
          ? props.recipe.ingredients.map((i) => ({ ...i, aisleOverridden: true }))
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
    await props.onSubmit(payload, {
      file: pendingFile.value,
      remove: removingPhoto.value && !pendingFile.value,
    })
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
      <!-- Icon-only close + a title that shrinks with text-truncate, rather than
           "annuler" + two spacers — on a phone-width dialog that combination
           left too little room and the title crowded into the OK button. -->
      <v-card-title class="d-flex align-center ga-2 pa-4">
        <v-btn
          variant="text"
          size="small"
          icon="mdi-close"
          aria-label="Annuler"
          @click="close"
        />
        <span class="text-subtitle-1 flex-grow-1 text-center text-truncate">
          {{ isEdit ? 'Modifier la recette' : 'Nouvelle recette' }}
        </span>
        <v-btn variant="text" size="small" :loading="saving" @click="submit">OK</v-btn>
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <SectionHeader icon="mdi-silverware-fork-knife" title="Recette" />
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

        <!-- ------------------------------ photo ------------------------------ -->
        <SectionHeader icon="mdi-camera-outline" title="Photo">
          <template #action>
            <v-btn
              v-if="currentPhoto"
              icon="mdi-delete-outline"
              variant="text"
              size="small"
              aria-label="Retirer la photo"
              @click="dropPhoto"
            />
            <v-btn
              :icon="currentPhoto ? 'mdi-image-edit-outline' : 'mdi-plus'"
              variant="text"
              size="small"
              :aria-label="currentPhoto ? 'Remplacer la photo' : 'Ajouter une photo'"
              @click="pickPhoto"
            />
          </template>
        </SectionHeader>

        <input
          ref="fileInput"
          type="file"
          accept="image/*"
          class="d-none"
          @change="onPhotoPicked"
        />

        <div class="mb-6">
          <v-img
            v-if="currentPhoto"
            :src="currentPhoto"
            height="160"
            cover
            rounded="lg"
            class="em-outline"
          />
          <!-- No photo: the same gradient the card will show, so the choice
               reads as a style rather than as something still loading. -->
          <div
            v-else
            class="em-outline pp-photo-empty d-flex flex-column align-center justify-center"
            :style="{ background: gradient }"
            @click="pickPhoto"
          >
            <v-icon icon="mdi-image-plus" size="28" class="mb-1" />
            <span class="text-caption">Ajouter une photo</span>
          </div>
          <p v-if="pendingFile" class="text-caption em-muted mt-1">
            Envoyée à l’enregistrement.
          </p>
        </div>

        <!-- --------------------------- ingredients --------------------------- -->
        <SectionHeader icon="mdi-food-variant" title="Ingrédients">
          <template #action>
            <v-btn
              icon="mdi-plus"
              variant="text"
              size="small"
              aria-label="Ajouter un ingrédient"
              @click="addIngredient"
            />
          </template>
        </SectionHeader>

        <!-- Name on its own row, quantity + unit below: side by side with the
             name too, all three got squeezed to the point of clipping on a
             phone-width dialog (a full ingredient name needs real room). -->
        <div v-for="(ingredient, index) in form.ingredients" :key="index" class="mb-4">
          <div class="d-flex ga-2 align-center mb-2">
            <v-text-field
              v-model="ingredient.name"
              label="Ingrédient"
              class="flex-grow-1"
              hide-details="auto"
              @update:model-value="scheduleAisleDetection(index)"
            />
            <v-btn
              icon="mdi-close"
              variant="text"
              size="small"
              aria-label="Retirer l’ingrédient"
              @click="removeIngredient(index)"
            />
          </div>

          <div class="d-flex ga-2">
            <v-text-field
              v-model="ingredient.quantity"
              label="Qté"
              type="number"
              hide-details="auto"
              style="max-width: 140px"
            />
            <v-combobox
              v-model="ingredient.unit"
              :items="UNITS"
              label="Unité"
              variant="outlined"
              density="comfortable"
              hide-details="auto"
              class="flex-grow-1"
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
                <v-btn v-bind="menuProps" variant="text" size="x-small" class="text-info">
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

        <!-- ------------------------------ steps ------------------------------ -->
        <SectionHeader icon="mdi-format-list-numbered" title="Étapes" class="mt-6">
          <template #action>
            <v-btn
              icon="mdi-plus"
              variant="text"
              size="small"
              aria-label="Ajouter une étape"
              @click="addStep"
            />
          </template>
        </SectionHeader>

        <div
          v-for="(step, index) in form.steps"
          :key="index"
          class="d-flex ga-2 align-start mb-2"
        >
          <span class="em-muted em-mono mt-3" style="min-width: 1rem">{{ index + 1 }}</span>
          <v-textarea
            v-model="form.steps[index]"
            label="Étape"
            rows="2"
            auto-grow
            hide-details="auto"
            class="flex-grow-1"
          />
          <v-btn
            icon="mdi-close"
            variant="text"
            size="x-small"
            class="mt-1"
            aria-label="Retirer l’étape"
            @click="removeStep(index)"
          />
        </div>

        <SectionHeader icon="mdi-note-text" title="Notes" class="mt-6" />
        <v-textarea v-model="form.notes" rows="3" />
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.pp-photo-empty {
  height: 160px;
  border-radius: 8px;
  cursor: pointer;
  color: rgba(0, 0, 0, 0.5);
}
</style>
