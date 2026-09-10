<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { storeToRefs } from "pinia";

import { ApiError } from "@/api/client";
import MemberAssign from "@/components/MemberAssign.vue";
import SectionHeader from "@/components/SectionHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { groceryLink, groupItems, useGroceryStore } from "@/stores/grocery";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const grocery = useGroceryStore();
const { shared, loading, busy } = storeToRefs(grocery);

/** 'aisle' walks the shop; 'recipe' checks nothing has been forgotten. */
const mode = ref("aisle");
const error = ref("");
const copied = ref(false);
const shareCopied = ref(false);

const code = computed(() => route.params.code);
const items = computed(() => shared.value?.items ?? []);

const groups = computed(() => groupItems(items.value, mode.value));

/**
 * The event's members, carried on the list itself.
 *
 * The shared page has no session and no event, so this is the only way a
 * visitor at the shop can see that the cheese is Marie's job. Changing that
 * is another matter: it needs an account and a membership, hence `canAssign`.
 */
const members = computed(() => shared.value?.members ?? []);
const canAssign = computed(
  () =>
    auth.isAuthenticated &&
    members.value.some((member) => member.id === auth.user?.id),
);

/** Everyone assigned to *every* line of a group — what the heading can show. */
function commonAssignees(group) {
  const lists = group.items.map((item) => item.assignees ?? []);
  if (!lists.length) return [];
  return lists[0].filter((id) => lists.every((list) => list.includes(id)));
}

function assignItems(keys, assignees) {
  if (!shared.value) return;
  grocery.assign(shared.value.event_id, [...new Set(keys)], assignees);
}

const progress = computed(() => {
  const total = items.value.length;
  const done = items.value.filter((item) => item.checked).length;
  return { total, done, percent: total ? Math.round((done / total) * 100) : 0 };
});

const priceLabel = (value) =>
  value === null || value === undefined
    ? ""
    : `${value.toFixed(2).replace(".", ",")} €`;

// The server stores one unit per family — grams, millilitres — so that two
// lines can be added up at all. Nobody shops for 1500 g of flour, so the jump
// back to the bigger unit happens here, where it changes nothing but the text.
const BIGGER_UNIT = { g: ["kg", 1000], ml: ["l", 1000] };

const formatNumber = (value) => {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded)
    ? String(rounded)
    : String(rounded).replace(".", ",");
};

const quantityLabel = (item) => {
  if (item.quantity === null || item.quantity === undefined)
    return item.unit || "";

  const bigger = BIGGER_UNIT[item.unit];
  if (bigger && Math.abs(item.quantity) >= bigger[1]) {
    return `${formatNumber(item.quantity / bigger[1])} ${bigger[0]}`;
  }
  return `${formatNumber(item.quantity)} ${item.unit}`.trim();
};

const assigneeNames = (item) =>
  (item.assignees ?? [])
    .map((id) => members.value.find((member) => member.id === id)?.display_name)
    .filter(Boolean);

watch(
  code,
  async (value) => {
    if (!value) return;
    error.value = "";
    try {
      await grocery.openShared(value);
    } catch (err) {
      error.value =
        err instanceof ApiError && err.status === 404
          ? "Cette liste de courses n’existe plus."
          : "Impossible de charger cette liste.";
    }
  },
  { immediate: true },
);

// The socket is per-page: leaving it open after navigating away would keep a
// connection per list the user has ever glanced at.
onBeforeUnmount(() => grocery.stopShared());

function toggle(item) {
  grocery.toggleItem(code.value, item.key, !item.checked);
}
function toggleGroup(group) {
  // If all checked, uncheck, else, check all
  if (group.items.some((item) => !item.checked))
    group.items.forEach((item) =>
      grocery.toggleItem(code.value, item.key, false),
    );
  else
    group.items.forEach((item) =>
      grocery.toggleItem(code.value, item.key, true),
    );
}

function areAllChecked(group) {
  return !group.items.some((item) => !item.checked);
}

async function estimate() {
  if (!shared.value) return;
  try {
    await grocery.estimatePrices(shared.value.event_id);
  } catch {
    // The store raised the toast.
  }
}

async function regenerate() {
  if (!shared.value) return;
  try {
    await grocery.generate(shared.value.event_id);
  } catch {
    // Already reported.
  }
}

/** The whole list as plain text, for pasting into a message. */
function asText() {
  const lines = [shared.value?.event_name || "Liste de courses", ""];
  for (const group of groups.value) {
    lines.push(`— ${group.title} —`);
    for (const item of group.items) {
      const quantity = quantityLabel(item);
      const who = assigneeNames(item);
      lines.push(
        `${item.checked ? "[x]" : "[ ]"} ${item.name}` +
          `${quantity ? ` : ${quantity}` : ""}` +
          `${who.length ? ` (${who.join(", ")})` : ""}`,
      );
    }
    lines.push("");
  }
  if (shared.value?.total_price) {
    lines.push(`Total estimé : ${priceLabel(shared.value.total_price)}`);
  }
  return lines.join("\n");
}

async function copyText() {
  try {
    await navigator.clipboard.writeText(asText());
    copied.value = true;
    setTimeout(() => (copied.value = false), 2500);
  } catch {
    copied.value = false;
  }
}

