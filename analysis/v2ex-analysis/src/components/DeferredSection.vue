<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue"

withDefaults(defineProps<{ as?: string }>(), { as: "section" })
const emit = defineEmits<{ visible: [] }>()
const element = ref<HTMLElement | null>(null)
const visible = ref(false)
let observer: IntersectionObserver | undefined

function reveal() {
  if (visible.value) return
  visible.value = true
  observer?.disconnect()
  void nextTick(() => { if (element.value?.isConnected) emit("visible") })
}

onMounted(() => {
  if (!("IntersectionObserver" in window)) return reveal()
  observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) reveal()
  }, { rootMargin: "240px 0px" })
  if (element.value) observer.observe(element.value)
})
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <component :is="as" ref="element" :data-visible="visible">
    <slot :visible="visible" />
  </component>
</template>
