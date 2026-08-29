<script setup>
import { computed } from 'vue'

const props = defineProps({
  recipe: { type: Object, required: true },
  variant: { type: String, default: 'list' }, // 'list' (mobile) | 'grid' (desktop)
  selected: { type: Boolean, default: false },
})

defineEmits(['select', 'toggle-favorite'])

const totalMinutes = computed(
  () => (props.recipe.prep_minutes || 0) + (props.recipe.cook_minutes || 0),
)

const durationLabel = computed(() =>
  totalMinutes.value ? `${totalMinutes.value} min` : null,
)

const ingredientCount = computed(() => props.recipe.ingredients?.length ?? 0)
</script>

<template>
  <v-card
    :class="['em-outline', selected ? 'em-selected' : '']"
    flat
    :height="variant === 'grid' ? 128 : undefined"
    @click="$emit('select', recipe)"
  >
    <div class="d-flex flex-column fill-height pa-3">
      <div class="d-flex align-start ga-2">
        <div class="text-body-2 font-weight-medium flex-grow-1 text-truncate">
          {{ recipe.name }}
        </div>
        <v-btn
          :icon="recipe.favorite ? 'mdi-heart' : 'mdi-heart-outline'"
          :color="recipe.favorite ? 'error' : 'secondary'"
          variant="text"
          size="x-small"
          density="comfortable"
          :aria-label="recipe.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
          @click.stop="$emit('toggle-favorite', recipe)"
        />
      </div>

      <div v-if="variant === 'grid'" class="flex-grow-1" />

      <div
        :class="[
          'd-flex align-center ga-2 text-caption em-muted',
          variant === 'grid' ? 'mt-2' : 'mt-2',
        ]"
      >
        <template v-if="variant === 'grid'">
          <span>{{ recipe.type }}</span>
          <span v-if="durationLabel">· {{ durationLabel }}</span>
          <span v-if="recipe.temperature === 'Froid'">· froid</span>
        </template>

        <template v-else>
          <v-chip size="x-small" variant="outlined" density="comfortable">
            {{ recipe.type }}
          </v-chip>
          <v-chip
            v-if="durationLabel"
            size="x-small"
            variant="outlined"
            density="comfortable"
          >
            {{ durationLabel }}
          </v-chip>
          <span v-if="ingredientCount" class="ms-auto">
            {{ ingredientCount }} ingr.
          </span>
        </template>
      </div>
    </div>
  </v-card>
</template>