async function share() {
  const url = groceryLink(code.value);
  if (navigator.share) {
    try {
      await navigator.share({ title: shared.value?.event_name, url });
      return;
    } catch {
      // Cancelled, or unavailable despite the feature check: fall through.
    }
  }
  try {
    await navigator.clipboard.writeText(url);
    shareCopied.value = true;
    setTimeout(() => (shareCopied.value = false), 2500);
  } catch {
    shareCopied.value = false;
  }
}
</script>

<template>
  <div class="em-page d-flex flex-column fill-height">
    <div class="em-scroll flex-grow-1">
      <v-container class="pa-4" style="max-width: 720px">
        <div class="d-flex align-center ga-2 mb-3">
          <v-btn
            v-if="auth.isAuthenticated"
            variant="text"
            size="small"
            prepend-icon="mdi-arrow-left"
            @click="router.back()"
          >
            retour
          </v-btn>
          <v-spacer />
          <v-btn
            variant="text"
            size="small"
            :prepend-icon="
              shareCopied ? 'mdi-check' : 'mdi-share-variant-outline'
            "
            @click="share"
          >
            {{ shareCopied ? "Lien copié" : "Partager" }}
          </v-btn>
          <v-btn
            variant="text"
            size="small"
            :prepend-icon="copied ? 'mdi-check' : 'mdi-content-copy'"
            @click="copyText"
          >
            {{ copied ? "Copié" : "Copier" }}
          </v-btn>
        </div>

        <v-skeleton-loader v-if="loading && !shared" type="article" />

        <div v-else-if="error" class="text-center em-muted py-12">
          <v-icon icon="mdi-cart-off" size="48" class="mb-4" />
          <p class="text-body-2">{{ error }}</p>
        </div>

        <template v-else-if="shared">
          <h2 class="text-h6 font-weight-medium mb-1">
            {{ shared.event_name }}
          </h2>
          <p class="text-body-2 em-muted mb-3">
            {{ progress.done }} / {{ progress.total }} articles
            <template v-if="shared.total_price">
              · <strong>{{ priceLabel(shared.total_price) }}</strong> estimés
            </template>
          </p>

          <v-progress-linear
            :model-value="progress.percent"
            color="success"
            height="8"
            rounded
            class="mb-4"
          />

          <div class="d-flex align-center flex-wrap ga-2 mb-5">
            <v-btn-toggle
              v-model="mode"
              density="compact"
              mandatory
              variant="outlined"
            >
              <v-btn value="aisle" size="small">Par rayon</v-btn>
              <v-btn value="recipe" size="small">Par recette</v-btn>
            </v-btn-toggle>
            <v-spacer />
            <!-- Both need the event behind the list, so they are only offered
                 to someone signed in as one of its members. -->
            <template v-if="auth.isAuthenticated">
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-refresh"
                :loading="busy"
                @click="regenerate"
              >
                Régénérer
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                prepend-icon="mdi-currency-eur"
                :loading="busy"
                @click="estimate"
              >
                Estimer les prix
              </v-btn>
            </template>
          </div>

          <div v-if="!items.length" class="text-center em-muted py-10">
            <v-icon icon="mdi-cart-outline" size="40" class="mb-3" />
            <p class="text-body-2">
              Rien à acheter pour l’instant — planifiez des repas puis régénérez
              la liste.
            </p>
          </div>

          <div v-for="group in groups" :key="group.key" class="mb-5">
            <SectionHeader icon="mdi-tag-outline" :title="group.title">
              <template #prepend>
                <!-- Assigning a heading assigns everything under it: one press
                     for a whole rayon, or for everything a recipe needs. -->
                <v-checkbox-btn
                  :model-value="areAllChecked(group)"
                  density="compact"
                  color="success"
                  @click.stop="toggleGroup(group)"
                />
                <MemberAssign
                  :members="members"
                  :model-value="commonAssignees(group)"
                  :readonly="!canAssign"
                  :label="
                    mode === 'recipe'
                      ? `Qui s’occupe de ${group.title} ?`
                      : `Qui s’occupe du rayon ${group.title} ?`
                  "
                  @update:model-value="
                    assignItems(
                      group.items.map((item) => item.key),
                      $event,
                    )
                  "
                />
              </template>
            </SectionHeader>
            <v-list class="pa-0 bg-transparent">
              <v-list-item
                v-for="(item, index) in group.items"
                :key="`${item.key}-${index}`"
                class="px-0"
                @click="toggle(item)"
              >
                <template #prepend>
                  <div class="d-flex align-center pr-3">
                    <v-checkbox-btn
                      :model-value="item.checked"
                      density="compact"
                      color="success"
                      @click.stop="toggle(item)"
                    />
                    <MemberAssign
                      :members="members"
                      :model-value="item.assignees ?? []"
                      :readonly="!canAssign"
                      :label="`Qui prend ${item.name} ?`"
                      @update:model-value="assignItems([item.key], $event)"
                    />
                  </div>
                </template>
                <v-list-item-title
                  class="text-body-2"
                  :class="item.checked ? 'pp-done' : ''"
                >
                  {{ item.name }}
                </v-list-item-title>
                <template #append>
                  <div class="text-end">
                    <div class="text-body-2 em-mono">
                      {{ quantityLabel(item) }}
                    </div>
                    <div
                      v-if="item.price !== null"
                      class="text-caption em-muted em-mono"
                    >
                      {{ priceLabel(item.price) }}
                    </div>
                  </div>
                </template>
              </v-list-item>
            </v-list>
          </div>
        </template>
      </v-container>
    </div>
  </div>
</template>

<style scoped>
.pp-done {
  text-decoration: line-through;
  color: var(--em-muted);
}
</style>
