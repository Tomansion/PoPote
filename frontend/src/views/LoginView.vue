<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

import UserAvatar from '@/components/UserAvatar.vue'
import { randomAvatarSeed, useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { busy, error } = storeToRefs(auth)

// One screen, two modes: a separate signup route would double the navigation
// for what is three extra fields.
const mode = ref('login')
const isRegister = computed(() => mode.value === 'register')

const email = ref('')
const password = ref('')
const displayName = ref('')
const avatarSeed = ref(randomAvatarSeed())
const showPassword = ref(false)

const emailRules = [
  (v) => !!v?.trim() || 'Email requis',
  (v) => /.+@.+\..+/.test(v ?? '') || 'Email invalide',
]
const passwordRules = [
  (v) => !!v || 'Mot de passe requis',
  (v) => (v?.length ?? 0) >= 8 || 'Au moins 8 caractères',
]
const nameRules = [(v) => !!v?.trim() || 'Un nom est requis']

const formValid = computed(() => {
  const base = /.+@.+\..+/.test(email.value) && password.value.length >= 8
  return isRegister.value ? base && displayName.value.trim().length > 0 : base
})

function switchMode() {
  mode.value = isRegister.value ? 'login' : 'register'
  error.value = null
}

async function submit() {
  if (!formValid.value || busy.value) return

  const ok = isRegister.value
    ? await auth.register({
        email: email.value.trim(),
        password: password.value,
        displayName: displayName.value.trim(),
        avatarSeed: avatarSeed.value,
      })
    : await auth.login(email.value.trim(), password.value)

  if (!ok) return

  // Signing in from an invite link lands on the invite, not on the recipes.
  const next = typeof route.query.next === 'string' ? route.query.next : '/'
  router.replace(next)
}
</script>

<template>
  <v-container class="fill-height justify-center pa-4">
    <div style="width: 100%; max-width: 400px">
      <div class="text-center mb-8">
        <div class="text-h5 font-weight-medium text-primary">Po'Pote</div>
        <div class="text-body-2 em-muted mt-1">
          {{ isRegister ? 'Créez votre compte' : 'Content de vous revoir' }}
        </div>
      </div>

      <!-- The avatar is picked before the account exists, so a new user sees
           who they are about to be rather than a placeholder. -->
      <div v-if="isRegister" class="d-flex flex-column align-center mb-6">
        <UserAvatar :seed="avatarSeed" :size="96" class="em-outline mb-3" />
        <v-btn
          variant="text"
          size="small"
          prepend-icon="mdi-dice-5-outline"
          @click="avatarSeed = randomAvatarSeed()"
        >
          Changer d'avatar
        </v-btn>
      </div>

      <v-form @submit.prevent="submit">
        <v-text-field
          v-if="isRegister"
          v-model="displayName"
          label="Nom affiché"
          placeholder="Comment vos amis vous connaissent"
          prepend-inner-icon="mdi-account-outline"
          :rules="nameRules"
          autocomplete="nickname"
          class="mb-2"
        />

        <v-text-field
          v-model="email"
          label="Email"
          type="email"
          prepend-inner-icon="mdi-email-outline"
          :rules="emailRules"
          autocomplete="email"
          class="mb-2"
        />

        <v-text-field
          v-model="password"
          label="Mot de passe"
          :type="showPassword ? 'text' : 'password'"
          prepend-inner-icon="mdi-lock-outline"
          :append-inner-icon="showPassword ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
          :rules="passwordRules"
          :hint="isRegister ? 'Au moins 8 caractères' : undefined"
          persistent-hint
          :autocomplete="isRegister ? 'new-password' : 'current-password'"
          @click:append-inner="showPassword = !showPassword"
        />

        <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-4">
          {{ error }}
        </v-alert>

        <v-btn
          type="submit"
          block
          size="large"
          color="primary"
          class="mt-6"
          :loading="busy"
          :disabled="!formValid"
        >
          {{ isRegister ? 'Créer mon compte' : 'Se connecter' }}
        </v-btn>
      </v-form>

      <div class="text-center mt-6">
        <v-btn variant="text" size="small" @click="switchMode">
          {{ isRegister ? 'J’ai déjà un compte' : 'Créer un compte' }}
        </v-btn>
      </div>

      <p v-if="isRegister" class="text-caption em-muted text-center mt-4">
        Il n’y a pas de récupération de mot de passe pour l’instant : notez-le
        quelque part.
      </p>
    </div>
  </v-container>
</template>
