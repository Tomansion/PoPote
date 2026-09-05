<script setup>
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'

defineProps({
  size: { type: [Number, String], default: 32 },
})

defineEmits(['click'])

const auth = useAuthStore()
</script>

<template>
  <button class="pp-avatar-button" aria-label="Mon compte" @click="$emit('click')">
    <UserAvatar :seed="auth.user?.avatar_seed ?? 0" :size="size" class="em-outline" />
  </button>
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
