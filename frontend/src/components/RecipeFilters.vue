<script setup>
import { storeToRefs } from 'pinia'

import { RECIPE_TYPES, useRecipesStore } from '@/stores/recipes'

defineProps({
  // 'bar' = horizontal chip row (mobile), 'panel' = stacked list (desktop drawer)
  layout: { type: String, default: 'bar' },
})

const store = useRecipesStore()
const { filters, sortDesc, activeFilterCount } = storeToRefs(store)

const TIME_LIMIT = 30

function cycleTemperature() {
  filters.value.temperature =
    filters.value.temperature === null
      ? 'Chaud'
      : filters.value.temperature === 'Chaud'
        ? 'Froid'
        : null
}

function toggleTimeLimit() {
  filters.value.maxMinutes = filters.value.maxMinutes ? null : TIME_LIMIT
}
</script>

<template>
  <!-- Mobile: one scrollable row of chips under the search field -->
  <div v-if="layout === 'bar'" class="d-flex align-center ga-2 overflow-x-auto pb-1">
    <span class="text-caption em-muted flex-shrink-0">Filtres</span>

    <v-chip
      size="small"
      variant="outlined"
      :prepend-icon="sortDesc ? 'mdi-sort-alphabetical-descending' : 'mdi-sort-alphabetical-ascending'"
      @click="sortDesc = !sortDesc"
    >
      {{ sortDesc ? 'Z→A' : 'A→Z' }}
    </v-chip>

    <v-menu>
      <template #activator="{ props }">
        <v-chip
          v-bind="props"
          size="small"
          variant="outlined"
          :color="filters.type ? 'accent' : undefined"
        >
          {{ filters.type || 'Type' }}
        </v-chip>
      </template>
      <v-list density="compact">
        <v-list-item title="Tous" @click="filters.type = null" />
        <v-list-item
          v-for="type in RECIPE_TYPES"
          :key="type"
          :title="type"
          @click="filters.type = type"
        />
      </v-list>
    </v-menu>

    <v-chip
      size="small"
      variant="outlined"
      :color="filters.temperature ? 'accent' : undefined"
      @click="cycleTemperature"
    >
      {{ filters.temperature || 'Chaud/Froid' }}
    </v-chip>

    <v-chip
      size="small"
      variant="outlined"
      :color="filters.maxMinutes ? 'accent' : undefined"
      @click="toggleTimeLimit"
    >
      ≤ {{ TIME_LIMIT }} min
    </v-chip>

    <v-chip
      size="small"
      variant="outlined"
      :color="filters.favoritesOnly ? 'accent' : undefined"
      @click="filters.favoritesOnly = !filters.favoritesOnly"
    >
      Favoris
    </v-chip>

    <v-chip
      v-if="activeFilterCount"
      size="small"
      variant="text"
      prepend-icon="mdi-close"
      @click="store.resetFilters()"
    >
      Effacer
    </v-chip>
  </div>

  <!-- Desktop: stacked pills in the navigation drawer -->
  <div v-else class="d-flex flex-column ga-2">
    <v-btn
      size="small"
      block
      class="justify-start"
      :prepend-icon="sortDesc ? 'mdi-sort-alphabetical-descending' : 'mdi-sort-alphabetical-ascending'"
      @click="sortDesc = !sortDesc"
    >
      {{ sortDesc ? 'Z → A' : 'A → Z' }}
    </v-btn>

    <v-menu>
      <template #activator="{ props }">
        <v-btn
          v-bind="props"
          size="small"
          block
          class="justify-start"
          append-icon="mdi-menu-down"
          :color="filters.type ? 'accent' : undefined"
        >
          {{ filters.type || 'Type' }}
        </v-btn>
      </template>
      <v-list density="compact">
        <v-list-item title="Tous" @click="filters.type = null" />
        <v-list-item
          v-for="type in RECIPE_TYPES"
          :key="type"
          :title="type"
          @click="filters.type = type"
        />
      </v-list>
    </v-menu>

    <v-btn
      size="small"
      block
      class="justify-start"
      :color="filters.temperature ? 'accent' : undefined"
      @click="cycleTemperature"
    >
      {{ filters.temperature || 'Chaud / Froid' }}
    </v-btn>

    <v-btn
      size="small"
      block
      class="justify-start"
      :color="filters.maxMinutes ? 'accent' : undefined"
      @click="toggleTimeLimit"
    >
      Temps ≤ {{ TIME_LIMIT }} min
    </v-btn>

    <v-btn
      size="small"
      block
      class="justify-start"
      :color="filters.favoritesOnly ? 'accent' : undefined"
      @click="filters.favoritesOnly = !filters.favoritesOnly"
    >
      Favoris
    </v-btn>

    <v-btn
      v-if="activeFilterCount"
      size="small"
      block
      variant="text"
      class="justify-start em-muted"
      prepend-icon="mdi-close"
      @click="store.resetFilters()"
    >
      Effacer les filtres
    </v-btn>
  </div>
</template>
