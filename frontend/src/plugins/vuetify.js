import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'

import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'

// Muted, paper-like palette with thin outlines, matching the mockups.
const everymealLight = {
  dark: false,
  colors: {
    background: '#f4f3ee',
    surface: '#ffffff',
    'surface-variant': '#ececec',
    primary: '#2f2f2f',
    secondary: '#8a8a8a',
    accent: '#1a56db',
    info: '#1a56db',
    success: '#2e7d5b',
    warning: '#b26a00',
    error: '#c0392b',
    'on-background': '#2f2f2f',
    'on-surface': '#2f2f2f',
    'on-primary': '#ffffff',
  },
}

export default createVuetify({
  theme: {
    defaultTheme: 'everymealLight',
    themes: { everymealLight },
  },
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  defaults: {
    VCard: { rounded: 'lg' },
    VBtn: { rounded: 'lg', variant: 'outlined', class: 'text-none' },
    VTextField: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
    VTextarea: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
    VSelect: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
    VChip: { rounded: 'lg' },
  },
})
