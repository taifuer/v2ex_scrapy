<script setup lang="ts">
import { nextTick, ref, watch } from "vue"

type SubtabItem = { id: string; label: string }
type SubtabGroup = { id: string; label?: string; items: SubtabItem[] }

const props = defineProps<{
  active: string
  groups: SubtabGroup[]
  label: string
}>()

const emit = defineEmits<{ select: [id: string] }>()
const nav = ref<HTMLElement | null>(null)

function revealActive() {
  nextTick(() => {
    const button = nav.value?.querySelector<HTMLElement>("[aria-selected='true']")
    button?.scrollIntoView({ block: "nearest", inline: "center" })
  })
}

watch(() => props.active, revealActive, { immediate: true })
</script>

<template>
  <nav ref="nav" class="subtab-list grouped-subtab-list" :aria-label="label" role="tablist">
    <div v-for="group in groups" :key="group.id" class="subtab-group">
      <span v-if="group.label" class="subtab-group-label" aria-hidden="true">{{ group.label }}</span>
      <button
        v-for="item in group.items"
        :key="item.id"
        type="button"
        role="tab"
        :class="{ active: active === item.id }"
        :aria-label="group.label ? `${group.label}${item.label}` : item.label"
        :aria-selected="active === item.id"
        @click="emit('select', item.id)"
      >{{ item.label }}</button>
    </div>
  </nav>
</template>
