<script setup>
// The one place that reaches outside src/ for the master artwork. Vite hashes
// and copies it like any other asset, so the APK bundles it too.
import logoUrl from '../../assets/logo.png'

defineProps({
  size: { type: [Number, String], default: 32 },
})
</script>

<template>
  <img :src="logoUrl" :width="size" :height="size" alt="Po'Pote" class="pp-logo" />
</template>

<style scoped>
.pp-logo {
  object-fit: contain;
  display: block;
  flex: none;
}
</style>
