<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDisplay } from 'vuetify'

import RecipeCard from '@/components/RecipeCard.vue'
import RecipeDetail from '@/components/RecipeDetail.vue'
import RecipeFilters from '@/components/RecipeFilters.vue'
import RecipeFormDialog from '@/components/RecipeFormDialog.vue'
import { useRecipesStore } from '@/stores/recipes'

const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()

const store = useRecipesStore()
const { search, filteredRecipes, loading, recipes, formOpen, editingRecipe } =
  storeToRefs(store)

const pendingDelete = ref(null)

const selectedId = computed(() => route.params.id ?? null)
const selected = computed(() => (selectedId.value ? store.byId(selectedId.value) : null))

// Mobile shows either the list or the detail; desktop shows both side by side.
const showDetailPage = computed(() => !mdAndUp.value && Boolean(selectedId.value))

function open(recipe) {
  router.push({ name: 'recipe', params: { id: recipe.id } })
}

function back() {
  router.push({ name: 'recipes' })
}

const startCreate = () => store.openCreateForm()
const startEdit = (recipe) => store.openEditForm(recipe)

async function handleSubmit(payload) {
  if (editingRecipe.value) {
    await store.updateRecipe(editingRecipe.value.id, payload)
  } else {
    const created = await store.createRecipe(payload)
    if (mdAndUp.value && created) open(created)
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
  <!-- ---------------- Mobile: recipe detail as a full page ---------------- -->
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

  <!-- ---------------- Desktop: grid + detail panel ---------------- -->
  <div v-else-if="mdAndUp" class="d-flex fill-height">
    <div class="flex-grow-1 pa-6 em-scroll">
      <div class="d-flex align-center ga-3 mb-4">
        <h2 class="text-subtitle-1 font-weight-medium">Mes recettes</h2>
        <span class="text-body-2 em-muted em-mono">{{ recipes.length }}</span>
        <v-spacer />
        <span class="text-caption em-muted">
          {{ filteredRecipes.length }} affichée{{ filteredRecipes.length > 1 ? 's' : '' }}
        </span>
      </div>

      <v-progress-linear v-if="loading" indeterminate class="mb-4" />

      <div v-if="filteredRecipes.length" class="em-grid">
        <RecipeCard
          v-for="recipe in filteredRecipes"
          :key="recipe.id"
          :recipe="recipe"
          variant="grid"
          :selected="recipe.id === selectedId"
          @select="open"
          @dblclick="startEdit(recipe)"
          @toggle-favorite="store.toggleFavorite($event)"
        />
      </div>

      <div v-else-if="!loading" class="text-center em-muted py-12">
        <v-icon icon="mdi-silverware-variant" size="40" class="mb-3" />
        <p class="text-body-2">
          {{ recipes.length ? 'Aucune recette ne correspond aux filtres.' : 'Aucune recette pour le moment.' }}
        </p>
      </div>

      <p class="text-caption text-info mt-4">
        clic = aperçu à droite · double-clic = édition
      </p>
    </div>

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
  </div>

  <!-- ---------------- Mobile: list ---------------- -->
  <div v-else class="em-page d-flex flex-column fill-height pa-4">
    <v-text-field
      v-model="search"
      placeholder="Rechercher une recette"
      prepend-inner-icon="mdi-magnify"
      clearable
      rounded="pill"
      class="mb-3"
    />

    <RecipeFilters layout="bar" class="mb-3" />

    <v-progress-linear v-if="loading" indeterminate class="mb-3" />

    <div class="flex-grow-1 em-scroll">
      <div class="d-flex flex-column ga-3">
        <RecipeCard
          v-for="recipe in filteredRecipes"
          :key="recipe.id"
          :recipe="recipe"
          variant="list"
          @select="open"
          @toggle-favorite="store.toggleFavorite($event)"
        />
      </div>

      <div v-if="!filteredRecipes.length && !loading" class="text-center em-muted py-10">
        <v-icon icon="mdi-silverware-variant" size="40" class="mb-3" />
        <p class="text-body-2">
          {{ recipes.length ? 'Aucune recette ne correspond aux filtres.' : 'Aucune recette pour le moment.' }}
        </p>
      </div>
    </div>

    <v-btn block size="large" class="mt-3" @click="startCreate">+ Nouvelle recette</v-btn>
  </div>

  <!-- Floating create button on desktop lives in the drawer; see App.vue -->
  <RecipeFormDialog
    v-model="formOpen"
    :recipe="editingRecipe"
    :fullscreen="!mdAndUp"
    :on-submit="handleSubmit"
  />

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
.em-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}
</style>
