<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  recipe: { type: Object, required: true },
  showBack: { type: Boolean, default: false },
})

const emit = defineEmits(['back', 'edit', 'delete', 'toggle-favorite', 'not-implemented'])

// Local override of the serving count: scales quantities for display only,
// it is never written back to the recipe.
const servings = ref(props.recipe.servings || 1)

watch(
  () => props.recipe.id,
  () => {
    servings.value = props.recipe.servings || 1
  },
)

const scale = computed(() => servings.value / (props.recipe.servings || 1))

const isScaled = computed(() => servings.value !== props.recipe.servings)

function formatQuantity(quantity) {
  if (quantity === null || quantity === undefined || quantity === '') return ''
  const scaled = quantity * scale.value
  // Keep at most one decimal, and drop it when it adds nothing (1.0 -> 1).
  const rounded = Math.round(scaled * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1).replace('.', ',')
}

const chips = computed(() => {
  const list = [props.recipe.type, `${props.recipe.servings} pers`]
  if (props.recipe.prep_minutes) list.push(`Prép ${props.recipe.prep_minutes} min`)
  if (props.recipe.cook_minutes) list.push(`Cuisson ${props.recipe.cook_minutes} min`)
  list.push(props.recipe.temperature)
  return list
})
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <!-- Header row: "← retour ... ♡ favori · ⋯" -->
    <div class="d-flex align-center ga-2 mb-3">
      <v-btn
        v-if="showBack"
        variant="text"
        size="small"
        prepend-icon="mdi-arrow-left"
        @click="emit('back')"
      >
        retour
      </v-btn>

      <v-spacer />

      <v-btn
        variant="text"
        size="small"
        :prepend-icon="recipe.favorite ? 'mdi-heart' : 'mdi-heart-outline'"
        :color="recipe.favorite ? 'error' : undefined"
        @click="emit('toggle-favorite', recipe)"
      >
        favori
      </v-btn>

      <v-menu>
        <template #activator="{ props: menuProps }">
          <v-btn
            v-bind="menuProps"
            icon="mdi-dots-horizontal"
            variant="text"
            size="small"
            aria-label="Plus d’actions"
          />
        </template>
        <v-list density="compact">
          <v-list-item
            prepend-icon="mdi-pencil-outline"
            title="Modifier"
            @click="emit('edit', recipe)"
          />
          <v-list-item
            prepend-icon="mdi-delete-outline"
            title="Supprimer"
            base-color="error"
            @click="emit('delete', recipe)"
          />
        </v-list>
      </v-menu>
    </div>

    <div class="em-scroll flex-grow-1 pe-1">
      <!-- Only shown once the AI has generated a real photo — the small
           placeholder blur used on cards would look like a mistake this big. -->
      <v-img
        v-if="recipe.image_url"
        :src="recipe.image_url"
        height="200"
        cover
        rounded="lg"
        class="em-outline mb-4"
      />

      <h2 class="text-h6 font-weight-medium mb-3">{{ recipe.name }}</h2>

      <div class="d-flex flex-wrap ga-2 mb-5">
        <v-chip v-for="chip in chips" :key="chip" size="small" variant="outlined">
          {{ chip }}
        </v-chip>
      </div>

      <!-- Ingredients, with the adjustable serving count from the mockup -->
      <div class="d-flex align-center ga-2 mb-2">
        <span class="text-subtitle-2 font-weight-medium">Ingrédients</span>
        <span class="text-caption em-muted">(pour</span>
        <v-btn
          icon="mdi-minus"
          size="x-small"
          variant="text"
          :disabled="servings <= 1"
          aria-label="Moins de portions"
          @click="servings = Math.max(1, servings - 1)"
        />
        <span class="text-caption em-mono" style="min-width: 1.5rem; text-align: center">
          {{ servings }}
        </span>
        <v-btn
          icon="mdi-plus"
          size="x-small"
          variant="text"
          :disabled="servings >= 50"
          aria-label="Plus de portions"
          @click="servings = Math.min(50, servings + 1)"
        />
        <span class="text-caption em-muted">— ajustable)</span>
        <v-btn
          v-if="isScaled"
          size="x-small"
          variant="text"
          class="em-muted"
          @click="servings = recipe.servings"
        >
          réinitialiser
        </v-btn>
      </div>

      <div v-if="recipe.ingredients?.length" class="mb-5">
        <div
          v-for="(ingredient, index) in recipe.ingredients"
          :key="`${ingredient.name}-${index}`"
          class="d-flex align-end text-body-2 mb-1"
        >
          <span>{{ ingredient.name }}</span>
          <span class="em-leader" />
          <span class="em-mono flex-shrink-0">
            <template v-if="ingredient.quantity !== null && ingredient.quantity !== undefined">
              {{ formatQuantity(ingredient.quantity) }}
            </template>
            {{ ingredient.unit }}
          </span>
          <span v-if="ingredient.aisle" class="text-caption em-muted ms-2 flex-shrink-0">
            · {{ ingredient.aisle }}
          </span>
        </div>
      </div>
      <p v-else class="text-body-2 em-muted mb-5">Aucun ingrédient renseigné.</p>

      <div v-if="recipe.steps?.length" class="mb-5">
        <div class="text-subtitle-2 font-weight-medium mb-2">Étapes</div>
        <div
          v-for="(step, index) in recipe.steps"
          :key="index"
          class="d-flex ga-3 text-body-2 mb-2"
        >
          <span class="em-muted em-mono">{{ index + 1 }}</span>
          <span>{{ step }}</span>
        </div>
      </div>

      <div class="mb-4">
        <div class="text-subtitle-2 font-weight-medium mb-2">Notes</div>
        <v-sheet
          class="em-outline pa-3 text-body-2"
          rounded="lg"
          :class="recipe.notes ? '' : 'em-muted'"
          min-height="72"
        >
          {{ recipe.notes || 'Aucune note.' }}
        </v-sheet>
      </div>
    </div>

    <!-- Planner / grocery list are out of scope for the POC.
         No `block` here: it forces width 100% on each button, so side by side
         they overflow and the second one is pushed off screen. -->
    <div class="d-flex ga-3 pt-3">
      <v-btn
        class="flex-grow-1"
        style="min-width: 0"
        @click="emit('not-implemented', 'La liste de courses arrive bientôt')"
      >
        + Liste de courses
      </v-btn>
      <v-btn
        class="flex-grow-1"
        style="min-width: 0; border-style: dashed"
        @click="emit('not-implemented', 'Le planificateur arrive bientôt')"
      >
        + Planning
      </v-btn>
    </div>
  </div>
</template>
