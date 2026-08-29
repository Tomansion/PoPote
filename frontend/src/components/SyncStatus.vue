<script setup>
import { computed } from 'vue'
import { storeToRefs } from 'pinia'

import { useRecipesStore } from '@/stores/recipes'

const props = defineProps({
  compact: { type: Boolean, default: false },
})

const store = useRecipesStore()
const { connection, lastSync, servedFromCache } = storeToRefs(store)

const syncedAt = computed(() => {
  if (!lastSync.value) return null
  return new Date(lastSync.value).toLocaleTimeString('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
  })
})

const state = computed(() => {
  if (connection.value === 'live') {
    return { icon: 'mdi-circle-small', color: 'success', label: 'sync' }
  }
  if (connection.value === 'connecting') {
    return { icon: 'mdi-sync', color: 'secondary', label: 'connexion…' }
  }
  return { icon: 'mdi-cloud-off-outline', color: 'secondary', label: 'hors ligne' }
})

// The mockup's "dispo hors-ligne · dernière sync 12:04" line.
const fullLabel = computed(() => {
  const parts = []
  if (servedFromCache.value || connection.value !== 'live') {
    parts.push('dispo hors-ligne')
  } else {
    parts.push('synchronisé')
  }
  if (syncedAt.value) parts.push(`dernière sync ${syncedAt.value}`)
  return parts.join(' · ')
})
</script>

<template>
  <div v-if="compact" class="d-flex align-center ga-1 text-caption em-muted">
    <v-icon :icon="state.icon" :color="state.color" size="16" />
    <span>{{ state.label }}</span>
    <v-icon v-if="connection === 'live'" icon="mdi-check" size="14" />
  </div>

  <div v-else class="d-flex align-center ga-2 text-caption">
    <v-icon :icon="state.icon" :color="state.color" size="14" />
    <span :class="connection === 'live' ? 'text-info' : 'em-muted'">
      {{ fullLabel }}
    </span>
  </div>
</template>
