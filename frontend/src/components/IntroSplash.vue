<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

// Kept in sync with the CSS transition below; the overlay is only unmounted
// once the fade has actually finished.
const FADE_MS = 320

// The intro is decoration: if anything at all goes wrong (a codec the WebView
// refuses, autoplay denied, a stalled network) the app must not stay hidden
// behind it. Every failure path calls dismiss(), and this is the backstop for
// the ones that report nothing at all.
const FAILSAFE_MS = 8000

const emit = defineEmits(['done'])

const videoEl = ref(null)
const leaving = ref(false)
let failsafeId = null
let fadeId = null

const src = `${import.meta.env.BASE_URL}intro.mp4`

function dismiss() {
  if (leaving.value) return
  leaving.value = true
  clearTimeout(failsafeId)
  window.removeEventListener('keydown', onKeydown)
  fadeId = setTimeout(() => emit('done'), FADE_MS)
}

function onKeydown() {
  dismiss()
}

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  failsafeId = setTimeout(dismiss, FAILSAFE_MS)

  const el = videoEl.value
  if (!el) return dismiss()

  // Set as a property, not just an attribute: Vue does not reflect `muted` onto
  // the element, and both Chrome and the Android WebView reject autoplay of a
  // clip that carries an audio track unless it is muted at play() time.
  el.muted = true
  try {
    await el.play()
  } catch {
    dismiss()
  }
})

onBeforeUnmount(() => {
  clearTimeout(failsafeId)
  clearTimeout(fadeId)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <div
      class="intro"
      :class="{ 'intro--leaving': leaving }"
      @click="dismiss"
    >
      <video
        ref="videoEl"
        class="intro__video"
        :src="src"
        muted
        playsinline
        autoplay
        preload="auto"
        disablepictureinpicture
        @ended="dismiss"
        @error="dismiss"
      />
      <button type="button" class="intro__skip" @click.stop="dismiss">Passer</button>
    </div>
  </Teleport>
</template>

<style scoped>
.intro {
  position: fixed;
  inset: 0;
  /* Sampled from the clip itself, so the letterbox bars left by object-fit:
     contain are indistinguishable from the video. */
  background: #062f41;
  /* Above Vuetify's overlays, which top out in the 2400s. */
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 1;
  transition: opacity 320ms ease-out;
}

.intro--leaving {
  opacity: 0;
  /* The app underneath is already interactive; do not swallow taps aimed at it
     during the fade. */
  pointer-events: none;
}

.intro__video {
  width: 100%;
  height: 70%;
  object-fit: contain;
}

.intro__skip {
  position: absolute;
  right: calc(16px + env(safe-area-inset-right, 0px));
  bottom: calc(20px + var(--em-safe-bottom));
  padding: 8px 18px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  border-radius: 999px;
  background: transparent;
  color: rgba(255, 255, 255, 0.85);
  font: inherit;
  font-size: 0.875rem;
  cursor: pointer;
}

.intro__skip:hover {
  border-color: rgba(255, 255, 255, 0.8);
  color: #fff;
}
</style>
