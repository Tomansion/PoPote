<script setup>
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'

defineProps({
  size: { type: [Number, String], default: 32 },
  /** Show the display name beside the avatar, as in the top bar. */
  showName: { type: Boolean, default: false },
})

defineEmits(['click'])

const auth = useAuthStore()
</script>

<template>
  <button class="pp-avatar-button" aria-label="Mon compte" @click="$emit('click')">
    <UserAvatar :seed="auth.user?.avatar_seed ?? 0" :size="size" class="em-outline" />
    <!-- Truncated rather than hidden on a phone: the name is the point of
         showing it, and the centred page title keeps its own room. -->
    <span v-if="showName" class="text-body-2 text-truncate pp-avatar-name">
      {{ auth.user?.display_name }}
    </span>
  </button>
</template>

<style scoped>
.pp-avatar-button {
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  line-height: 0;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: inherit;
}

.pp-avatar-name {
  line-height: 1.2;
  max-width: 12rem;
}

/* A long name must never push into the centred page title. */
@media (max-width: 600px) {
  .pp-avatar-name {
    max-width: 5.5rem;
  }
}
</style>
