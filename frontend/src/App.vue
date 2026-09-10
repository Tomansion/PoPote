<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { storeToRefs } from "pinia";
import { useDisplay } from "vuetify";

import AppLogo from "@/components/AppLogo.vue";
import IntroSplash from "@/components/IntroSplash.vue";
import ProfileAvatarButton from "@/components/ProfileAvatarButton.vue";
import ProfilePanel from "@/components/ProfilePanel.vue";
import { useAuthStore } from "@/stores/auth";
import { useEventsStore } from "@/stores/events";
import { useGroceryStore } from "@/stores/grocery";
import { usePlanStore } from "@/stores/plan";
import { useRecipesStore } from "@/stores/recipes";

const route = useRoute();
const router = useRouter();
const { mdAndUp } = useDisplay();

const store = useRecipesStore();
const auth = useAuthStore();
const events = useEventsStore();
const plan = usePlanStore();
const grocery = useGroceryStore();
const { toast } = storeToRefs(store);
const { toast: eventToast } = storeToRefs(events);
const { toast: planToast } = storeToRefs(plan);
const { toast: groceryToast } = storeToRefs(grocery);

const snackbar = ref(false);
const activeToast = ref(null);
const profileOpen = ref(false);

// Every store raises toasts; whichever fired last wins the one snackbar.
watch([toast, eventToast, planToast, groceryToast], () => {
  const latest = [
    toast.value,
    eventToast.value,
    planToast.value,
    groceryToast.value,
  ]
    .filter(Boolean)
    .sort((a, b) => b.at - a.at)[0];
  if (latest && latest !== activeToast.value) {
    activeToast.value = latest;
    snackbar.value = true;
  }
});

/**
 * Screens that render on their own, with no nav, bars or drawer.
 *
 * The login screen always. The shared shopping list only for a visitor with
 * no account: a member who followed the link from inside the app should keep
 * the navigation they arrived with.
 */
const isBare = computed(
  () =>
    Boolean(route.meta.bare) ||
    (route.meta.publicShell && !auth.isAuthenticated),
);

const NAV_ITEMS = [
  { key: "recipes", title: "Recettes", to: "/", icon: "mdi-notebook-outline" },
  {
    key: "planner",
    title: "Planificateur",
    to: "/planner",
    icon: "mdi-calendar-month-outline",
  },
  {
    key: "groceries",
    title: "Liste de courses",
    to: "/groceries",
    icon: "mdi-cart-outline",
  },
];

const activeNav = computed(() => route.meta.nav ?? "recipes");

// The detail screen supplies its own "← retour" header, so the global app bar
// would be a duplicate there — true at every width now that the recipe list
// and its detail page share the same layout on mobile and desktop.
const showAppBar = computed(() => !route.meta.detail);

// Plays once per app start, on the web and in the APK alike. Skipped outright
// for anyone who asked the system for less motion.
const showIntro = ref(
  !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches,
);

// The store loads behind the intro, so the recipes are already there when it
// fades out. Nothing is loaded until there is a session to load it for: the
// feed needs a token, and the recipes it returns are this user's.
onMounted(async () => {
  await auth.restore();
  if (auth.isAuthenticated) store.init();
});

// Signing in starts the feed; signing out tears it down and empties the stores,
// so no trace of the previous account is left on screen.
watch(
  () => auth.isAuthenticated,
  (signedIn, wasSignedIn) => {
    if (signedIn && !wasSignedIn) store.init();
    else if (!signedIn && wasSignedIn) store.reset();
  },
);

onBeforeUnmount(() => store.stop());
</script>

<template>
  <IntroSplash v-if="showIntro" @done="showIntro = false" />

  <v-app>
    <!-- The login screen gets the bare app shell: no nav, no bars. -->
    <v-main v-if="isBare">
      <router-view />
    </v-main>

    <template v-else>
      <!-- The panel lives at the top level of the shell, not nested inside the
         app bar or the permanent drawer below — both apply their own CSS
         transform, which would break this drawer's full-screen overlay. -->
      <ProfilePanel v-model="profileOpen" />

      <!-- ============ Desktop: permanent navigation drawer ============ -->
      <v-navigation-drawer
        v-if="mdAndUp"
        permanent
        width="240"
        color="background"
        border="0"
        class="em-outline"
      >
        <div class="pa-4">
          <!-- The logo is the way home, the way it is on every site: it sits
               where "back to the start" is looked for, and nothing else in
               the drawer says "Recettes" from inside a recipe. -->
          <button
            type="button"
            class="d-flex align-center ga-3 mb-6 ps-1 pp-home"
            aria-label="Accueil — mes recettes"
            @click="router.push('/')"
          >
            <AppLogo :size="36" />
            <div class="text-subtitle-1 font-weight-medium">Po'Pote</div>
          </button>

          <v-list density="compact" nav class="pa-0">
            <v-list-item
              v-for="item in NAV_ITEMS"
              :key="item.key"
              :title="item.title"
              :active="activeNav === item.key"
              rounded="lg"
              @click="router.push(item.to)"
            />
          </v-list>
        </div>
      </v-navigation-drawer>

      <!-- ============ Top bar: avatar on the left, centred title — same at every width ============ -->
      <v-app-bar v-if="showAppBar" flat color="background">
        <!-- Only where the drawer is not already showing one. -->
        <template #prepend>
          <ProfileAvatarButton
            :size="32"
            show-name
            @click="profileOpen = true"
          />
          <button
            v-if="!mdAndUp"
            type="button"
            class="ps-2 d-flex align-center pp-home"
            aria-label="Accueil — mes recettes"
            @click="router.push('/')"
          >
            <AppLogo :size="28" />
          </button>
        </template>
        <v-app-bar-title class="text-center text-subtitle-1">
          {{ route.meta.title }}
        </v-app-bar-title>
      </v-app-bar>

      <v-main>
        <router-view />
      </v-main>

      <!-- ============ Mobile bottom navigation ============ -->
      <v-bottom-navigation
        v-if="!mdAndUp"
        :model-value="activeNav"
        color="primary"
        grow
        height="56"
        class="em-outline"
      >
        <v-btn
          v-for="item in NAV_ITEMS"
          :key="item.key"
          :value="item.key"
          variant="text"
          @click="router.push(item.to)"
        >
          <v-icon :icon="item.icon" size="20" />
          <span class="text-caption">{{ item.title }}</span>
        </v-btn>
      </v-bottom-navigation>

      <v-snackbar
        v-model="snackbar"
        :color="activeToast?.color ?? 'error'"
        timeout="3500"
        location="bottom"
      >
        {{ activeToast?.message }}
      </v-snackbar>
    </template>
  </v-app>
</template>

<style scoped>
/* A button that has to look exactly like the logo it wraps. */
.pp-home {
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  color: inherit;
  text-align: start;
}

.pp-home:hover {
  opacity: 0.75;
}
</style>
