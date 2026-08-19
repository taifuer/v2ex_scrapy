<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

type SubtabItem = { id: string; label: string }
type SubtabGroup = { id: string; label?: string; items: SubtabItem[] }

const props = defineProps<{
  active: string
  groups: SubtabGroup[]
  label: string
}>()

const emit = defineEmits<{ select: [id: string] }>()
const nav = ref<HTMLElement | null>(null)
const canScrollLeft = ref(false)
const canScrollRight = ref(false)

function updateScrollEdges() {
  const element = nav.value
  if (!element) return
  canScrollLeft.value = element.scrollLeft > 2
  canScrollRight.value = element.scrollLeft + element.clientWidth < element.scrollWidth - 2
}

function revealActive() {
  nextTick(() => {
    const button = nav.value?.querySelector<HTMLElement>("[aria-selected='true']")
    button?.scrollIntoView({ block: "nearest", inline: "nearest" })
    requestAnimationFrame(updateScrollEdges)
  })
}

watch(() => props.active, revealActive, { immediate: true })
onMounted(() => {
  nav.value?.addEventListener("scroll", updateScrollEdges, { passive: true })
  window.addEventListener("resize", updateScrollEdges)
  updateScrollEdges()
})
onBeforeUnmount(() => {
  nav.value?.removeEventListener("scroll", updateScrollEdges)
  window.removeEventListener("resize", updateScrollEdges)
})
</script>

<template>
  <div class="subtab-scroll-shell" :class="{ 'can-scroll-left': canScrollLeft, 'can-scroll-right': canScrollRight }">
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
  </div>
</template>
