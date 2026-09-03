import { createRouter, createWebHistory } from 'vue-router'

import RecipesView from '@/views/RecipesView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'
import PlannerView from '@/views/PlannerView.vue'
import LoginView from '@/views/LoginView.vue'
import JoinView from '@/views/JoinView.vue'
import { useAuthStore } from '@/stores/auth'

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
    component: PlannerView,
    meta: { title: 'Planificateur', nav: 'planner' },
  },
  {
    // The target of a shared invite link. A real route, so opening the link
    // cold — from a message, on a phone — lands straight on the invitation.
    path: '/join/:code',
    name: 'join',
    component: JoinView,
    meta: { title: 'Invitation', nav: 'planner', detail: true },
  },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { title: 'Connexion', public: true, bare: true },
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

const router = createRouter({
  // Capacitor serves the app from https://localhost, where history mode works.
  history: createWebHistory(),
  routes,
})

/**
 * Gate every route but the login screen.
 *
 * `next` carries the route that was asked for, so following an invite link
 * while signed out sends you to the invitation after logging in, rather than
 * dumping you on the recipe list with the link lost.
 */
router.beforeEach((to) => {
  const auth = useAuthStore()

  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath === '/' ? {} : { next: to.fullPath } }
  }
  if (to.meta.public && auth.isAuthenticated) {
    return { path: '/' }
  }
  return true
})

export default router
