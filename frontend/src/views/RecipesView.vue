<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDisplay } from 'vuetify'

import { api, ApiError } from '@/api/client'
import RecipeCard from '@/components/RecipeCard.vue'
import RecipeDetail from '@/components/RecipeDetail.vue'
import RecipeFilters from '@/components/RecipeFilters.vue'
import RecipeFormDialog from '@/components/RecipeFormDialog.vue'
import { useRecipesStore } from '@/stores/recipes'

const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()

const store = useRecipesStore()
const { search, filteredRecipes, recipesByCategory, loading, recipes, formOpen, editingRecipe } =
  storeToRefs(store)

const pendingDelete = ref(null)

const selectedId = computed(() => route.params.id ?? null)
const selected = computed(() => (selectedId.value ? store.byId(selectedId.value) : null))

// Mobile shows either the list or the detail, full page. Desktop shows both
// side by side, so selecting a recipe there never navigates away from the
// (still category-grouped) list.
const showDetailPage = computed(() => !mdAndUp.value && Boolean(selectedId.value))

function open(recipe) {
  router.push({ name: 'recipe', params: { id: recipe.id } })
}

function back() {
  router.push({ name: 'recipes' })
}

const startEdit = (recipe) => store.openEditForm(recipe)

// "+ Nouvelle recette" asks first whether to start from an AI-written draft.
// The draft is passed to the same form as `editingRecipe` would be, but
// stays null there — so submitting still creates a new recipe, not an edit.
const aiChoiceOpen = ref(false)
const aiPromptOpen = ref(false)
const aiPrompt = ref('')
const aiBusy = ref(false)
const aiDraft = ref(null)
const aiError = ref('')
// Matches the backend's RecipePrompt.prompt max_length — kept in sync by
// hand since there's no shared schema between the two apps.
const AI_PROMPT_MAX_LENGTH = 2000

function startCreate() {
  aiChoiceOpen.value = true
}

function startBlankCreate() {
  aiChoiceOpen.value = false
  aiDraft.value = null
  store.openCreateForm()
}

function startAICreate() {
  aiChoiceOpen.value = false
  aiPrompt.value = ''
  aiError.value = ''
  aiPromptOpen.value = true
}

async function submitAIPrompt() {
  const prompt = aiPrompt.value.trim()
  if (!prompt || aiBusy.value) return

  aiBusy.value = true
  aiError.value = ''
  try {
    aiDraft.value = await api.generateRecipe(prompt)
    aiPromptOpen.value = false
    store.openCreateForm()
  } catch (error) {
    // Shown right in the dialog rather than as a toast elsewhere on screen —
    // the prompt that caused it is still right there to fix and retry.
    aiError.value =
      error instanceof ApiError ? error.message : 'La génération a échoué, réessayez'
  } finally {
    aiBusy.value = false
  }
}

// Closing the form for any reason (cancel, or after a successful save) drops
// the draft, so it can't resurface on the next "+ Nouvelle recette".
watch(formOpen, (open) => {
  if (!open) aiDraft.value = null
})

async function handleSubmit(payload) {
  if (editingRecipe.value) {
    await store.updateRecipe(editingRecipe.value.id, payload)
    return
  }

  const created = await store.createRecipe(payload)
  if (created) {
    // Best-effort and fire-and-forget: the recipe already exists either way,
    // and a `recipe.updated` event will fill in the picture once it's ready.
    api.generateRecipeImage(created.id).catch((error) => {
      console.warn('Image generation skipped:', error)
    })
    // On desktop the new recipe shows up right away in its preview panel;
    // on mobile that panel doesn't exist, so there is nothing to select.
    if (mdAndUp.value) open(created)
  }
}

async function confirmDelete() {
  const recipe = pendingDelete.value
  pendingDelete.value = null
  if (!recipe) return

  await store.deleteRecipe(recipe.id)
  if (selectedId.value === recipe.id) back()
}

function notImplemented(message) {
  store.toast = { message, color: 'info', at: Date.now() }
}
</script>

