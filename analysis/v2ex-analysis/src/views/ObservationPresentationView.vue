<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ArrowRight, ChevronLeft, ChevronRight, List, Maximize2, Minimize2, Search, X } from "@lucide/vue"
import PresentationPosts from "../components/PresentationPosts.vue"
import type { PresentationChartHandle, PresentationChartSpec } from "../presentationCharts"
import type { PresentationSlide } from "../types/presentation"

const props = defineProps<{
  observations: any
  selectedSlide: string
  nodeLabel: (node: string) => string
}>()
const emit = defineEmits<{
  openSearch: [restoreTo: HTMLElement]
  "update:selectedSlide": [value: string]
}>()

const root = ref<HTMLElement | null>(null)
const menuButton = ref<HTMLButtonElement | null>(null)
const menu = ref<HTMLElement | null>(null)
const menuOpen = ref(false)
const fullscreen = ref(false)
const chartError = ref(false)
let chart: PresentationChartHandle | null = null
let renderToken = 0
let observer: ResizeObserver | null = null
let resizeFrame = 0

const presentation = computed(() => props.observations.presentation || {})
const slides = computed<PresentationSlide[]>(() => presentation.value.slides || [])
const current = computed(() => Math.max(0, slides.value.findIndex(item => item.id === props.selectedSlide)))
const slide = computed(() => slides.value[current.value])
const charts = computed<Record<string, PresentationChartSpec>>(() => presentation.value.charts || {})
const chapters = computed(() => [...new Set(slides.value.map(item => item.chapter))])
const counter = computed(() => `${current.value + 1} / ${slides.value.length}`)

function normalizeSelection() {
  if (slides.value.length && props.selectedSlide && (current.value === 0 || !slides.value.some(item => item.id === props.selectedSlide))) {
    emit("update:selectedSlide", "")
  }
}

async function selectPage(index: number) {
  const next = Math.max(0, Math.min(slides.value.length - 1, index))
  if (!slides.value[next]) return
  const fromMenu = menuOpen.value
  menuOpen.value = false
  emit("update:selectedSlide", next === 0 ? "" : slides.value[next].id)
  await nextTick()
  if (fromMenu) menuButton.value?.focus({ preventScroll: true })
  const rect = root.value?.getBoundingClientRect()
  if (!fullscreen.value && rect && (rect.top < 0 || window.innerWidth <= 680)) root.value?.scrollIntoView({ block: "start" })
  else if (fullscreen.value && root.value) root.value.scrollTop = 0
}

async function toggleMenu() {
  menuOpen.value = !menuOpen.value
  if (menuOpen.value) {
    await nextTick()
    menu.value?.querySelector<HTMLButtonElement>('[aria-current="page"]')?.focus()
  }
}

function handlePointer(event: PointerEvent) {
  if (menuOpen.value && !menu.value?.contains(event.target as Node) && !menuButton.value?.contains(event.target as Node)) menuOpen.value = false
}

function handleKeydown(event: KeyboardEvent) {
  const target = event.target as HTMLElement
  if (event.altKey || event.ctrlKey || event.metaKey || target.closest('input, textarea, select, [contenteditable="true"], [role="dialog"]')) return
  if (menuOpen.value) {
    if (event.key === "Escape") {
      event.preventDefault()
      menuOpen.value = false
      menuButton.value?.focus()
    }
    return
  }
  if (target !== document.body && !root.value?.contains(target)) return
  const pages: Record<string, number> = { ArrowRight: current.value + 1, PageDown: current.value + 1, ArrowLeft: current.value - 1, PageUp: current.value - 1, Home: 0, End: slides.value.length - 1 }
  const next = pages[event.key]
  if (next === undefined) return
  event.preventDefault()
  void selectPage(next)
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await root.value?.requestFullscreen()
  } catch { fullscreen.value = false }
}

function handleFullscreen() {
  fullscreen.value = document.fullscreenElement === root.value
  scheduleResize()
}

async function openSearch(event: MouseEvent) {
  const target = event.currentTarget as HTMLElement
  if (document.fullscreenElement) await document.exitFullscreen()
  emit("openSearch", target)
}

