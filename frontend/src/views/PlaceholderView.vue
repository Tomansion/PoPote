<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const title = computed(() => route.meta.title)
const icon = computed(() => route.meta.icon ?? 'mdi-progress-wrench')
const blurb = computed(() => route.meta.blurb ?? '')
</script>

<template>
  <v-container class="fill-height justify-center">
    <div class="text-center em-muted" style="max-width: 380px">
      <v-icon :icon="icon" size="48" class="mb-4" />
      <h2 class="text-h6 font-weight-medium mb-2 text-primary">{{ title }}</h2>
      <p class="text-body-2 mb-4">{{ blurb }}</p>
      <v-chip size="small" variant="outlined">Pas encore implémenté</v-chip>
    </div>
  </v-container>
</template>
