<script setup>
import { PREF_QUESTIONS } from '@/utils/prefs'

/**
 * The ten answers, as ten fields.
 *
 * A combobox rather than a select even where there are suggestions: "Je bois
 * de tout" covers most people, but the point of the fun half of this list is
 * that anyone can write their own answer, and one widget for all ten keeps the
 * screen from turning into a form.
 */
const model = defineModel({ type: Object, required: true })
</script>

<template>
  <div class="d-flex flex-column ga-4">
    <v-combobox
      v-for="question in PREF_QUESTIONS"
      :key="question.key"
      v-model="model[question.key]"
      :items="question.suggestions ?? []"
      :label="question.label"
      :placeholder="question.placeholder"
      :prepend-inner-icon="question.icon"
      :menu-icon="question.suggestions ? undefined : ''"
      variant="outlined"
      density="comfortable"
      hide-details="auto"
      persistent-placeholder
      clearable
    />
  </div>
</template>
