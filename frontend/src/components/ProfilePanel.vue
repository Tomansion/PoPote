<script setup>
import { useRouter } from 'vue-router'

import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'

// A single instance of this panel lives at the top level of the app shell —
// it must not be nested inside the app bar or the desktop drawer, since both
// apply a CSS transform to themselves, which would turn this drawer's fixed
// positioning into a slide-inside-that-box instead of a full-screen overlay.
const open = defineModel({ type: Boolean, default: false })

const auth = useAuthStore()
const router = useRouter()

function go(name) {
  open.value = false
  router.push({ name })
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
    <!-- Editing used to happen inline here. It moved to its own page when the
         profile grew ten questions: a 280px drawer is the wrong shape for a
         form you actually have to think about. -->
    <button class="pp-profile-header pa-5 text-center" @click="go('profile')">
      <UserAvatar
        :seed="auth.user?.avatar_seed ?? 0"
        :size="72"
        class="em-outline mx-auto mb-3"
      />
      <div class="text-subtitle-2">{{ auth.user?.display_name }}</div>
      <div class="text-caption em-muted">Voir mon profil</div>
    </button>

    <v-divider />

    <v-list nav density="compact">
      <v-list-item
        prepend-icon="mdi-account-outline"
        title="Mon profil"
        rounded="lg"
        @click="go('profile')"
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
      <v-list nav density="compact" class="pb-2">
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

<style scoped>
.pp-profile-header {
  display: block;
  width: 100%;
  background: none;
  border: 0;
  cursor: pointer;
  color: inherit;
  font: inherit;
}
</style>
