<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

const props = defineProps<{ items: Array<{ id: string; label: string }> }>()
const activeId = ref(props.items[0]?.id || "")
let frame = 0

function updateActiveSection() {
  frame = 0
  if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2) {
    activeId.value = props.items[props.items.length - 1]?.id || ""
    return
  }
  const marker = Math.min(window.innerHeight * 0.32, 220)
  let active = props.items[0]?.id || ""
  for (const item of props.items) {
    const section = document.getElementById(item.id)
    if (!section) continue
    if (section.getBoundingClientRect().top <= marker) active = item.id
    else break
  }
  activeId.value = active
}

function scheduleUpdate() {
  if (!frame) frame = window.requestAnimationFrame(updateActiveSection)
}

function bindSections() {
  nextTick(updateActiveSection)
}

watch(() => props.items.map(item => item.id).join("|"), bindSections)
onMounted(() => {
  window.addEventListener("scroll", scheduleUpdate, { passive: true })
  window.addEventListener("resize", scheduleUpdate)
  bindSections()
})
onBeforeUnmount(() => {
  window.removeEventListener("scroll", scheduleUpdate)
  window.removeEventListener("resize", scheduleUpdate)
  if (frame) window.cancelAnimationFrame(frame)
})
</script>

<template>
  <nav class="view-section-nav" aria-label="当前页面区域">
    <span>快速定位</span>
    <a
      v-for="item in items"
      :key="item.id"
      :href="`#${item.id}`"
      :class="{ active: activeId === item.id }"
      :aria-current="activeId === item.id ? 'location' : undefined"
      @click="activeId = item.id"
    >{{ item.label }}</a>
  </nav>
</template>
