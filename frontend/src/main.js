import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify'
import { installUnauthorizedHandler } from './stores/auth'
import './styles.css'

const app = createApp(App)

// Pinia before the router: the navigation guard calls useAuthStore(), so the
// store has to be installed before the first navigation is resolved.
app.use(createPinia())
installUnauthorizedHandler(router)
app.use(router).use(vuetify).mount('#app')