function scheduleResize() {
  cancelAnimationFrame(resizeFrame)
  resizeFrame = requestAnimationFrame(() => chart?.resize())
}

async function renderCurrentChart() {
  const token = ++renderToken
  chart?.dispose()
  chart = null
  chartError.value = false
  await nextTick()
  const element = root.value?.querySelector<HTMLElement>("[data-deck-chart]")
  const key = slide.value?.chart
  if (!element || !key || !charts.value[key]) return
  try {
    const runtime = await import("../presentationCharts")
    if (token !== renderToken || !element.isConnected) return
    chart = runtime.createPresentationChart(element, charts.value[key], { nodeLabel: props.nodeLabel })
  } catch {
    if (token === renderToken) chartError.value = true
  }
}

watch([slides, () => props.selectedSlide], normalizeSelection, { immediate: true })
watch([() => slide.value?.id, charts], renderCurrentChart, { flush: "post" })

onMounted(() => {
  window.addEventListener("keydown", handleKeydown)
  document.addEventListener("pointerdown", handlePointer)
  document.addEventListener("fullscreenchange", handleFullscreen)
  observer = new ResizeObserver(scheduleResize)
  if (root.value) observer.observe(root.value)
  void renderCurrentChart()
})

onBeforeUnmount(() => {
  renderToken += 1
  chart?.dispose()
  observer?.disconnect()
  cancelAnimationFrame(resizeFrame)
  window.removeEventListener("keydown", handleKeydown)
  document.removeEventListener("pointerdown", handlePointer)
  document.removeEventListener("fullscreenchange", handleFullscreen)
})
</script>

