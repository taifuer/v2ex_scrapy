<script setup lang="ts">
import { nextTick, ref, watch } from "vue"

type SubtabItem = { id: string; label: string }

const props = defineProps<{
  active: string
  items: SubtabItem[]
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
  <nav ref="nav" class="subtab-list" :aria-label="label" role="tablist">
    <button
      v-for="item in items"
      :key="item.id"
      type="button"
      role="tab"
      :class="{ active: active === item.id }"
      :aria-selected="active === item.id"
      @click="emit('select', item.id)"
    >{{ item.label }}</button>
  </nav>
</template>
