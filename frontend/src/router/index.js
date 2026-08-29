import { createRouter, createWebHistory } from 'vue-router'

import RecipesView from '@/views/RecipesView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'

const routes = [
  {
    path: '/',
    name: 'recipes',
    component: RecipesView,
    meta: { title: 'Recettes', nav: 'recipes' },
  },
  {
    // Same view as the list: on desktop it fills the right-hand panel, on
    // mobile it takes over the screen. Being a real route means Android's
    // hardware back button works inside the APK for free.
    path: '/recipes/:id',
    name: 'recipe',
    component: RecipesView,
    props: true,
    meta: { title: 'Recette', nav: 'recipes', detail: true },
  },
  {
    path: '/planner',
    name: 'planner',
    component: PlaceholderView,
    meta: {
      title: 'Planificateur',
      nav: 'planner',
      icon: 'mdi-calendar-month-outline',
      blurb: 'Planifier les repas de la semaine à partir de vos recettes.',
    },
  },
  {
    path: '/groceries',
    name: 'groceries',
    component: PlaceholderView,
    meta: {
      title: 'Liste de courses',
      nav: 'groceries',
      icon: 'mdi-cart-outline',
      blurb: 'Regrouper les ingrédients par rayon pour vos courses.',
    },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export default createRouter({
  // Capacitor serves the app from https://localhost, where history mode works.
  history: createWebHistory(),
  routes,
})
