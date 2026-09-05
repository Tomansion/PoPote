<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDisplay } from 'vuetify'

import IntroSplash from '@/components/IntroSplash.vue'
import ProfileAvatarButton from '@/components/ProfileAvatarButton.vue'
import ProfilePanel from '@/components/ProfilePanel.vue'
import RecipeFilters from '@/components/RecipeFilters.vue'
import { useAuthStore } from '@/stores/auth'
import { useEventsStore } from '@/stores/events'
import { useRecipesStore } from '@/stores/recipes'

const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()

const store = useRecipesStore()
const auth = useAuthStore()
const events = useEventsStore()
const { search, toast } = storeToRefs(store)
const { toast: eventToast } = storeToRefs(events)

const snackbar = ref(false)
const activeToast = ref(null)
const profileOpen = ref(false)

// Both stores raise toasts; whichever fires last wins the one snackbar.
watch([toast, eventToast], () => {
  const latest = [toast.value, eventToast.value]
    .filter(Boolean)
    .sort((a, b) => b.at - a.at)[0]
  if (latest && latest !== activeToast.value) {
    activeToast.value = latest
    snackbar.value = true
  }
})

/** The login screen renders on its own, with no nav, bars or drawer. */
const isBare = computed(() => Boolean(route.meta.bare))

const NAV_ITEMS = [
  { key: 'recipes', title: 'Recettes', to: '/', icon: 'mdi-notebook-outline' },
  { key: 'planner', title: 'Planificateur', to: '/planner', icon: 'mdi-calendar-month-outline' },
  { key: 'groceries', title: 'Liste de courses', to: '/groceries', icon: 'mdi-cart-outline' },
]

const activeNav = computed(() => route.meta.nav ?? 'recipes')

// The mobile detail screen supplies its own "← retour" header, so the global
// app bar would be a duplicate there.
const showMobileAppBar = computed(() => !mdAndUp.value && !route.meta.detail)

const isRecipesSection = computed(() => activeNav.value === 'recipes')

// Plays once per app start, on the web and in the APK alike. Skipped outright
// for anyone who asked the system for less motion.
const showIntro = ref(!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)

// The store loads behind the intro, so the recipes are already there when it
// fades out. Nothing is loaded until there is a session to load it for: the
// feed needs a token, and the recipes it returns are this user's.
onMounted(async () => {
  await auth.restore()
  if (auth.isAuthenticated) store.init()
})

// Signing in starts the feed; signing out tears it down and empties the stores,
// so no trace of the previous account is left on screen.
watch(
  () => auth.isAuthenticated,
  (signedIn, wasSignedIn) => {
    if (signedIn && !wasSignedIn) store.init()
    else if (!signedIn && wasSignedIn) store.reset()
  },
)

onBeforeUnmount(() => store.stop())
</script>

<template>
  <IntroSplash v-if="showIntro" @done="showIntro = false" />

  <v-app>
    <!-- The login screen gets the bare app shell: no nav, no bars. -->
    <v-main v-if="isBare">
      <router-view />
    </v-main>

    <template v-else>
    <!-- The panel lives at the top level of the shell, not nested inside the
         app bar or the permanent drawer below — both apply their own CSS
         transform, which would break this drawer's full-screen overlay. -->
    <ProfilePanel v-model="profileOpen" />

    <!-- ============ Desktop: permanent drawer with nav + filters ============ -->
    <v-navigation-drawer
      v-if="mdAndUp"
      permanent
      width="240"
      color="background"
      border="0"
      class="em-outline"
    >
      <div class="pa-4">
        <div class="d-flex align-center ga-3 mb-6">
          <ProfileAvatarButton :size="36" @click="profileOpen = true" />
          <div class="text-subtitle-1 font-weight-medium">Po'Pote</div>
        </div>

        <v-list density="compact" nav class="pa-0">
          <v-list-item
            v-for="item in NAV_ITEMS"
            :key="item.key"
            :title="item.title"
            :active="activeNav === item.key"
            rounded="lg"
            @click="router.push(item.to)"
          />
        </v-list>

        <template v-if="isRecipesSection">
          <div class="text-caption em-muted mt-8 mb-3 ps-1">FILTRES</div>
          <RecipeFilters layout="panel" />
        </template>
      </div>

      <template #append>
        <div class="pa-4">
          <v-btn
            v-if="isRecipesSection"
            block
            size="large"
            class="mb-3"
            @click="store.openCreateForm()"
          >
            + Nouvelle recette
          </v-btn>
        </div>
      </template>
    </v-navigation-drawer>

    <!-- ============ Desktop top bar: search ============ -->
    <v-app-bar v-if="mdAndUp" flat height="64" color="background">
      <div class="d-flex align-center ga-4 px-4 fill-height" style="width: 100%">
        <v-text-field
          v-model="search"
          placeholder="Rechercher"
          prepend-inner-icon="mdi-magnify"
          rounded="pill"
          clearable
          hide-details
          style="max-width: 520px"
        />
      </div>
    </v-app-bar>

    <!-- ============ Mobile top bar: avatar on the left, centred title ============ -->
    <v-app-bar v-else-if="showMobileAppBar" flat color="background">
      <template #prepend>
        <div class="ps-2">
          <ProfileAvatarButton :size="32" @click="profileOpen = true" />
        </div>
      </template>
      <v-app-bar-title class="text-center text-subtitle-1">
        {{ route.meta.title }}
      </v-app-bar-title>
    </v-app-bar>

    <v-main>
      <router-view />
    </v-main>

    <!-- ============ Mobile bottom navigation ============ -->
    <v-bottom-navigation
      v-if="!mdAndUp"
      :model-value="activeNav"
      color="primary"
      grow
      height="56"
      class="em-outline"
    >
      <v-btn
        v-for="item in NAV_ITEMS"
        :key="item.key"
        :value="item.key"
        variant="text"
        @click="router.push(item.to)"
      >
        <v-icon :icon="item.icon" size="20" />
        <span class="text-caption">{{ item.title }}</span>
      </v-btn>
    </v-bottom-navigation>

    <v-snackbar
      v-model="snackbar"
      :color="activeToast?.color ?? 'error'"
      timeout="3500"
      location="bottom"
    >
      {{ activeToast?.message }}
    </v-snackbar>
    </template>
  </v-app>
</template>
