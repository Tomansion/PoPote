<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

import { ApiError } from '@/api/client'
import SectionHeader from '@/components/SectionHeader.vue'
import { useAuthStore } from '@/stores/auth'
import { groceryLink, groupItems, useGroceryStore } from '@/stores/grocery'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const grocery = useGroceryStore()
const { shared, loading, busy } = storeToRefs(grocery)

/** 'aisle' walks the shop; 'recipe' checks nothing has been forgotten. */
const mode = ref('aisle')
const error = ref('')
const copied = ref(false)
const shareCopied = ref(false)

const code = computed(() => route.params.code)
const items = computed(() => shared.value?.items ?? [])

const groups = computed(() => groupItems(items.value, mode.value))

const progress = computed(() => {
  const total = items.value.length
  const done = items.value.filter((item) => item.checked).length
  return { total, done, percent: total ? Math.round((done / total) * 100) : 0 }
})

const priceLabel = (value) =>
  value === null || value === undefined
    ? ''
    : `${value.toFixed(2).replace('.', ',')} €`

const quantityLabel = (item) => {
  if (item.quantity === null || item.quantity === undefined) return item.unit || ''
  const rounded = Math.round(item.quantity * 100) / 100
  const number = Number.isInteger(rounded)
    ? String(rounded)
    : String(rounded).replace('.', ',')
  return `${number} ${item.unit}`.trim()
}

watch(
  code,
  async (value) => {
    if (!value) return
    error.value = ''
    try {
      await grocery.openShared(value)
    } catch (err) {
      error.value =
        err instanceof ApiError && err.status === 404
          ? 'Cette liste de courses n’existe plus.'
          : 'Impossible de charger cette liste.'
    }
  },
  { immediate: true },
)

// The socket is per-page: leaving it open after navigating away would keep a
// connection per list the user has ever glanced at.
onBeforeUnmount(() => grocery.stopShared())

function toggle(item) {
  grocery.toggleItem(code.value, item.key, !item.checked)
}

async function estimate() {
  if (!shared.value) return
  try {
    await grocery.estimatePrices(shared.value.event_id)
  } catch {
    // The store raised the toast.
  }
}

async function regenerate() {
  if (!shared.value) return
  try {
    await grocery.generate(shared.value.event_id)
  } catch {
    // Already reported.
  }
}

/** The whole list as plain text, for pasting into a message. */
function asText() {
  const lines = [shared.value?.event_name || 'Liste de courses', '']
  for (const group of groups.value) {
    lines.push(`— ${group.title} —`)
    for (const item of group.items) {
      const quantity = quantityLabel(item)
      lines.push(`${item.checked ? '[x]' : '[ ]'} ${item.name}${quantity ? ` : ${quantity}` : ''}`)
    }
    lines.push('')
  }
  if (shared.value?.total_price) {
    lines.push(`Total estimé : ${priceLabel(shared.value.total_price)}`)
  }
  return lines.join('\n')
}

async function copyText() {
  try {
    await navigator.clipboard.writeText(asText())
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
  } catch {
    copied.value = false
  }
}

async function share() {
  const url = groceryLink(code.value)
  if (navigator.share) {
    try {
      await navigator.share({ title: shared.value?.event_name, url })
      return
    } catch {
      // Cancelled, or unavailable despite the feature check: fall through.
    }
  }
  try {
    await navigator.clipboard.writeText(url)
    shareCopied.value = true
    setTimeout(() => (shareCopied.value = false), 2500)
  } catch {
    shareCopied.value = false
  }
}
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <div class="em-scroll flex-grow-1">
      <v-container class="pa-4" style="max-width: 720px">
        <div class="d-flex align-center ga-2 mb-3">
          <v-btn
            v-if="auth.isAuthenticated"
            variant="text"
            size="small"
            prepend-icon="mdi-arrow-left"
            @click="router.back()"
          >
            retour
          </v-btn>
          <v-spacer />
          <v-btn
            variant="text"
            size="small"
            :prepend-icon="shareCopied ? 'mdi-check' : 'mdi-share-variant-outline'"
            @click="share"
          >
            {{ shareCopied ? 'Lien copié' : 'Partager' }}
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            :prepend-icon="copied ? 'mdi-check' : 'mdi-content-copy'"
            @click="copyText"
          >
            {{ copied ? 'Copié' : 'Copier' }}
          </v-btn>
        </div>

        <v-skeleton-loader v-if="loading && !shared" type="article" />

        <div v-else-if="error" class="text-center em-muted py-12">
          <v-icon icon="mdi-cart-off" size="48" class="mb-4" />
          <p class="text-body-2">{{ error }}</p>
        </div>

        <template v-else-if="shared">
          <h2 class="text-h6 font-weight-medium mb-1">{{ shared.event_name }}</h2>
          <p class="text-body-2 em-muted mb-3">
            {{ progress.done }} / {{ progress.total }} articles
            <template v-if="shared.total_price">
              · <strong>{{ priceLabel(shared.total_price) }}</strong> estimés
            </template>
          </p>

          <v-progress-linear
            :model-value="progress.percent"
            color="success"
            height="8"
            rounded
            class="mb-4"
          />

          <div class="d-flex align-center flex-wrap ga-2 mb-5">
            <v-btn-toggle v-model="mode" density="compact" mandatory variant="outlined">
              <v-btn value="aisle" size="small">Par rayon</v-btn>
              <v-btn value="recipe" size="small">Par recette</v-btn>
            </v-btn-toggle>
            <v-spacer />
            <!-- Both need the event behind the list, so they are only offered
                 to someone signed in as one of its members. -->
            <template v-if="auth.isAuthenticated">
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-refresh"
                :loading="busy"
                @click="regenerate"
              >
                Régénérer
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-currency-eur"
                :loading="busy"
                @click="estimate"
              >
                Estimer les prix
              </v-btn>
            </template>
          </div>

          <div v-if="!items.length" class="text-center em-muted py-10">
            <v-icon icon="mdi-cart-outline" size="40" class="mb-3" />
            <p class="text-body-2">
              Rien à acheter pour l’instant — planifiez des repas puis
              régénérez la liste.
            </p>
          </div>

          <div v-for="group in groups" :key="group.key" class="mb-5">
            <SectionHeader icon="mdi-tag-outline" :title="group.title" />
            <v-list class="pa-0 bg-transparent">
              <v-list-item
                v-for="(item, index) in group.items"
                :key="`${item.key}-${index}`"
                class="px-0"
                @click="toggle(item)"
              >
                <template #prepend>
                  <v-checkbox-btn
                    :model-value="item.checked"
                    density="compact"
                    color="success"
                    @click.stop="toggle(item)"
                  />
                </template>
                <v-list-item-title
                  class="text-body-2"
                  :class="item.checked ? 'pp-done' : ''"
                >
                  {{ item.name }}
                </v-list-item-title>
                <template #append>
                  <div class="text-end">
                    <div class="text-body-2 em-mono">{{ quantityLabel(item) }}</div>
                    <div v-if="item.price !== null" class="text-caption em-muted em-mono">
                      {{ priceLabel(item.price) }}
                    </div>
                  </div>
                </template>
              </v-list-item>
            </v-list>
          </div>

          <p v-if="items.length" class="text-caption em-muted">
            Tout le monde voit les cases cochées en direct.
            <template v-if="shared.priced_at">
              Les prix sont une estimation, pas un devis.
            </template>
          </p>
        </template>
      </v-container>
    </div>
  </div>
</template>

<style scoped>
.pp-done {
  text-decoration: line-through;
  color: var(--em-muted);
}
</style>
