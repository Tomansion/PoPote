<script setup>
import { ref, watch } from 'vue'

import UserAvatar from '@/components/UserAvatar.vue'
import { randomAvatarSeed, useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const open = ref(false)
const editing = ref(false)
const draftName = ref('')
const draftSeed = ref(0)
const saving = ref(false)

defineProps({
  size: { type: [Number, String], default: 32 },
})

watch(editing, (value) => {
  if (!value) return
  draftName.value = auth.user?.display_name ?? ''
  draftSeed.value = auth.user?.avatar_seed ?? 0
})

async function save() {
  saving.value = true
  await auth.updateProfile({
    displayName: draftName.value.trim() || undefined,
    avatarSeed: draftSeed.value,
  })
  saving.value = false
  editing.value = false
  open.value = false
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
  <v-menu v-model="open" :close-on-content-click="false" location="bottom end">
    <template #activator="{ props }">
      <button v-bind="props" class="pp-avatar-button" aria-label="Mon profil">
        <UserAvatar :seed="auth.user?.avatar_seed ?? 0" :size="size" class="em-outline" />
      </button>
    </template>

    <v-card rounded="xl" min-width="260">
      <v-card-text class="text-center pt-5">
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
      </v-card-text>

      <v-card-actions class="px-4 pb-4">
        <template v-if="editing">
          <v-spacer />
          <v-btn variant="text" size="small" @click="editing = false">Annuler</v-btn>
          <v-btn color="primary" variant="flat" size="small" :loading="saving" @click="save">
            Enregistrer
          </v-btn>
        </template>
        <template v-else>
          <v-btn variant="text" size="small" prepend-icon="mdi-pencil-outline" @click="editing = true">
            Modifier
          </v-btn>
          <v-spacer />
          <v-btn variant="text" size="small" color="error" prepend-icon="mdi-logout" @click="signOut">
            Déconnexion
          </v-btn>
        </template>
      </v-card-actions>
    </v-card>
  </v-menu>
</template>

<style scoped>
.pp-avatar-button {
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  line-height: 0;
  border-radius: 50%;
}
</style>
