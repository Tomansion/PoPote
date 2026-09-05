<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import UserAvatar from '@/components/UserAvatar.vue'
import { randomAvatarSeed, useAuthStore } from '@/stores/auth'

// A single instance of this panel lives at the top level of the app shell —
// it must not be nested inside the app bar or the desktop drawer, since both
// apply a CSS transform to themselves, which would turn this drawer's fixed
// positioning into a slide-inside-that-box instead of a full-screen overlay.
const open = defineModel({ type: Boolean, default: false })

const auth = useAuthStore()
const router = useRouter()

const editing = ref(false)
const draftName = ref('')
const draftSeed = ref(0)
const saving = ref(false)

// Reset back to the menu, rather than a stale edit form, every time the panel
// is reopened.
watch(open, (value) => {
  if (!value) editing.value = false
})

watch(editing, (value) => {
  if (!value) return
  draftName.value = auth.user?.display_name ?? ''
  draftSeed.value = auth.user?.avatar_seed ?? 0
})

function go(name) {
  open.value = false
  router.push({ name })
}

async function save() {
  saving.value = true
  await auth.updateProfile({
    displayName: draftName.value.trim() || undefined,
    avatarSeed: draftSeed.value,
  })
  saving.value = false
  editing.value = false
}

async function signOut() {
  open.value = false
  await auth.signOut()
  // A full reload is the simplest way to be sure nothing from the previous
  // session is left in memory — stores, the socket, or an in-flight request.
  window.location.assign('/login')
}
</script>

<template>
  <v-navigation-drawer v-model="open" temporary location="start" width="280">
    <div class="pa-5 text-center">
      <UserAvatar
        :seed="editing ? draftSeed : (auth.user?.avatar_seed ?? 0)"
        :size="72"
        class="em-outline mx-auto mb-3"
      />

      <template v-if="editing">
        <v-btn
          variant="text"
          size="small"
          prepend-icon="mdi-dice-5-outline"
          class="mb-3"
          @click="draftSeed = randomAvatarSeed()"
        >
          Changer d'avatar
        </v-btn>
        <v-text-field v-model="draftName" label="Nom affiché" density="compact" hide-details />
      </template>

      <div v-else class="text-subtitle-2">{{ auth.user?.display_name }}</div>
    </div>

    <v-divider />

    <div v-if="editing" class="pa-4 d-flex justify-end ga-2">
      <v-btn variant="text" size="small" @click="editing = false">Annuler</v-btn>
      <v-btn color="primary" variant="flat" size="small" :loading="saving" @click="save">
        Enregistrer
      </v-btn>
    </div>

    <v-list v-else nav density="compact">
      <v-list-item
        prepend-icon="mdi-account-outline"
        title="Mon profil"
        rounded="lg"
        @click="editing = true"
      />
      <v-list-item
        prepend-icon="mdi-account-group-outline"
        title="Mes amis"
        rounded="lg"
        @click="go('friends')"
      />
      <v-list-item
        prepend-icon="mdi-cog-outline"
        title="Paramètres"
        rounded="lg"
        @click="go('settings')"
      />
    </v-list>

    <template #append>
      <v-list v-if="!editing" nav density="compact" class="pb-2">
        <v-list-item
          prepend-icon="mdi-logout"
          title="Déconnexion"
          rounded="lg"
          @click="signOut"
        />
      </v-list>
    </template>
  </v-navigation-drawer>
</template>
