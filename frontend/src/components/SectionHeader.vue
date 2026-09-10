<script setup>
/**
 * The "icon — title — rule" heading from the recipe form.
 *
 * Extracted so the form and the recipe *display* share one definition rather
 * than two that drift apart: the two screens show the same recipe and used to
 * introduce its ingredients in visibly different ways.
 *
 * The `action` slot is where a section's own button goes — "add an
 * ingredient", "add a step" — sitting on the title's baseline at the right
 * rather than as a full-width button below the list.
 */
defineProps({
  icon: { type: String, required: true },
  title: { type: String, required: true },
})
</script>

<template>
  <div class="d-flex align-center ga-2 mb-4">
    <v-icon :icon="icon" size="20" class="text-primary" />
    <!-- flex-none: the divider next to it grows, and without this a
         two-word title ("Quand ?") is squeezed onto two lines. -->
    <span class="text-subtitle-1 font-weight-bold flex-none text-no-wrap">{{ title }}</span>
    <v-divider class="flex-grow-1 mx-3" />
    <slot name="action" />
  </div>
</template>
