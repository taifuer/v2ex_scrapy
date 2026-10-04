<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"
import { ArrowUp } from "@lucide/vue"

const visible = ref(false)
const fullscreen = ref(false)
const contentOffset = ref(0)
let frame = 0
let layoutObserver: ResizeObserver | undefined

function updatePosition() {
  frame = 0
  visible.value = window.scrollY > window.innerHeight
  const content = document.querySelector(".dashboard-shell > .view-section")
  const bottom = content?.getBoundingClientRect().bottom
  contentOffset.value = bottom === undefined ? 0 : Math.max(0, window.innerHeight - bottom)
}

function schedulePosition() {
  if (!frame) frame = requestAnimationFrame(updatePosition)
}

function updateFullscreen() { fullscreen.value = Boolean(document.fullscreenElement) }

function backToTop() {
  document.getElementById("dashboard-main")?.focus({ preventScroll: true })
  window.scrollTo({
    top: 0,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  })
}

onMounted(() => {
  updatePosition()
  updateFullscreen()
  layoutObserver = new ResizeObserver(schedulePosition)
  layoutObserver.observe(document.body)
  const main = document.getElementById("dashboard-main")
  if (main) layoutObserver.observe(main)
  window.addEventListener("scroll", schedulePosition, { passive: true })
  window.addEventListener("resize", schedulePosition)
  document.addEventListener("fullscreenchange", updateFullscreen)
})

onBeforeUnmount(() => {
  layoutObserver?.disconnect()
  window.removeEventListener("scroll", schedulePosition)
  window.removeEventListener("resize", schedulePosition)
  document.removeEventListener("fullscreenchange", updateFullscreen)
  cancelAnimationFrame(frame)
})
</script>

<template>
  <Teleport to="body">
    <button
      v-show="visible && !fullscreen"
      class="icon-button back-to-top-button"
      :style="{ '--content-offset': `${contentOffset}px` }"
      type="button"
      aria-label="返回顶部"
      @click="backToTop"
    >
      <ArrowUp :size="20" aria-hidden="true" />
      <span class="back-to-top-tooltip" aria-hidden="true">返回顶部</span>
    </button>
  </Teleport>
</template>

<style scoped>
.back-to-top-button { position: fixed; right: max(8px, calc((100vw - 1620px) / 2)); bottom: max(calc(48px + env(safe-area-inset-bottom, 0px)), calc(var(--content-offset, 0px) + 24px)); z-index: 25; width: 40px; height: 40px; box-shadow: var(--shadow-sm); }
.back-to-top-tooltip { position: absolute; right: calc(100% + 8px); top: 50%; transform: translateY(-50%); padding: 6px 9px; border: 1px solid var(--line); border-radius: 5px; background: #fff; color: var(--ink); font-size: 12px; white-space: nowrap; box-shadow: var(--shadow-sm); opacity: 0; pointer-events: none; }
.back-to-top-button:focus-visible .back-to-top-tooltip { opacity: 1; }
@media (hover: hover) { .back-to-top-button:hover .back-to-top-tooltip { opacity: 1; } }
:global(body.dialog-open .back-to-top-button) { display: none; }
@media (max-width: 680px) {
  .back-to-top-button { right: max(8px, env(safe-area-inset-right, 0px)); width: 44px; height: 44px; }
}
</style>
