<script setup>
import { computed } from 'vue'

import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'

/**
 * "Who is doing this?" — one control, four places.
 *
 * The day roster and each dish on the planner, then each line and each
 * heading of the shopping list. All four are the same question about the same
 * people, so they get the same widget: a row of faces that opens a list of
 * members to tick.
 *
 * It never fetches anything. The members come from the event (or, on the
 * shared shopping page, from the list itself), which is what lets it work for
 * a visitor with no account — read-only, since `readonly` is what that page
 * passes.
 */
const props = defineProps({
  members: { type: Array, default: () => [] },
  modelValue: { type: Array, default: () => [] },
  size: { type: [Number, String], default: 22 },
  /** Shown at the top of the menu. */
  label: { type: String, default: 'Qui s’en occupe ?' },
  /** What the empty state offers, when there is room to say it. */
  placeholder: { type: String, default: '' },
  readonly: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const auth = useAuthStore()

const assigned = computed(() =>
  props.modelValue
    .map((id) => props.members.find((member) => member.id === id))
    .filter(Boolean),
)

/**
 * You first, then everyone else in the event's own order.
 *
 * Assigning yourself is by far the most common of the two — "I'll get the
 * bread" — and it should not mean hunting for your own name in a list.
 */
const ordered = computed(() => {
  const me = auth.user?.id
  return [...props.members].sort((a, b) => (a.id === me ? -1 : b.id === me ? 1 : 0))
})

const isOn = (id) => props.modelValue.includes(id)

function toggle(id) {
  emit(
    'update:modelValue',
    isOn(id) ? props.modelValue.filter((value) => value !== id) : [...props.modelValue, id],
  )
}
</script>

<template>
  <!-- Read-only: the faces, and nothing to press. -->
  <div v-if="readonly" class="d-flex align-center ga-1">
    <UserAvatar
      v-for="member in assigned"
      :key="member.id"
      :seed="member.avatar_seed"
      :size="size"
      :title="member.display_name"
    />
  </div>

  <v-menu v-else :close-on-content-click="false" location="bottom end">
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        variant="text"
        size="small"
        density="comfortable"
        class="pp-assign-btn px-1"
        :aria-label="label"
        @click.stop
      >
        <div v-if="assigned.length" class="d-flex align-center ga-1">
          <UserAvatar
            v-for="member in assigned"
            :key="member.id"
            :seed="member.avatar_seed"
            :size="size"
          />
          <span v-if="placeholder" class="text-caption ms-1">
            {{ assigned.map((m) => m.display_name).join(', ') }}
          </span>
        </div>
        <div v-else class="d-flex align-center ga-1 em-muted">
          <v-icon icon="mdi-account-plus-outline" :size="Number(size) - 2" />
          <span v-if="placeholder" class="text-caption">{{ placeholder }}</span>
        </div>
      </v-btn>
    </template>

    <v-list density="compact" min-width="220">
      <v-list-subheader>{{ label }}</v-list-subheader>
      <v-list-item
        v-for="member in ordered"
        :key="member.id"
        :active="isOn(member.id)"
        @click="toggle(member.id)"
      >
        <template #prepend>
          <v-checkbox-btn
            :model-value="isOn(member.id)"
            density="compact"
            color="primary"
            @click.stop="toggle(member.id)"
          />
          <UserAvatar :seed="member.avatar_seed" :size="22" class="me-2" />
        </template>
        <v-list-item-title class="text-body-2">
          {{ member.display_name }}
          <span v-if="member.id === auth.user?.id" class="em-muted">(moi)</span>
        </v-list-item-title>
      </v-list-item>

      <template v-if="modelValue.length">
        <v-divider class="my-1" />
        <v-list-item
          prepend-icon="mdi-account-off-outline"
          title="Personne"
          @click="emit('update:modelValue', [])"
        />
      </template>
    </v-list>
  </v-menu>
</template>

<style scoped>
/* Vuetify's minimum button width leaves a lone avatar swimming in padding. */
.pp-assign-btn {
  min-width: 0;
}
</style>
