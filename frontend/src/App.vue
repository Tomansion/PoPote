<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useDisplay } from 'vuetify'

import RecipeFilters from '@/components/RecipeFilters.vue'
import SyncStatus from '@/components/SyncStatus.vue'
import { useRecipesStore } from '@/stores/recipes'

const route = useRoute()
const router = useRouter()
const { mdAndUp } = useDisplay()

const store = useRecipesStore()
const { search, toast } = storeToRefs(store)

const snackbar = ref(false)

watch(toast, (value) => {
  if (value) snackbar.value = true
})

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

onMounted(() => store.init())
onBeforeUnmount(() => store.stop())
</script>

<template>
  <v-app>
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
        <div class="text-subtitle-1 font-weight-medium mb-6">Po'Pote</div>

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
          <v-btn block size="large" @click="store.openCreateForm()">
            + Nouvelle recette
          </v-btn>
        </div>
      </template>
    </v-navigation-drawer>

    <!-- ============ Desktop top bar: search + sync ============ -->
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
        <v-spacer />
        <SyncStatus compact />
      </div>
    </v-app-bar>

    <!-- ============ Mobile top bar: centred title ============ -->
    <v-app-bar v-else-if="showMobileAppBar" flat color="background">
      <template #prepend>
        <v-avatar size="32" class="em-outline" />
      </template>
      <v-app-bar-title class="text-center text-subtitle-1">
        {{ route.meta.title }}
      </v-app-bar-title>
      <template #append>
        <v-avatar size="32" class="em-outline" />
      </template>
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
      :color="toast?.color ?? 'error'"
      timeout="3500"
      location="bottom"
    >
      {{ toast?.message }}
    </v-snackbar>
  </v-app>
</template>
