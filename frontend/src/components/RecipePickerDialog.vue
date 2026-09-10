<script setup>
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useDisplay } from 'vuetify'

import RecipeFormDialog from '@/components/RecipeFormDialog.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import { usePlanStore } from '@/stores/plan'
import { useRecipesStore } from '@/stores/recipes'
import { placeholderGradient } from '@/utils/gradient'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  eventId: { type: String, required: true },
  /** The event's members, to name and picture whose recipe each one is. */
  members: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'pick'])

const auth = useAuthStore()
const plan = usePlanStore()
const recipesStore = useRecipesStore()
const { eventRecipes } = storeToRefs(plan)
const { mdAndUp } = useDisplay()

const tab = ref('mine')
const search = ref('')
const creating = ref(false)

const all = computed(() => eventRecipes.value[props.eventId] ?? [])
const mine = computed(() => all.value.filter((r) => r.owner_id === auth.user?.id))
const others = computed(() => all.value.filter((r) => r.owner_id !== auth.user?.id))

const memberName = (id) =>
  props.members.find((m) => m.id === id)?.display_name ?? 'Un membre'
const memberSeed = (id) => props.members.find((m) => m.id === id)?.avatar_seed ?? 0

function matches(recipe, term) {
  const haystack = [recipe.name, recipe.type, recipe.category, memberName(recipe.owner_id)]
    .join(' ')
    .toLowerCase()
  return haystack.includes(term)
}

/**
 * Search runs across everyone's recipes at once, but keeps the two halves
 * apart in the results: "who wrote this" is the first thing you want to know
 * about a dish you are about to sign up to cook.
 */
const results = computed(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return null
  return {
    mine: mine.value.filter((r) => matches(r, term)),
    others: others.value.filter((r) => matches(r, term)),
  }
})

/**
 * What to render, as titled sections.
 *
 * One shape for both modes — browsing a tab and searching everything — so the
 * row markup exists once instead of once per case. A section with no title is
 * a plain tab listing; searching produces two titled ones.
 */
const sections = computed(() => {
  if (results.value) {
    return [
      { key: 'mine', title: 'Mes recettes', recipes: results.value.mine, showOwner: false },
      {
        key: 'others',
        title: 'Recettes du groupe',
        recipes: results.value.others,
        showOwner: true,
      },
    ].filter((section) => section.recipes.length)
  }

  return [
    {
      key: tab.value,
      title: '',
      recipes: tab.value === 'mine' ? mine.value : others.value,
      showOwner: tab.value === 'others',
    },
  ]
})

const isEmpty = computed(() => sections.value.every((section) => !section.recipes.length))

const emptyMessage = computed(() => {
  if (results.value) return 'Aucune recette ne correspond.'
  return tab.value === 'mine'
    ? 'Vous n’avez pas encore de recette.'
    : 'Les autres membres n’ont pas encore partagé de recette.'
})

// Reopening the picker should not resume the previous search.
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      search.value = ''
      tab.value = 'mine'
    }
  },
)

function pick(recipe) {
  emit('pick', recipe)
}

/**
 * The "add a recipe" shortcut.
 *
 * It writes to your own recipe book like any other creation, and then plans
 * what it just created — which is the reason you were in this dialog.
 */
async function createAndPick(payload, photo) {
  const created = await recipesStore.createRecipe(payload)
  if (!created) return
  if (photo?.file) {
    try {
      await recipesStore.uploadPhoto(created.id, photo.file)
    } catch {
      // Already reported; the recipe itself is fine.
    }
  }
  // Keep the picker's own list in step without refetching the whole event.
  eventRecipes.value[props.eventId] = [...all.value, created]
  pick(created)
}

const thumb = (recipe) => recipe.image_thumb_url || recipe.image_url || ''
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
        <span class="text-subtitle-1 flex-grow-1 text-center">Ajouter une recette</span>
        <v-btn
          variant="text"
          size="small"
          icon="mdi-plus"
          aria-label="Créer une recette"
          @click="creating = true"
        />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <v-text-field
          v-model="search"
          placeholder="Chercher dans toutes les recettes du groupe"
          prepend-inner-icon="mdi-magnify"
          clearable
          rounded="pill"
          hide-details
          class="mb-3"
        />

        <!-- Searching spans everyone, so the tabs (which do not) would only
             contradict the results underneath. -->
        <v-tabs v-if="!results" v-model="tab" density="compact" class="mb-2">
          <v-tab value="mine">Mes recettes ({{ mine.length }})</v-tab>
          <v-tab value="others">Le groupe ({{ others.length }})</v-tab>
        </v-tabs>

        <div v-for="section in sections" :key="section.key" class="mb-2">
          <div v-if="section.title" class="text-caption em-muted mb-1">
            {{ section.title }}
          </div>

          <v-list class="pa-0 bg-transparent">
            <v-list-item
              v-for="recipe in section.recipes"
              :key="recipe.id"
              class="px-0"
              @click="pick(recipe)"
            >
              <template #prepend>
                <v-avatar rounded="lg" size="40" class="me-3">
                  <v-img v-if="thumb(recipe)" :src="thumb(recipe)" cover />
                  <!-- Same derived tint as the recipe's card, so a dish is
                       recognisable here before you have read its name. -->
                  <div
                    v-else
                    class="pp-swatch"
                    :style="{ background: placeholderGradient(recipe.id) }"
                  />
                </v-avatar>
              </template>
              <v-list-item-title class="text-body-2">{{ recipe.name }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption d-flex align-center ga-1">
                <template v-if="section.showOwner">
                  <UserAvatar :seed="memberSeed(recipe.owner_id)" :size="14" />
                  {{ memberName(recipe.owner_id) }} ·
                </template>
                {{ recipe.type }} · {{ recipe.servings }} pers
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </div>

        <p v-if="isEmpty" class="text-body-2 em-muted text-center py-8">
          {{ emptyMessage }}
        </p>

      </v-card-text>
    </v-card>
  </v-dialog>

  <!-- The shortcut: create a recipe and plan it in one go, without losing
       the slot you were filling in. -->
  <RecipeFormDialog
    v-model="creating"
    :recipe="null"
    :fullscreen="!mdAndUp"
    :on-submit="createAndPick"
  />
</template>

<style scoped>
.pp-swatch {
  width: 100%;
  height: 100%;
}
</style>
