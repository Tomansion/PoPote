<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import ProfilePrefsForm from '@/components/ProfilePrefsForm.vue'
import SectionHeader from '@/components/SectionHeader.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { randomAvatarSeed, useAuthStore } from '@/stores/auth'
import { answeredPrefs, blankPrefs } from '@/utils/prefs'

const auth = useAuthStore()
const router = useRouter()

const name = ref('')
const seed = ref(0)
const prefs = ref(blankPrefs())
const saving = ref(false)
const saved = ref(false)

/**
 * Load the form from the session.
 *
 * `blankPrefs()` first, then the stored answers on top: an account created
 * before the questions existed has no `prefs` at all, and every field still
 * has to be present for `v-model` to bind to it.
 */
function load() {
  name.value = auth.user?.display_name ?? ''
  seed.value = auth.user?.avatar_seed ?? 0
  prefs.value = { ...blankPrefs(), ...(auth.user?.prefs ?? {}) }
}

watch(() => auth.user, load, { immediate: true, deep: false })

const answeredCount = computed(() => answeredPrefs(prefs.value).length)

const dirty = computed(
  () =>
    name.value.trim() !== (auth.user?.display_name ?? '') ||
    seed.value !== (auth.user?.avatar_seed ?? 0) ||
    JSON.stringify(prefs.value) !==
      JSON.stringify({ ...blankPrefs(), ...(auth.user?.prefs ?? {}) }),
)

async function save() {
  if (!name.value.trim()) return
  saving.value = true
  // The combobox hands back null when a field is cleared; the API wants the
  // ten keys present, as strings.
  const answers = Object.fromEntries(
    Object.entries(prefs.value).map(([key, value]) => [key, (value ?? '').trim()]),
  )
  const ok = await auth.updateProfile({
    displayName: name.value.trim(),
    avatarSeed: seed.value,
    prefs: answers,
  })
  saving.value = false
  saved.value = ok
  if (ok) setTimeout(() => (saved.value = false), 2500)
}
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <!-- This screen hides the app bar (meta.detail), so it carries its own
         way back — the bottom navigation has no entry for the profile. -->
    <div class="d-flex align-center ga-2 pa-4 pb-0">
      <v-btn variant="text" size="small" prepend-icon="mdi-arrow-left" @click="router.back()">
        retour
      </v-btn>
    </div>

    <div class="em-scroll flex-grow-1">
      <v-container class="pa-4" style="max-width: 640px">
        <div class="text-center mb-6">
          <UserAvatar :seed="seed" :size="88" class="em-outline mx-auto mb-3" />
          <div>
            <v-btn
              variant="text"
              size="small"
              prepend-icon="mdi-dice-5-outline"
              @click="seed = randomAvatarSeed()"
            >
              Changer d’avatar
            </v-btn>
          </div>
        </div>

        <SectionHeader icon="mdi-account-outline" title="Mon compte" />
        <v-text-field v-model="name" label="Nom affiché" class="mb-6" />

        <SectionHeader icon="mdi-silverware-fork-knife" title="À table" />
        <p class="text-body-2 em-muted mb-4">
          Ce que voient les personnes avec qui vous organisez un événement, pour
          savoir quoi cuisiner, et pour le plaisir. Tout est facultatif !
          <span v-if="answeredCount" class="em-mono">
            ({{ answeredCount }}/10 remplies)
          </span>
        </p>

        <ProfilePrefsForm v-model="prefs" />

        <div class="d-flex align-center ga-2 mt-8">
          <v-spacer />
          <span v-if="saved" class="text-caption text-success">Enregistré</span>
          <v-btn
            color="primary"
            variant="flat"
            :loading="saving"
            :disabled="!dirty || !name.trim()"
            @click="save"
          >
            Enregistrer
          </v-btn>
        </div>
      </v-container>
    </div>
  </div>
</template>
