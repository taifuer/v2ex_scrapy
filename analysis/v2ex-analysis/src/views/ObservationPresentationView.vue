<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ArrowRight, ChevronLeft, ChevronRight, List, Maximize2, Minimize2, Search, X } from "@lucide/vue"
import PresentationRanking from "../components/PresentationRanking.vue"
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
let chartHandles: PresentationChartHandle[] = []
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
const hasSupport = computed(() => slide.value && (slide.value.type !== "chart" || slide.value.metrics?.length || slide.value.posts?.length || slide.value.comments?.length || slide.value.findings?.length))
const hasAside = computed(() => slide.value?.type === "chart" && ((slide.value.posts?.length && !slide.value.post_layout) || slide.value.comments?.length))

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
  resizeFrame = requestAnimationFrame(() => {
    const element = root.value
    if (element && !fullscreen.value) {
      const top = element.getBoundingClientRect().top + window.scrollY
      element.style.setProperty("--deck-height", `${Math.max(0, window.innerHeight - top - 16)}px`)
    }
    chartHandles.forEach(chart => chart.resize())
  })
}

async function renderCurrentChart() {
  const token = ++renderToken
  scheduleResize()
  chartHandles.forEach(chart => chart.dispose())
  chartHandles = []
  chartError.value = false
  await nextTick()
  const elements = [...root.value?.querySelectorAll<HTMLElement>("[data-deck-chart]") || []]
  if (!elements.length) return
  try {
    const runtime = await import("../presentationCharts")
    if (token !== renderToken) return
    for (const element of elements) {
      const key = element.dataset.deckChart || slide.value?.chart
      if (key && charts.value[key] && element.isConnected) chartHandles.push(runtime.createPresentationChart(element, charts.value[key], { nodeLabel: props.nodeLabel }))
    }
  } catch {
    if (token === renderToken) chartError.value = true
  }
}

watch([slides, () => props.selectedSlide], normalizeSelection, { immediate: true })
watch(() => slide.value?.id, () => {
  root.value?.querySelectorAll(".deck-body, .deck-stage").forEach(element => { element.scrollTop = 0 })
}, { flush: "post" })
watch([() => slide.value?.id, charts], renderCurrentChart, { flush: "post" })

onMounted(() => {
  window.addEventListener("keydown", handleKeydown)
  window.addEventListener("resize", scheduleResize)
  document.addEventListener("pointerdown", handlePointer)
  document.addEventListener("fullscreenchange", handleFullscreen)
  observer = new ResizeObserver(scheduleResize)
  if (root.value) observer.observe(root.value)
  void renderCurrentChart()
})

