<script setup>
import { computed } from 'vue'

const props = defineProps({
  recipe: { type: Object, required: true },
  selected: { type: Boolean, default: false },
})

defineEmits(['select', 'toggle-favorite'])

const totalMinutes = computed(
  () => (props.recipe.prep_minutes || 0) + (props.recipe.cook_minutes || 0),
)

const durationLabel = computed(() =>
  totalMinutes.value ? `${totalMinutes.value} min` : null,
)

// Real picture once the AI has generated one; until then, a placeholder
// that is at least stable per recipe, so the card doesn't reshuffle its
// picture on every render.
const imageUrl = computed(
  () => props.recipe.image_url || `https://picsum.photos/seed/${props.recipe.id}/20/10?blur=10`,
)
</script>

<template>
  <v-card
    :class="['em-outline pp-card', selected ? 'em-selected' : '']"
    flat
    @click="$emit('select', recipe)"
  >
    <div class="pp-card-image">
      <v-img :src="imageUrl" height="84" cover />
      <v-btn
        :icon="recipe.favorite ? 'mdi-heart' : 'mdi-heart-outline'"
        :color="recipe.favorite ? 'error' : 'white'"
        variant="text"
        size="small"
        density="comfortable"
        class="pp-card-favorite"
        :aria-label="recipe.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
        @click.stop="$emit('toggle-favorite', recipe)"
      />
    </div>

    <div class="pp-card-body">
      <div class="text-body-2 font-weight-medium text-truncate">
        {{ recipe.name }}
      </div>

      <div class="text-caption em-muted text-truncate">
        {{ recipe.type }}<template v-if="durationLabel"> · {{ durationLabel }}</template>
      </div>
    </div>
  </v-card>
</template>

<style scoped>
/* Fixed size so every card lines up regardless of name length or how many
   details it has — a mix of short and long recipe names otherwise produces
   ragged rows of unequal height. */
.pp-card {
  width: 184px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.pp-card-image {
  position: relative;
}

.pp-card-favorite {
  position: absolute;
  top: 4px;
  right: 4px;
  /* A plain white icon can vanish against a light patch of the photo — the
     shadow keeps its outline (and the filled red heart) readable anywhere. */
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.7));
}

.pp-card-body {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
  height: 68px;
  padding: 8px;
}
</style>
