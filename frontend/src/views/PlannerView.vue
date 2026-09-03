<script setup>
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useDisplay } from 'vuetify'

import EventFormDialog from '@/components/EventFormDialog.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { inviteLink, useEventsStore } from '@/stores/events'
import { useAuthStore } from '@/stores/auth'

const store = useEventsStore()
const auth = useAuthStore()
const { mdAndUp } = useDisplay()
const { loading, upcoming, past } = storeToRefs(store)

const showPast = ref(false)
/** The event whose invite sheet is open, if any. */
const sharing = ref(null)
const copied = ref(false)
const confirming = ref(null)

const isOwner = (event) => event.owner_id === auth.user?.id

const shareUrl = computed(() => (sharing.value ? inviteLink(sharing.value.invite_code) : ''))

function formatRange(event) {
  const opts = { day: 'numeric', month: 'long' }
  const start = new Date(event.starts_on)
  const end = new Date(event.ends_on)
  const year = end.getFullYear() === new Date().getFullYear() ? '' : ` ${end.getFullYear()}`

  if (event.starts_on === event.ends_on) {
    return `${start.toLocaleDateString('fr-FR', { ...opts, weekday: 'long' })}${year}`
  }
  return `du ${start.toLocaleDateString('fr-FR', opts)} au ${end.toLocaleDateString('fr-FR', opts)}${year}`
}

function openShare(event) {
  sharing.value = event
  copied.value = false
}

/**
 * Hand the link to the OS share sheet where there is one — that is the natural
 * gesture on a phone and inside the APK — and fall back to the clipboard on
 * desktop. Both paths end at the same link.
 */
async function share() {
  const url = shareUrl.value
  if (navigator.share) {
    try {
      await navigator.share({ title: sharing.value.name, text: 'Rejoins mon événement', url })
      return
    } catch {
      // Cancelled, or unavailable despite the feature check: fall through.
    }
  }
  try {
    await navigator.clipboard.writeText(url)
    copied.value = true
    setTimeout(() => (copied.value = false), 2500)
  } catch {
    copied.value = false
  }
}

async function confirmRemove() {
  const event = confirming.value
  confirming.value = null
  if (!event) return
  if (isOwner(event)) await store.deleteEvent(event.id)
  else await store.leaveEvent(event.id)
}
</script>

<template>
  <v-container class="pa-4" style="max-width: 760px">
    <div class="d-flex align-center mb-4">
      <!-- On mobile the app bar already shows the section title. -->
      <h2 v-if="mdAndUp" class="text-h6 font-weight-medium text-primary">Planificateur</h2>
      <v-spacer />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="store.openCreateForm()">
        Événement
      </v-btn>
    </div>

    <v-skeleton-loader v-if="loading" type="list-item-two-line@3" />

    <div v-else-if="!upcoming.length && !past.length" class="text-center em-muted py-12">
      <v-icon icon="mdi-calendar-blank-outline" size="48" class="mb-4" />
      <p class="text-body-2 mb-4">
        Aucun événement pour le moment.<br />
        Créez-en un et partagez le lien pour inviter vos proches.
      </p>
    </div>

    <template v-else>
      <v-card
        v-for="event in upcoming"
        :key="event.id"
        rounded="xl"
        variant="outlined"
        class="mb-3"
      >
        <v-card-item>
          <v-card-title class="text-subtitle-1">{{ event.name }}</v-card-title>
          <v-card-subtitle class="text-capitalize">{{ formatRange(event) }}</v-card-subtitle>
        </v-card-item>

        <v-card-text class="pt-0">
          <div class="d-flex align-center ga-2">
            <div class="d-flex">
              <UserAvatar
                v-for="member in event.members"
                :key="member.id"
                :seed="member.avatar_seed"
                :size="28"
                class="em-outline pp-stack"
              />
            </div>
            <span class="text-caption em-muted">
              {{ event.members.map((m) => m.display_name).join(', ') }}
            </span>
          </div>
        </v-card-text>

        <v-card-actions class="px-4 pb-3">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-share-variant-outline" @click="openShare(event)">
            Inviter
          </v-btn>
          <v-spacer />
          <v-btn v-if="isOwner(event)" size="small" variant="text" icon="mdi-pencil-outline" @click="store.openEditForm(event)" />
          <v-btn
            size="small"
            variant="text"
            :icon="isOwner(event) ? 'mdi-delete-outline' : 'mdi-exit-to-app'"
            @click="confirming = event"
          />
        </v-card-actions>
      </v-card>

      <template v-if="past.length">
        <v-btn variant="text" size="small" class="mt-2" @click="showPast = !showPast">
          {{ showPast ? 'Masquer' : 'Voir' }} les événements passés ({{ past.length }})
        </v-btn>
        <v-expand-transition>
          <div v-if="showPast" class="mt-2">
            <v-card
              v-for="event in past"
              :key="event.id"
              rounded="xl"
              variant="outlined"
              class="mb-2"
              style="opacity: 0.6"
            >
              <v-card-item>
                <v-card-title class="text-subtitle-2">{{ event.name }}</v-card-title>
                <v-card-subtitle class="text-caption">{{ formatRange(event) }}</v-card-subtitle>
              </v-card-item>
            </v-card>
          </div>
        </v-expand-transition>
      </template>
    </template>

    <EventFormDialog />

    <!-- ===================== Invite sheet ===================== -->
    <v-dialog :model-value="Boolean(sharing)" max-width="440" @update:model-value="sharing = null">
      <v-card v-if="sharing" rounded="xl">
        <v-card-title class="text-subtitle-1 font-weight-medium pt-5 px-5">
          Inviter à « {{ sharing.name }} »
        </v-card-title>
        <v-card-text class="px-5">
          <p class="text-body-2 em-muted mb-4">
            Toute personne ayant ce lien peut rejoindre l’événement.
          </p>

          <v-text-field :model-value="shareUrl" readonly hide-details density="compact" class="mb-3" />

          <div class="text-center">
            <div class="text-caption em-muted mb-1">ou avec ce code</div>
            <div class="text-h6 font-weight-medium" style="letter-spacing: 0.2em">
              {{ sharing.invite_code }}
            </div>
          </div>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" @click="sharing = null">Fermer</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :prepend-icon="copied ? 'mdi-check' : 'mdi-share-variant-outline'"
            @click="share"
          >
            {{ copied ? 'Lien copié' : 'Partager' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ===================== Delete / leave ===================== -->
    <v-dialog :model-value="Boolean(confirming)" max-width="400" @update:model-value="confirming = null">
      <v-card v-if="confirming" rounded="xl">
        <v-card-title class="text-subtitle-1 pt-5 px-5">
          {{ isOwner(confirming) ? 'Supprimer l’événement ?' : 'Quitter l’événement ?' }}
        </v-card-title>
        <v-card-text class="px-5 text-body-2 em-muted">
          <template v-if="isOwner(confirming)">
            « {{ confirming.name }} » sera supprimé pour tous les participants.
          </template>
          <template v-else>
            Vous ne verrez plus « {{ confirming.name }} ». Le lien d’invitation
            permet de le rejoindre à nouveau.
          </template>
        </v-card-text>
        <v-card-actions class="px-5 pb-5">
          <v-spacer />
          <v-btn variant="text" @click="confirming = null">Annuler</v-btn>
          <v-btn color="error" variant="flat" @click="confirmRemove">
            {{ isOwner(confirming) ? 'Supprimer' : 'Quitter' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<style scoped>
/* Overlap the member avatars slightly, so a long list stays compact. */
.pp-stack + .pp-stack {
  margin-left: -8px;
}
</style>