<template>
  <!-- ---------------- Recipe detail, as a full page ---------------- -->
  <div v-if="showDetailPage" class="pa-4 fill-height">
    <RecipeDetail
      v-if="selected"
      :recipe="selected"
      show-back
      @back="back"
      @edit="startEdit"
      @delete="pendingDelete = $event"
      @toggle-favorite="store.toggleFavorite($event)"
      @not-implemented="notImplemented"
    />
    <div v-else class="text-center em-muted pt-8">
      <p class="mb-4">Recette introuvable.</p>
      <v-btn size="small" @click="back">Retour aux recettes</v-btn>
    </div>
  </div>

  <!-- ---------------- Recipe list: grouped by category ---------------- -->
  <div v-else class="d-flex fill-height">
    <div class="em-page d-flex flex-column flex-grow-1 pa-4" style="min-width: 0">
      <div class="d-flex align-center ga-2 mb-3">
        <v-text-field
          v-model="search"
          placeholder="Rechercher une recette"
          prepend-inner-icon="mdi-magnify"
          clearable
          rounded="pill"
          hide-details
          class="flex-grow-1"
        />
        <v-btn
          v-if="mdAndUp"
          prepend-icon="mdi-plus"
          color="primary"
          variant="flat"
          rounded="pill"
          size="large"
          @click="startCreate"
          >
          Nouvelle recette
        </v-btn>
        <v-btn
        v-else
        icon="mdi-plus"
          color="primary"
          variant="flat"
          rounded="circle"
          aria-label="Nouvelle recette"
          @click="startCreate"
        />
      </div>

      <RecipeFilters layout="bar" class="mb-3" />

      <v-progress-linear v-if="loading" indeterminate class="mb-3" />

      <div class="flex-grow-1 em-scroll">
        <div v-if="filteredRecipes.length" class="d-flex flex-column ga-5">
          <section v-for="group in recipesByCategory" :key="group.category">
            <h3 class="text-subtitle-2 font-weight-medium mb-2">{{ group.category }}</h3>

            <div class="pp-card-grid">
              <RecipeCard
                v-for="recipe in group.recipes"
                :key="recipe.id"
                :recipe="recipe"
                :selected="recipe.id === selectedId"
                @select="open"
                @dblclick="startEdit(recipe)"
                @toggle-favorite="store.toggleFavorite($event)"
              />
            </div>
          </section>
        </div>

        <div v-else-if="!loading" class="text-center em-muted py-10">
          <v-icon icon="mdi-silverware-variant" size="40" class="mb-3" />
          <p class="text-body-2">
            {{ recipes.length ? 'Aucune recette ne correspond aux filtres.' : 'Aucune recette pour le moment.' }}
          </p>
        </div>
      </div>

      <p v-if="mdAndUp" class="text-caption text-info mt-3">
        clic = aperçu à droite · double-clic = édition
      </p>
    </div>

    <template v-if="mdAndUp">
      <v-divider vertical />

      <div class="pa-6 em-scroll" style="width: 400px; flex: 0 0 400px">
        <RecipeDetail
          v-if="selected"
          :recipe="selected"
          @edit="startEdit"
          @delete="pendingDelete = $event"
          @toggle-favorite="store.toggleFavorite($event)"
          @not-implemented="notImplemented"
        />
        <div v-else class="text-center em-muted pt-12">
          <v-icon icon="mdi-book-open-page-variant-outline" size="40" class="mb-3" />
          <p class="text-body-2">Sélectionnez une recette pour l’afficher ici.</p>
        </div>
      </div>
    </template>
  </div>

  <RecipeFormDialog
    v-model="formOpen"
    :recipe="editingRecipe || aiDraft"
    :fullscreen="!mdAndUp"
    :on-submit="handleSubmit"
  />

  <!-- ---------------- "+ Nouvelle recette": AI or blank? ---------------- -->
  <v-dialog v-model="aiChoiceOpen" max-width="420">
    <v-card flat class="pa-2">
      <v-card-title class="text-subtitle-1">Nouvelle recette</v-card-title>
      <v-card-text class="text-body-2">
        Générer une recette avec l'IA à partir d'une simple description, ou
        partir d'un formulaire vide ?
      </v-card-text>
      <v-card-actions class="flex-wrap">
        <v-spacer />
        <v-btn variant="text" size="small" @click="startBlankCreate">
          Formulaire vide
        </v-btn>
        <v-btn color="primary" variant="flat" size="small" @click="startAICreate">
          Générer avec l'IA
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog v-model="aiPromptOpen" max-width="480" persistent>
    <v-card flat class="pa-2">
      <v-card-title class="text-subtitle-1">Décrivez la recette</v-card-title>
      <v-card-text>
        <v-textarea
          v-model="aiPrompt"
          placeholder="Ex. Un curry de légumes d'automne, épicé, prêt en 30 min"
          rows="3"
          autofocus
          :maxlength="AI_PROMPT_MAX_LENGTH"
          counter
          hide-details="auto"
          @keydown.enter.ctrl="submitAIPrompt"
          @update:model-value="aiError = ''"
        />
        <v-alert v-if="aiError" type="error" variant="tonal" density="compact" class="mt-3">
          {{ aiError }}
        </v-alert>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" size="small" :disabled="aiBusy" @click="aiPromptOpen = false">
          Annuler
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          size="small"
          :loading="aiBusy"
          :disabled="!aiPrompt.trim()"
          @click="submitAIPrompt"
        >
          Générer
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-dialog :model-value="Boolean(pendingDelete)" max-width="420" @update:model-value="pendingDelete = null">
    <v-card flat class="pa-2">
      <v-card-title class="text-subtitle-1">Supprimer la recette ?</v-card-title>
      <v-card-text class="text-body-2">
        « {{ pendingDelete?.name }} » sera supprimée pour tout le monde.
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" size="small" @click="pendingDelete = null">Annuler</v-btn>
        <v-btn color="error" size="small" @click="confirmDelete">Supprimer</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.pp-card-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
