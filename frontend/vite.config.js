import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'

// The API base URL is injected at build time via VITE_API_URL:
//   web (dev)  -> unset, falls back to "/api" and the dev proxy below
//   web (prod) -> unset, falls back to "/api" served by nginx on the same host
//   APK        -> https://everymeal.tomansion.fr/api (no same-origin to rely on)
export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 8100 rather than the usual 8000, which is already taken on this machine.
      '/api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
