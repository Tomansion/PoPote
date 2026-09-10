<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

import { useGroceryStore } from '@/stores/grocery'

const router = useRouter()
const grocery = useGroceryStore()
const { summaries, loading } = storeToRefs(grocery)

// Refreshed on every visit: the counters move as other people tick things off
// at the shop, and a stale "0/24" is exactly the wrong thing to show.
onMounted(() => grocery.loadSummaries())

const priceLabel = (value) =>
  value === null || value === undefined ? '' : `${value.toFixed(2).replace('.', ',')} €`

function percent(row) {
  return row.item_count ? Math.round((row.checked_count / row.item_count) * 100) : 0
}

function formatRange(row) {
  if (!row.starts_on) return ''
  const options = { day: 'numeric', month: 'short' }
  const start = new Date(row.starts_on).toLocaleDateString('fr-FR', options)
  const end = new Date(row.ends_on).toLocaleDateString('fr-FR', options)
  return row.starts_on === row.ends_on ? start : `${start} – ${end}`
}
</script>

<template>
  <v-container class="pa-4" style="max-width: 760px">
    <v-skeleton-loader v-if="loading && !summaries.length" type="list-item-two-line@3" />

    <div v-else-if="!summaries.length" class="text-center em-muted py-12">
      <v-icon icon="mdi-cart-outline" size="48" class="mb-4" />
      <p class="text-body-2 mb-4">
        Aucune liste pour le moment.<br />
        Les listes se génèrent depuis un événement, à partir des repas planifiés.
      </p>
      <v-btn size="small" @click="router.push({ name: 'planner' })">
        Voir mes événements
      </v-btn>
    </div>

    <v-card
      v-for="row in summaries"
      :key="row.event_id"
      variant="outlined"
      rounded="xl"
      class="mb-3"
      @click="router.push({ name: 'grocery', params: { code: row.share_code } })"
    >
      <v-card-item>
        <v-card-title class="text-subtitle-1">{{ row.event_name }}</v-card-title>
        <v-card-subtitle class="text-caption">
          {{ formatRange(row) }}
          <template v-if="row.total_price">
            · {{ priceLabel(row.total_price) }} estimés
          </template>
        </v-card-subtitle>
      </v-card-item>

      <v-card-text class="pt-0">
        <v-progress-linear
          :model-value="percent(row)"
          color="success"
          height="6"
          rounded
          class="mb-2"
        />
        <span class="text-caption em-muted">
          {{ row.checked_count }} / {{ row.item_count }} articles cochés
        </span>
      </v-card-text>
    </v-card>
  </v-container>
</template>
