<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'

import { api, ApiError } from '@/api/client'
import RecipeCard from '@/components/RecipeCard.vue'
import RecipeDetail from '@/components/RecipeDetail.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { answeredPrefs } from '@/utils/prefs'

const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()

const loading = ref(true)
const error = ref('')
const profile = ref(null)
/** The recipe being previewed, if any — their book is read-only from here. */
const previewing = ref(null)

const answers = computed(() => answeredPrefs(profile.value?.user?.prefs))
const recipes = computed(() => profile.value?.recipes ?? [])

async function load(id) {
  loading.value = true
  error.value = ''
  profile.value = null
  try {
    profile.value = await api.userProfile(id)
  } catch (err) {
    // 404 covers both "no such account" and "you don't share an event with
    // them" — the API does not distinguish, and neither should the message.
    error.value =
      err instanceof ApiError && err.status === 404
        ? 'Ce profil n’est pas accessible. Vous ne partagez aucun événement avec cette personne.'
        : 'Impossible de charger ce profil.'
  } finally {
    loading.value = false
  }
}

watch(() => route.params.id, (id) => id && load(id), { immediate: true })
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <div class="d-flex align-center ga-2 pa-4 pb-0">
      <v-btn variant="text" size="small" prepend-icon="mdi-arrow-left" @click="router.back()">
        retour
      </v-btn>
    </div>

    <div class="em-scroll flex-grow-1">
      <v-container class="pa-4" style="max-width: 720px">
        <v-skeleton-loader v-if="loading" type="article, actions" />

        <div v-else-if="error" class="text-center em-muted py-12">
          <v-icon icon="mdi-lock-outline" size="48" class="mb-4" />
          <p class="text-body-2">{{ error }}</p>
        </div>

        <template v-else-if="profile">
          <div class="text-center mb-8">
            <UserAvatar
              :seed="profile.user.avatar_seed"
              :size="88"
              class="em-outline mx-auto mb-3"
            />
            <h2 class="text-h6 font-weight-medium">{{ profile.user.display_name }}</h2>
          </div>

          <template v-if="answers.length">
            <SectionHeader icon="mdi-silverware-fork-knife" title="À table" />
            <v-list class="pa-0 bg-transparent mb-8">
              <v-list-item
                v-for="answer in answers"
                :key="answer.key"
                :prepend-icon="answer.icon"
                class="px-0"
              >
                <v-list-item-title class="text-body-2">{{ answer.answer }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  {{ answer.label }}
                </v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </template>

          <SectionHeader icon="mdi-notebook-outline" title="Ses recettes" />
          <div v-if="recipes.length" class="pp-card-grid">
            <RecipeCard
              v-for="recipe in recipes"
              :key="recipe.id"
              :recipe="recipe"
              @select="previewing = $event"
              @menu="previewing = $event.recipe"
            />
          </div>
          <p v-else class="text-body-2 em-muted">
            {{ profile.user.display_name }} n’a pas encore de recette à montrer.
          </p>
        </template>
      </v-container>
    </div>

    <!-- Read-only: someone else's recipe can be opened and scaled, never
         edited or deleted. -->
    <v-dialog
      :model-value="Boolean(previewing)"
      :fullscreen="!mdAndUp"
      :max-width="mdAndUp ? 640 : undefined"
      scrollable
      @update:model-value="previewing = null"
    >
      <v-card v-if="previewing" flat class="pa-4">
        <RecipeDetail
          :recipe="previewing"
          readonly
          show-back
          :owner-name="profile?.user?.display_name ?? ''"
          @back="previewing = null"
        />
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.pp-card-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
