import { createRouter, createWebHistory } from 'vue-router'

import RecipesView from '@/views/RecipesView.vue'
import PlaceholderView from '@/views/PlaceholderView.vue'
import PlannerView from '@/views/PlannerView.vue'
import EventDetailView from '@/views/EventDetailView.vue'
import GroceriesView from '@/views/GroceriesView.vue'
import GroceryListView from '@/views/GroceryListView.vue'
import LoginView from '@/views/LoginView.vue'
import JoinView from '@/views/JoinView.vue'
import ProfileView from '@/views/ProfileView.vue'
import UserProfileView from '@/views/UserProfileView.vue'
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
    path: '/planner/:id',
    name: 'event',
    component: EventDetailView,
    props: true,
    meta: { title: 'Événement', nav: 'planner', detail: true },
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
    // `guestOnly`, not merely public: signing in has nowhere to send someone
    // who is already signed in.
    component: LoginView,
    meta: { title: 'Connexion', public: true, guestOnly: true, bare: true },
  },
  {
    path: '/groceries',
    name: 'groceries',
    component: GroceriesView,
    meta: { title: 'Liste de courses', nav: 'groceries' },
  },
  {
    // The shared shopping list. Public on purpose: whoever is at the shop may
    // have no account, and `publicShell` drops the app chrome for them while
    // keeping it for a member who followed the link from inside the app.
    path: '/courses/:code',
    name: 'grocery',
    component: GroceryListView,
    props: true,
    meta: {
      title: 'Liste de courses',
      nav: 'groceries',
      detail: true,
      public: true,
      publicShell: true,
    },
  },
  {
    path: '/profile',
    name: 'profile',
    component: ProfileView,
    meta: { title: 'Mon profil', detail: true },
  },
  {
    // Someone else's page, reached from an event's member list.
    path: '/users/:id',
    name: 'user',
    component: UserProfileView,
    props: true,
    meta: { title: 'Profil', detail: true },
  },
  {
    // Reached from the profile side panel, not the bottom/drawer navigation.
    path: '/friends',
    name: 'friends',
    component: PlaceholderView,
    meta: {
      title: 'Mes amis',
      icon: 'mdi-account-group-outline',
      blurb: 'Retrouvez vos amis et partagez vos recettes.',
    },
  },
  {
    path: '/settings',
    name: 'settings',
    component: PlaceholderView,
    meta: {
      title: 'Paramètres',
      icon: 'mdi-cog-outline',
      blurb: 'Réglages du compte et de l’application.',
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
 * Gate every route but the public ones.
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
  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { path: '/' }
  }
  return true
})

export default router