onBeforeUnmount(() => {
  renderToken += 1
  chartHandles.forEach(chart => chart.dispose())
  observer?.disconnect()
  cancelAnimationFrame(resizeFrame)
  window.removeEventListener("keydown", handleKeydown)
  window.removeEventListener("resize", scheduleResize)
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
        <div class="deck-eyebrow"><span>{{ slide.eyebrow }}</span></div>
        <h2 id="deck-title" :class="{ 'deck-brand': slide.type === 'cover' }"><img v-if="slide.type === 'cover'" src="/favicon.svg" alt="" />{{ slide.title }}</h2>
        <p>{{ slide.summary }}</p>
      </header>

      <div class="deck-body" :class="{ 'deck-body-chart': slide.type === 'chart', 'deck-body-aside': hasAside, 'deck-body-caption': slide.type === 'chart' && hasSupport && !hasAside }">
        <div v-if="slide.type === 'chart'" class="deck-chart-wrap">
          <div class="deck-chart-canvas" data-deck-chart role="img" :aria-label="slide.title"></div>
        </div>
        <div v-if="hasSupport" class="deck-support">
          <div v-if="slide.panels?.length" class="deck-distributions" :class="{ 'deck-distributions-comparison': slide.panel_layout === 'comparison' }">
            <section v-for="panel in slide.panels" :key="panel.chart">
              <header><h3>{{ panel.title }}</h3><span>{{ panel.detail }}</span></header>
              <div class="deck-distribution-chart" :data-deck-chart="panel.chart" role="img" :aria-label="panel.title"></div>
            </section>
          </div>
          <dl v-if="slide.metrics?.length" class="deck-metrics" :class="{ 'deck-metrics-facts': slide.type === 'facts' || slide.type === 'cover' }">
            <div v-for="item in slide.metrics" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd><small v-if="item.detail">{{ item.detail }}</small></div>
          </dl>

          <div v-if="slide.definitions?.length" class="deck-definitions">
            <section v-for="item in slide.definitions" :key="item.title"><h3>{{ item.title }}</h3><p>{{ item.text }}</p></section>
          </div>

          <div v-else-if="slide.type === 'timeline'" class="deck-timeline">
            <section v-for="item in slide.milestones" :key="item.period">
              <span class="deck-timeline-period">{{ item.period }}</span>
              <h3>{{ item.title }}</h3>
              <ol><li v-for="term in item.items" :key="term.label"><strong>{{ term.label }}</strong><span>{{ term.count.toLocaleString('zh-CN') }}</span></li></ol>
              <p v-if="item.text">{{ item.text }}</p>
            </section>
          </div>

          <div v-else-if="slide.type === 'posts' || slide.id === 'comment-thanks'" class="deck-stories">
            <PresentationRanking :posts="slide.posts" :comments="slide.comments" :node-label="props.nodeLabel" />
          </div>

          <div v-else-if="slide.type === 'explore' || slide.type === 'summary'" class="deck-explore">
            <ol class="deck-takeaways">
              <li v-for="item in slide.takeaways" :key="item.number">
                <span class="deck-takeaway-number">{{ item.number }}</span><h3>{{ item.title }}</h3><p>{{ item.text }}</p>
                <a v-if="slide.type === 'explore'" :href="item.href">{{ item.link }}<ArrowRight :size="16" /></a>
              </li>
            </ol>
            <div v-if="slide.type === 'explore'" class="deck-search-row"><button type="button" class="deck-search" aria-label="打开全站搜索" @click="openSearch"><Search :size="22" /><span>搜索看板数据</span><ArrowRight :size="20" /></button><p>覆盖已收录的话题、标题关键词、节点和部分活跃成员。</p></div>
          </div>

          <div v-if="slide.post_layout === 'strip'" class="deck-examples">
            <a v-for="post in slide.posts" :key="post.id" :href="post.url" target="_blank" rel="noreferrer"><span>{{ post.date }} · {{ post.badge }}</span><strong>{{ post.title }}</strong></a>
          </div>
          <PresentationRanking v-else-if="slide.type === 'chart' && slide.posts?.length" class="deck-chart-cases" :posts="slide.posts" :node-label="props.nodeLabel" />
          <a v-for="comment in slide.type === 'chart' ? slide.comments : []" :key="comment.id" class="deck-comment" :href="comment.url" target="_blank" rel="noreferrer">
            <div><span>{{ comment.label || '评论原文' }}</span><h3 v-if="comment.topic_title">{{ comment.topic_title }}</h3><blockquote>{{ comment.text }}</blockquote><p>{{ comment.note }}</p></div>
            <small>{{ comment.username }} · {{ comment.date }}<br>感谢 {{ comment.thanks?.toLocaleString('zh-CN') ?? '未知' }} · #{{ comment.topic_id }}</small>
          </a>
          <section v-if="slide.findings?.length" class="deck-findings" aria-label="数据解读">
            <div v-for="finding in slide.findings" :key="finding.title">
              <h3>{{ finding.title }}</h3>
              <p>{{ finding.text }}</p>
            </div>
          </section>
        </div>
        <div v-if="chartError" class="deck-chart-error" role="alert"><p>图表暂时无法加载</p><button type="button" class="text-action" @click="renderCurrentChart">重新加载</button></div>
      </div>
      <footer class="deck-note">
        <span class="deck-note-copy">{{ slide.note }}</span>
        <details v-if="slide.note" :key="slide.id" class="deck-note-mobile"><summary>数据说明</summary><p>{{ slide.note }}</p></details>
        <span class="deck-counter">{{ counter }}</span>
      </footer>
    </article>
    <div v-else class="deck-empty" role="status">演示数据暂未准备完成。</div>

  </section>
</template>

<style scoped src="../assets/presentation.css"></style>
