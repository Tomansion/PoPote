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

// ------------------------------------------------------- context menu
//
// One menu for the whole list rather than one per card: a category screen is
// dozens of cards, and each would otherwise carry its own (mounted, hidden)
// overlay. The cards report where they were pressed; this owns the menu.

const menuOpen = ref(false)
const menuTarget = ref([0, 0])
const menuRecipe = ref(null)

function openMenu({ recipe, x, y }) {
  menuRecipe.value = recipe
  menuTarget.value = [x, y]
  // Re-anchoring an already-open menu leaves it at the old position, so close
  // first and let the next tick reopen it where the second click landed.
  menuOpen.value = false
  requestAnimationFrame(() => {
    menuOpen.value = true
  })
}

async function duplicate(recipe) {
  const copy = await store.duplicateRecipe(recipe)
  if (copy && mdAndUp.value) open(copy)
}

/**
 * Apply whatever the form said to do with the photo.
 *
 * Deliberately not allowed to fail the save: by the time this runs the recipe
 * itself is stored, and losing the picture is worth a toast, not a dialog the
 * user cannot get out of.
 */
async function applyPhoto(recipeId, photo) {
  if (!photo) return
  try {
    if (photo.file) await store.uploadPhoto(recipeId, photo.file)
    else if (photo.remove) await store.removePhoto(recipeId)
  } catch {
    // The store has already raised the toast.
  }
}

async function handleSubmit(payload, photo) {
  if (editingRecipe.value) {
    const { id } = editingRecipe.value
    await store.updateRecipe(id, payload)
    await applyPhoto(id, photo)
    return
  }

  const created = await store.createRecipe(payload)
  if (created) {
    await applyPhoto(created.id, photo)
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
          @click="store.openCreateForm()"
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
          @click="store.openCreateForm()"
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
                @menu="openMenu"
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
        clic = aperçu à droite · double-clic = édition · clic droit = menu
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
        />
        <div v-else class="text-center em-muted pt-12">
          <v-icon icon="mdi-book-open-page-variant-outline" size="40" class="mb-3" />
          <p class="text-body-2">Sélectionnez une recette pour l’afficher ici.</p>
        </div>
      </div>
    </template>
  </div>

  <!-- ------------- Right-click / long-press on a card ------------- -->
  <v-menu v-model="menuOpen" :target="menuTarget" location="bottom start">
    <v-list v-if="menuRecipe" density="compact" min-width="200">
      <v-list-item
        prepend-icon="mdi-book-open-page-variant-outline"
        title="Ouvrir"
        @click="open(menuRecipe)"
      />
      <v-list-item
        prepend-icon="mdi-pencil-outline"
        title="Modifier"
        @click="startEdit(menuRecipe)"
      />
      <v-list-item
        :prepend-icon="menuRecipe.favorite ? 'mdi-heart-off-outline' : 'mdi-heart-outline'"
        :title="menuRecipe.favorite ? 'Retirer des favoris' : 'Ajouter aux favoris'"
        @click="store.toggleFavorite(menuRecipe)"
      />
      <v-list-item
        prepend-icon="mdi-content-copy"
        title="Dupliquer"
        @click="duplicate(menuRecipe)"
      />
      <v-divider class="my-1" />
      <v-list-item
        prepend-icon="mdi-delete-outline"
        title="Supprimer"
        base-color="error"
        @click="pendingDelete = menuRecipe"
      />
    </v-list>
  </v-menu>

  <RecipeFormDialog
    v-model="formOpen"
    :recipe="editingRecipe"
    :fullscreen="!mdAndUp"
    :on-submit="handleSubmit"
  />

  <v-dialog
    :model-value="Boolean(pendingDelete)"
    max-width="420"
    @update:model-value="pendingDelete = null"
  >
    <v-card flat class="pa-2">
      <v-card-title class="text-subtitle-1">Supprimer la recette ?</v-card-title>
      <v-card-text class="text-body-2">
        « {{ pendingDelete?.name }} » sera supprimée définitivement.
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
