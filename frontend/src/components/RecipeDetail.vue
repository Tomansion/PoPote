<script setup>
import { computed, ref, watch } from 'vue'

import SectionHeader from '@/components/SectionHeader.vue'
import { placeholderGradient } from '@/utils/gradient'

const props = defineProps({
  recipe: { type: Object, required: true },
  showBack: { type: Boolean, default: false },
  /** Someone else's recipe, seen from their member page: no editing. */
  readonly: { type: Boolean, default: false },
  /** Their display name, shown under the title when there is one. */
  ownerName: { type: String, default: '' },
})

const emit = defineEmits(['back', 'edit', 'delete', 'toggle-favorite'])

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

const gradient = computed(() => placeholderGradient(props.recipe.id))

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

      <template v-if="!readonly">
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
      </template>
    </div>

    <div class="em-scroll flex-grow-1 pe-1">
      <v-img
        v-if="recipe.image_url"
        :src="recipe.image_url"
        height="200"
        cover
        rounded="lg"
        class="em-outline mb-4"
      />
      <!-- No photo: the same derived tint the card shows, so the recipe keeps
           a consistent identity between the list and this page. -->
      <div
        v-else
        class="em-outline mb-4 pp-detail-placeholder"
        :style="{ background: gradient }"
      />

      <h2 class="text-h6 font-weight-medium mb-1">{{ recipe.name }}</h2>
      <p v-if="ownerName" class="text-caption em-muted mb-2">Recette de {{ ownerName }}</p>

      <div class="d-flex flex-wrap ga-2 mb-5 mt-3">
        <v-chip v-for="chip in chips" :key="chip" size="small" variant="outlined">
          {{ chip }}
        </v-chip>
      </div>

      <!-- The same section headings as the edit form, from one component:
           the two screens describe the same recipe and used to introduce its
           parts in visibly different ways. -->
      <SectionHeader icon="mdi-food-variant" title="Ingrédients">
        <template #action>
          <div class="d-flex align-center ga-1 flex-shrink-0">
            <span class="text-caption em-muted">pour</span>
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
            <v-btn
              v-if="isScaled"
              icon="mdi-restore"
              size="x-small"
              variant="text"
              aria-label="Revenir aux portions de la recette"
              @click="servings = recipe.servings"
            />
          </div>
        </template>
      </SectionHeader>

      <div v-if="recipe.ingredients?.length" class="mb-6">
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
      <p v-else class="text-body-2 em-muted mb-6">Aucun ingrédient renseigné.</p>

      <template v-if="recipe.steps?.length">
        <SectionHeader icon="mdi-format-list-numbered" title="Étapes" />
        <div class="mb-6">
          <div
            v-for="(step, index) in recipe.steps"
            :key="index"
            class="d-flex ga-3 text-body-2 mb-2"
          >
            <span class="em-muted em-mono">{{ index + 1 }}</span>
            <span>{{ step }}</span>
          </div>
        </div>
      </template>

      <SectionHeader icon="mdi-note-text" title="Notes" />
      <v-sheet
        class="em-outline pa-3 text-body-2 mb-4"
        rounded="lg"
        :class="recipe.notes ? '' : 'em-muted'"
        min-height="72"
      >
        {{ recipe.notes || 'Aucune note.' }}
      </v-sheet>
    </div>
  </div>
</template>

<style scoped>
.pp-detail-placeholder {
  height: 200px;
  border-radius: 8px;
}
</style>
