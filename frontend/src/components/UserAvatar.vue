<script setup>
import { computed } from 'vue'
import { Avatar, Style } from '@dicebear/core'
import definition from '@dicebear/styles/thumbs.json'

/**
 * Deterministic avatar, generated from a number.
 *
 * The seed is the only thing stored on the account — never an image — so an
 * avatar costs 4 bytes in the database and renders identically on the web and
 * in the APK. DiceBear emits a self-contained inline SVG, so nothing is
 * fetched at runtime and it works offline.
 *
 * The style definition is parsed once at module load rather than per
 * component: it is the same 12 KB JSON for every avatar on screen.
 */
const style = new Style(definition)

const props = defineProps({
  seed: { type: [Number, String], default: 0 },
  size: { type: [Number, String], default: 40 },
})

const svg = computed(() =>
  new Avatar(style, { seed: String(props.seed) }).toString(),
)
</script>

<template>
  <!-- v-html is safe here: the markup is generated locally by DiceBear from a
       number, never supplied by a user or fetched from the network. -->
  <div
    class="pp-avatar"
    :style="{ width: `${size}px`, height: `${size}px` }"
    v-html="svg"
  />
</template>

<style scoped>
.pp-avatar {
  border-radius: 50%;
  overflow: hidden;
  flex: none;
  line-height: 0;
}
.pp-avatar :deep(svg) {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
