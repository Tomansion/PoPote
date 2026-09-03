<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import UserAvatar from '@/components/UserAvatar.vue'
import { api, ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { useEventsStore } from '@/stores/events'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const events = useEventsStore()

const code = String(route.params.code ?? '').toUpperCase()

const preview = ref(null)
const loading = ref(true)
const joining = ref(false)
const error = ref(null)

function formatRange(p) {
  const opts = { day: 'numeric', month: 'long' }
  const start = new Date(p.starts_on)
  const end = new Date(p.ends_on)
  if (p.starts_on === p.ends_on) {
    return start.toLocaleDateString('fr-FR', { ...opts, weekday: 'long' })
  }
  return `du ${start.toLocaleDateString('fr-FR', opts)} au ${end.toLocaleDateString('fr-FR', opts)}`
}

onMounted(async () => {
  try {
    preview.value = await api.previewInvite(code)
  } catch (err) {
    error.value =
      err instanceof ApiError && err.status === 404
        ? 'Cette invitation n’existe plus.'
        : 'Impossible de charger cette invitation.'
  } finally {
    loading.value = false
  }
})

async function accept() {
  joining.value = true
  try {
    await events.joinByCode(code)
    router.replace('/planner')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : 'Impossible de rejoindre.'
  } finally {
    joining.value = false
  }
}
</script>

<template>
  <v-container class="fill-height justify-center pa-4">
    <div class="text-center" style="width: 100%; max-width: 400px">
      <v-progress-circular v-if="loading" indeterminate color="primary" />

      <template v-else-if="error">
        <v-icon icon="mdi-link-variant-off" size="48" class="mb-4 em-muted" />
        <p class="text-body-2 em-muted mb-6">{{ error }}</p>
        <v-btn variant="tonal" @click="router.replace('/planner')">Retour</v-btn>
      </template>

      <template v-else-if="preview">
        <div class="text-caption em-muted mb-2">INVITATION</div>
        <h2 class="text-h6 font-weight-medium text-primary mb-1">{{ preview.name }}</h2>
        <p class="text-body-2 em-muted text-capitalize mb-1">{{ formatRange(preview) }}</p>
        <p class="text-body-2 em-muted mb-8">
          Proposé par {{ preview.owner_name }} ·
          {{ preview.member_count }} participant{{ preview.member_count > 1 ? 's' : '' }}
        </p>

        <div class="d-flex flex-column align-center mb-8">
          <UserAvatar :seed="auth.user?.avatar_seed ?? 0" :size="64" class="em-outline mb-2" />
          <div class="text-body-2">
            Vous rejoindrez en tant que <strong>{{ auth.user?.display_name }}</strong>
          </div>
        </div>

        <v-alert
          v-if="preview.already_member"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          Vous participez déjà à cet événement.
        </v-alert>

        <v-btn
          v-if="preview.already_member"
          block
          size="large"
          variant="flat"
          color="primary"
          @click="router.replace('/planner')"
        >
          Voir l’événement
        </v-btn>
        <v-btn
          v-else
          block
          size="large"
          variant="flat"
          color="primary"
          :loading="joining"
          @click="accept"
        >
          Rejoindre
        </v-btn>

        <v-btn variant="text" size="small" class="mt-3" @click="router.replace('/planner')">
          Non merci
        </v-btn>
      </template>
    </div>
  </v-container>
</template>