<template>
  <section ref="root" class="view-section deck-view" aria-label="社区数据演示">
    <header class="deck-toolbar">
      <div class="deck-toolbar-title"><strong>数据演示</strong><span>持续迭代中</span></div>
      <nav class="deck-controls" aria-label="演示翻页">
        <button type="button" class="icon-button" aria-label="上一页" title="上一页" :disabled="current === 0" @click="selectPage(current - 1)"><ChevronLeft :size="20" /></button>
        <span class="deck-counter">{{ slides.length ? counter : "准备中" }}</span>
        <button type="button" class="icon-button" aria-label="下一页" title="下一页" :disabled="!slides.length || current === slides.length - 1" @click="selectPage(current + 1)"><ChevronRight :size="20" /></button>
        <button ref="menuButton" type="button" class="icon-button" aria-label="演示目录" title="演示目录" aria-controls="deck-directory" :aria-expanded="menuOpen" @click="toggleMenu"><X v-if="menuOpen" :size="18" /><List v-else :size="18" /></button>
        <button type="button" class="icon-button deck-fullscreen" :aria-label="fullscreen ? '退出全屏' : '全屏演示'" :title="fullscreen ? '退出全屏' : '全屏演示'" @click="toggleFullscreen"><Minimize2 v-if="fullscreen" :size="18" /><Maximize2 v-else :size="18" /></button>
      </nav>
      <nav v-if="menuOpen" id="deck-directory" ref="menu" class="deck-directory" aria-label="演示章节">
        <section v-for="chapter in chapters" :key="chapter">
          <h3>{{ chapter }}</h3>
          <template v-for="(item, index) in slides" :key="item.id">
            <button v-if="item.chapter === chapter" type="button" :aria-current="index === current ? 'page' : undefined" @click="selectPage(index)"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ item.title }}</button>
          </template>
        </section>
      </nav>
    </header>
    <span class="sr-only" aria-live="polite">{{ slide ? `第 ${current + 1} 页，共 ${slides.length} 页，${slide.title}` : "正在准备演示" }}</span>

    <article v-if="slide" class="deck-stage" :data-kind="slide.type" :data-slide="slide.id" aria-labelledby="deck-title">
      <header class="deck-heading">
        <div class="deck-eyebrow"><span>{{ slide.eyebrow }}</span><span>{{ String(current + 1).padStart(2, '0') }}</span></div>
        <h2 id="deck-title" :class="{ 'deck-brand': slide.type === 'cover' }"><img v-if="slide.type === 'cover'" src="/favicon.svg" alt="" />{{ slide.title }}</h2>
        <p>{{ slide.summary }}</p>
      </header>

      <dl v-if="slide.metrics?.length" class="deck-metrics" :class="{ 'deck-metrics-facts': slide.type === 'facts' || slide.type === 'cover' }">
        <div v-for="item in slide.metrics" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd><small v-if="item.detail">{{ item.detail }}</small></div>
      </dl>

      <div v-if="slide.definitions?.length" class="deck-definitions">
        <section v-for="item in slide.definitions" :key="item.title"><h3>{{ item.title }}</h3><p>{{ item.text }}</p></section>
      </div>

      <div v-else-if="slide.type === 'chart'" class="deck-visual" :class="{ 'deck-visual-with-cases': slide.posts?.length }">
        <div class="deck-chart-wrap">
          <div class="deck-chart-canvas" :class="{ 'deck-chart-multiples': charts[slide.chart || '']?.kind === 'small_multiples' }" data-deck-chart role="img" :aria-label="slide.title"></div>
          <div v-if="chartError" class="deck-chart-error" role="alert"><p>图表暂时无法加载</p><button type="button" class="text-action" @click="renderCurrentChart">重新加载</button></div>
        </div>
        <PresentationPosts v-if="slide.posts?.length" :posts="slide.posts" :node-label="props.nodeLabel" />
      </div>

      <div v-else-if="slide.type === 'timeline'" class="deck-timeline">
        <section v-for="item in slide.milestones" :key="item.period">
          <span class="deck-timeline-period">{{ item.period }}</span>
          <h3>{{ item.title }}</h3>
          <ol><li v-for="term in item.items" :key="term.label"><strong>{{ term.label }}</strong><span>{{ term.count.toLocaleString('zh-CN') }}</span></li></ol>
          <p v-if="item.text">{{ item.text }}</p>
        </section>
      </div>

      <div v-else-if="slide.type === 'posts'" class="deck-stories">
        <PresentationPosts v-if="slide.posts?.length" :posts="slide.posts" :node-label="props.nodeLabel" />
        <a v-for="comment in slide.comments" :key="comment.id" class="deck-comment" :href="comment.url" target="_blank" rel="noreferrer">
          <div><span>评论中的回应</span><blockquote>{{ comment.text }}</blockquote><p>{{ comment.note }}</p></div>
          <small>{{ comment.username }} · {{ comment.date }}<br>感谢 {{ comment.thanks.toLocaleString('zh-CN') }} · #{{ comment.topic_id }}</small>
        </a>
      </div>

      <ol v-else-if="slide.type === 'conclusion'" class="deck-takeaways">
        <li v-for="item in slide.takeaways" :key="item.number"><span>{{ item.number }}</span><div><h3>{{ item.title }}</h3><p>{{ item.text }}</p></div></li>
      </ol>

      <div v-else-if="slide.type === 'explore'" class="deck-explore">
        <button type="button" class="deck-search" aria-label="打开全站搜索" @click="openSearch"><Search :size="24" /><span>搜索看板数据</span><ArrowRight :size="20" /></button>
        <p>搜索已收录的话题、标题关键词、节点和部分活跃成员。</p>
        <div class="deck-explore-links"><a href="?tab=content&view=topics">讨论的变化<ArrowRight :size="16" /></a><a href="?tab=engagement">值得一读的帖子<ArrowRight :size="16" /></a><a href="?tab=about&about=catalog">全部收录对象<ArrowRight :size="16" /></a></div>
      </div>

      <footer v-if="slide.note" class="deck-note">{{ slide.note }}</footer>
    </article>
    <div v-else class="deck-empty" role="status">演示数据暂未准备完成。</div>

    <footer v-if="slide" class="deck-bottom"><span>{{ slide.chapter }}</span><button v-if="current < slides.length - 1" type="button" @click="selectPage(current + 1)">{{ slides[current + 1]?.eyebrow }}<ArrowRight :size="16" /></button><button v-else type="button" @click="selectPage(0)">回到开场<ArrowRight :size="16" /></button></footer>
  </section>
</template>

<style scoped src="../assets/presentation.css"></style>
