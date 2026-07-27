<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import RankedColumns from "../components/RankedColumns.vue"
import SearchSelect from "../components/SearchSelect.vue"
import { getJson } from "../services/dataClient"
import type { DashboardChart } from "../chartRuntime"
import type { Grain, RankedColumn, RankedItem, SearchOption } from "../types/analytics"
import { paginationItems } from "../utils/pagination"

type HotspotRow = [string, string, number, number, number, number, number, number]
type HotspotItem = {
  period: string
  term: string
  count: number
  authors: number
  nodes: number
  share: number
  burst: number
  score: number
}
type ContentPost = {
  id: number
  title: string
  node: string
  tags: string[]
  create_at: number
  clicks: number
  reply_count: number
  favorite_count: number
  thank_count: number
  author: string
  score: number
}

const props = defineProps<{
  fromPeriod: string
  toPeriod: string
  grain: Grain
  selectedTerm: string
  topLimit: number
  nodeLabel: (node: string) => string
}>()
const emit = defineEmits<{
  "update:selectedTerm": [term: string]
  "update:topLimit": [limit: number]
  topic: [tag: string]
  node: [node: string]
}>()

const index = shallowRef<any>(null)
const rows = shallowRef<HotspotRow[]>([])
const detail = shallowRef<any>(null)
const loading = ref(true)
const detailLoading = ref(false)
const error = ref("")
const postPage = ref(1)
const pageSize = 10
const yearCache = new Map<string, HotspotRow[]>()
const detailCache = new Map<string, any>()
let heatmapChart: DashboardChart | null = null
let trendChart: DashboardChart | null = null
let chartRuntime: typeof import("../chartRuntime") | null = null
let detailRequestId = 0
let rowsRequestId = 0
let heatmapRenderId = 0
let trendRenderId = 0
const heatmapTermIndices = new Map<string, number[]>()
let hoveredHeatmapTerm = ""

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}

function formatDateTime(timestamp: number | undefined) {
  if (!timestamp) return "时间未知"
  const date = new Date(timestamp * 1000)
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(item => item.type === type)?.value || ""
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`
}

function toItem(row: HotspotRow): HotspotItem {
  return {
    period: row[0], term: row[1], count: row[2], authors: row[3], nodes: row[4],
    share: row[5], burst: row[6], score: row[7],
  }
}

const selectedTermModel = computed({
  get: () => props.selectedTerm,
  set: (value: string) => emit("update:selectedTerm", value),
})

const availablePeriods = computed(() => Object.keys(index.value?.period_totals || {})
  .filter(period => period >= props.fromPeriod && period <= props.toPeriod))

const displayRows = computed<HotspotItem[]>(() => {
  const selected = rows.value.map(toItem).filter(item => item.period >= props.fromPeriod && item.period <= props.toPeriod)
  if (props.grain === "month") return selected
  const grouped = new Map<string, HotspotItem>()
  for (const item of selected) {
    const period = item.period.slice(0, 4)
    const key = `${period}\u0000${item.term}`
    const current = grouped.get(key) || { period, term: item.term, count: 0, authors: 0, nodes: 0, share: 0, burst: 0, score: 0 }
    current.count += item.count
    current.authors = Math.max(current.authors, item.authors)
    current.nodes = Math.max(current.nodes, item.nodes)
    current.burst += item.burst * item.count
    current.score += item.score
    grouped.set(key, current)
  }
  const totals = new Map<string, number>()
  for (const period of availablePeriods.value) {
    const year = period.slice(0, 4)
    totals.set(year, (totals.get(year) || 0) + Number(index.value.period_totals[period] || 0))
  }
  return [...grouped.values()].map(item => ({
    ...item,
    share: item.count / Math.max(1, totals.get(item.period) || 0) * 100,
    burst: item.count ? item.burst / item.count : 0,
  }))
})

const displayPeriods = computed(() => props.grain === "month"
  ? availablePeriods.value
  : [...new Set(availablePeriods.value.map(period => period.slice(0, 4)))])

const rankings = computed(() => {
  const grouped = new Map<string, HotspotItem[]>()
  for (const item of displayRows.value) {
    if (!grouped.has(item.period)) grouped.set(item.period, [])
    grouped.get(item.period)!.push(item)
  }
  for (const values of grouped.values()) values.sort((a, b) => b.count - a.count || b.score - a.score || a.term.localeCompare(b.term, "zh-CN"))
  return grouped
})

const latestPeriod = computed(() => displayPeriods.value[displayPeriods.value.length - 1] || "")
const latestRows = computed(() => rankings.value.get(latestPeriod.value) || [])
const rankingColumns = computed<RankedColumn[]>(() => {
  const hotspots = latestRows.value.slice(0, 10)
  const emerging = [...latestRows.value]
    .filter(item => item.burst > 0.25)
    .sort((a, b) => b.burst - a.burst || b.count - a.count)
    .slice(0, 10)
  const broad = [...latestRows.value]
    .sort((a, b) => b.nodes - a.nodes || b.authors - a.authors || b.count - a.count)
    .slice(0, 10)
  const items = (values: HotspotItem[], value: (item: HotspotItem) => string) => values.map(item => ({
    key: item.term, label: item.term, value: value(item), action: `term:${item.term}`, active: item.term === props.selectedTerm,
  }))
  return [
    { key: "hot", title: `${latestPeriod.value} 热点内容`, items: items(hotspots, item => `${formatNumber(item.count)} 帖`) },
    { key: "rise", title: "新兴内容", items: items(emerging, item => `+${item.burst.toFixed(1)}`) },
    { key: "breadth", title: "讨论覆盖", items: items(broad, item => `${formatNumber(item.nodes)} 节点`) },
  ]
})

const searchOptions = computed<SearchOption[]>(() => Object.entries(index.value?.terms || {})
  .map(([term, raw]) => {
    const entry = raw as any
    return { value: term, label: term, meta: `${formatNumber(entry.total)} 个标题 · ${entry.first_period} 至 ${entry.last_period}` }
  })
  .sort((a, b) => a.label.localeCompare(b.label, "zh-CN")))

const detailRows = computed<HotspotItem[]>(() => (detail.value?.rows || [])
  .map(toItem)
  .filter((item: HotspotItem) => item.period >= props.fromPeriod && item.period <= props.toPeriod))

const detailSeries = computed(() => {
  const source = new Map(detailRows.value.map(item => [item.period, item]))
  if (props.grain === "month") return availablePeriods.value.map(period => source.get(period) || {
    period, term: props.selectedTerm, count: 0, authors: 0, nodes: 0, share: 0, burst: 0, score: 0,
  })
  return displayPeriods.value.map(period => {
    const values = detailRows.value.filter(item => item.period.startsWith(period))
    const count = values.reduce((sum, item) => sum + item.count, 0)
    const total = availablePeriods.value.filter(month => month.startsWith(period))
      .reduce((sum, month) => sum + Number(index.value.period_totals[month] || 0), 0)
    return {
      period, term: props.selectedTerm, count,
      authors: Math.max(0, ...values.map(item => item.authors)),
      nodes: Math.max(0, ...values.map(item => item.nodes)),
      share: count / Math.max(1, total) * 100,
      burst: count ? values.reduce((sum, item) => sum + item.burst * item.count, 0) / count : 0,
      score: values.reduce((sum, item) => sum + item.score, 0),
    }
  })
})

const detailStats = computed(() => {
  const active = detailSeries.value.filter(item => item.count > 0)
  const total = active.reduce((sum, item) => sum + item.count, 0)
  const peak = [...active].sort((a, b) => b.count - a.count)[0]
  const latest = active[active.length - 1]
  return {
    total,
    share: total / Math.max(1, availablePeriods.value.reduce((sum, period) => sum + Number(index.value?.period_totals?.[period] || 0), 0)) * 100,
    peak: peak?.period || "-",
    burst: latest?.burst || 0,
  }
})

const detailColumns = computed<RankedColumn[]>(() => detail.value ? [
  {
    key: "tags", title: "关联标签", items: (detail.value.tags || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 主题`, action: `tag:${item[0]}`,
    })),
  },
  {
    key: "nodes", title: "主要节点", items: (detail.value.nodes || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: props.nodeLabel(item[0]), value: `${formatNumber(item[1])} 主题`, action: `node:${item[0]}`,
    })),
  },
] : [])

const detailPosts = computed<ContentPost[]>(() => (detail.value?.posts || [])
  .filter((post: ContentPost) => {
    const period = new Date(post.create_at * 1000).toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" }).slice(0, 7)
    return period >= props.fromPeriod && period <= props.toPeriod
  })
  .sort((a: ContentPost, b: ContentPost) => b.score - a.score || b.create_at - a.create_at))
const postPageCount = computed(() => Math.max(1, Math.ceil(detailPosts.value.length / pageSize)))
const displayedPosts = computed(() => detailPosts.value.slice((postPage.value - 1) * pageSize, postPage.value * pageSize))
const postPagination = computed(() => paginationItems(postPage.value, postPageCount.value))

async function ensureRuntime() {
  chartRuntime ||= await import("../chartRuntime")
  return chartRuntime
}

function lineDataZoom(periods: string[], visiblePeriods = 24) {
  if (periods.length <= visiblePeriods) return []
  const start = Math.max(0, (1 - visiblePeriods / periods.length) * 100)
  return [
    { type: "inside", xAxisIndex: 0, start, end: 100, zoomOnMouseWheel: false, moveOnMouseWheel: true },
    { type: "slider", xAxisIndex: 0, start, end: 100, bottom: 8, height: 18, borderColor: "#d9dee7", fillerColor: "rgba(49,105,216,.12)", handleStyle: { color: "#3169d8" } },
  ]
}

function heatmapDataZoom(periods: string[], element: HTMLElement) {
  const availableWidth = Math.max(320, element.clientWidth)
  const maxVisible = props.grain === "month" ? 14 : 12
  const visibleCount = Math.max(4, Math.min(periods.length, maxVisible, Math.floor(availableWidth / 76)))
  const startValue = Math.max(0, periods.length - visibleCount)
  const endValue = Math.max(0, periods.length - 1)
  return [
    {
      type: "inside", xAxisIndex: 0, startValue, endValue,
      zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: true,
    },
    {
      type: "slider", xAxisIndex: 0, startValue, endValue, height: 18, bottom: 8,
      brushSelect: false, showDetail: false, borderColor: "#d9dee7", backgroundColor: "#f7f8fa",
      fillerColor: "rgba(47, 143, 131, 0.18)", handleStyle: { color: "#ffffff", borderColor: "#667085" },
      moveHandleStyle: { color: "#667085" },
      selectedDataBackground: { lineStyle: { color: "#2f8f83" }, areaStyle: { color: "#b9d8d0" } },
    },
  ]
}

function heatmapValue(params: any) {
  return params.data?.value || params.data || []
}

function clearHeatmapHighlight() {
  if (!heatmapChart || !hoveredHeatmapTerm) return
  heatmapChart.dispatchAction({
    type: "downplay", seriesIndex: 0,
    dataIndex: heatmapTermIndices.get(hoveredHeatmapTerm) || [],
  })
  hoveredHeatmapTerm = ""
}

function highlightHeatmapTerm(term: string) {
  if (!heatmapChart || !term || term === hoveredHeatmapTerm) return
  clearHeatmapHighlight()
  hoveredHeatmapTerm = term
  heatmapChart.dispatchAction({
    type: "highlight", seriesIndex: 0,
    dataIndex: heatmapTermIndices.get(term) || [],
  })
}

async function renderHeatmap() {
  const renderId = ++heatmapRenderId
  await nextTick()
  const element = document.getElementById("content-hotspot-heatmap")
  if (!element) return
  const runtime = await ensureRuntime()
  if (renderId !== heatmapRenderId || !element.isConnected) return
  if (!heatmapChart || heatmapChart.getDom() !== element) {
    heatmapChart?.dispose()
    heatmapChart = runtime.initChart(element)
  }
  const chartRows: any[] = []
  heatmapTermIndices.clear()
  for (const [x, period] of displayPeriods.value.entries()) {
    for (const [rank, item] of (rankings.value.get(period) || []).slice(0, props.topLimit).entries()) {
      const dataIndex = chartRows.length
      chartRows.push([x, rank, item.count, item.term, item.count, item.authors, item.nodes, item.burst, item.share])
      const indices = heatmapTermIndices.get(item.term) || []
      indices.push(dataIndex)
      heatmapTermIndices.set(item.term, indices)
    }
  }
  const max = Math.max(1, ...chartRows.map(item => Number(item[2])))
  const data = chartRows.map(item => ({
    value: item,
    label: { color: item[2] > max * 0.55 ? "#ffffff" : "#1d2939" },
  }))
  hoveredHeatmapTerm = ""
  heatmapChart.off("mouseover")
  heatmapChart.off("globalout")
  heatmapChart.off("click")
  heatmapChart.setOption({
    aria: { enabled: true }, animation: false,
    tooltip: {
      confine: true,
      formatter: (params: any) => {
        const item = heatmapValue(params)
        const authorLabel = props.grain === "year" ? "单月作者峰值" : "作者"
        return `<strong>${displayPeriods.value[item[0]]} · ${item[3]}</strong><br>标题：${formatNumber(item[4])}<br>同期占比：${Number(item[8]).toFixed(2)}%<br>${authorLabel}：${formatNumber(item[5])}<br>节点：${formatNumber(item[6])}<br>相对热度：${item[7] > 0 ? "+" : ""}${Number(item[7]).toFixed(2)}`
      },
    },
    grid: { top: 18, right: 24, bottom: 92, left: 24 },
    xAxis: {
      type: "category", data: displayPeriods.value, position: "bottom",
      axisLabel: { interval: 0, rotate: 45, color: "#667085", fontSize: 10 },
      axisLine: { lineStyle: { color: "#d9dee7" } }, axisTick: { alignWithLabel: true },
    },
    yAxis: { type: "category", data: Array.from({ length: props.topLimit }, (_, index) => `Top ${index + 1}`), inverse: true, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
    visualMap: {
      show: false, min: 0, max, dimension: 2, calculable: false,
      inRange: { color: ["#f7f8fa", "#b9d8d0", "#2f8f83", "#0b4f4a"] },
    },
    dataZoom: heatmapDataZoom(displayPeriods.value, element),
    series: [{
      type: "heatmap", data, progressive: 1000,
      label: {
        show: true, fontSize: 10, width: 78, overflow: "truncate",
        formatter: (params: any) => heatmapValue(params)[3] || "",
      },
      itemStyle: { borderColor: "#ffffff", borderWidth: 1 },
      emphasis: {
        itemStyle: { color: "#d94841", borderColor: "#ffffff", borderWidth: 1 },
        label: { color: "#ffffff", fontWeight: 700 },
      },
    }],
  } as any, true)
  heatmapChart.on("mouseover", (params: any) => highlightHeatmapTerm(heatmapValue(params)[3] || ""))
  heatmapChart.on("globalout", clearHeatmapHighlight)
  heatmapChart.on("click", (params: any) => selectTerm(heatmapValue(params)[3] || ""))
  heatmapChart.resize()
}

async function renderTrend() {
  const renderId = ++trendRenderId
  await nextTick()
  const element = document.getElementById("content-term-trend")
  if (!element || !detail.value) return
  const runtime = await ensureRuntime()
  if (renderId !== trendRenderId || !element.isConnected) return
  if (!trendChart || trendChart.getDom() !== element) {
    trendChart?.dispose()
    trendChart = runtime.initChart(element)
  }
  const periods = detailSeries.value.map(item => item.period)
  trendChart.setOption({
    aria: { enabled: true }, animation: false,
    tooltip: {
      trigger: "axis", confine: true,
      formatter: (params: any[]) => {
        const item = params[0]
        const point = detailSeries.value[item?.dataIndex]
        return `<strong>${item?.axisValueLabel || ""}</strong><br>${props.selectedTerm}：${formatNumber(point?.count)} 个标题 · ${Number(point?.share || 0).toFixed(2)}%`
      },
    },
    grid: { top: 24, left: 68, right: 24, bottom: periods.length > 24 ? 72 : 42 },
    xAxis: { type: "category", data: periods, axisLabel: { color: "#667085", fontSize: 10, showMaxLabel: true }, axisLine: { lineStyle: { color: "#d9dee7" } } },
    yAxis: { type: "value", name: "标题数", axisLabel: { color: "#667085", fontSize: 10 }, splitLine: { lineStyle: { color: "#edf0f3" } } },
    dataZoom: lineDataZoom(periods),
    series: [{
      name: props.selectedTerm, type: "line", showSymbol: false, smooth: false,
      data: detailSeries.value.map(item => item.count),
      lineStyle: { width: 2, color: "#c4322f" }, itemStyle: { color: "#c4322f" }, areaStyle: { color: "rgba(196,50,47,.08)" },
    }],
  } as any, true)
  trendChart.resize()
}

async function loadRows() {
  if (!index.value || !props.fromPeriod || !props.toPeriod) return
  const requestId = ++rowsRequestId
  const initialLoad = rows.value.length === 0
  if (initialLoad) loading.value = true
  error.value = ""
  try {
    const start = Number(props.fromPeriod.slice(0, 4))
    const end = Number(props.toPeriod.slice(0, 4))
    const years = Array.from({ length: end - start + 1 }, (_, offset) => String(start + offset))
    await Promise.all(years.map(async year => {
      if (yearCache.has(year) || !index.value.year_shards?.[year]) return
      const payload = await getJson(index.value.year_shards[year])
      yearCache.set(year, payload.rows || [])
    }))
    if (requestId !== rowsRequestId) return
    rows.value = years.flatMap(year => yearCache.get(year) || [])
    const known = Boolean(index.value.terms?.[props.selectedTerm])
    if (!known) emit("update:selectedTerm", latestRows.value[0]?.term || "")
  } catch (cause) {
    if (requestId === rowsRequestId) error.value = cause instanceof Error ? cause.message : "内容热点加载失败"
  } finally {
    if (requestId === rowsRequestId && initialLoad) loading.value = false
  }
  if (requestId !== rowsRequestId) return
  await nextTick()
  await renderHeatmap()
}

async function loadDetail(term: string) {
  const requestId = ++detailRequestId
  postPage.value = 1
  if (!term || !index.value?.terms?.[term]) {
    detail.value = null
    return
  }
  detailLoading.value = true
  try {
    const bucket = index.value.terms[term].bucket
    let payload = detailCache.get(bucket)
    if (!payload) {
      payload = await getJson(`dynamic-content-term-details-${bucket}.json`)
      detailCache.set(bucket, payload)
    }
    if (requestId === detailRequestId) detail.value = payload.details?.[term] || null
  } catch (cause) {
    if (requestId === detailRequestId) error.value = cause instanceof Error ? cause.message : "内容详情加载失败"
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
  await nextTick()
  if (requestId === detailRequestId) await renderTrend()
}

function selectTerm(term: string) {
  if (!term) return
  emit("update:selectedTerm", term)
  nextTick(() => document.getElementById("content-term-detail")?.scrollIntoView({ behavior: "smooth", block: "start" }))
}

function selectRankedItem(item: RankedItem) {
  if (item.action?.startsWith("term:")) selectTerm(item.action.slice(5))
  else if (item.action?.startsWith("tag:")) emit("topic", item.action.slice(4))
  else if (item.action?.startsWith("node:")) emit("node", item.action.slice(5))
}

function handleResize() {
  heatmapChart?.resize()
  trendChart?.resize()
}

watch(() => [props.fromPeriod, props.toPeriod], loadRows)
watch(() => [props.grain, props.topLimit], async () => {
  await renderHeatmap()
  await renderTrend()
})
watch(() => props.selectedTerm, loadDetail)
watch(detailPosts, () => { postPage.value = Math.min(postPage.value, postPageCount.value) })

onMounted(async () => {
  window.addEventListener("resize", handleResize)
  try {
    index.value = await getJson("dynamic-content-hotspots-index.json")
    await loadRows()
    await loadDetail(props.selectedTerm || latestRows.value[0]?.term || "")
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : "内容热点加载失败"
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize)
  heatmapChart?.dispose()
  trendChart?.dispose()
})
</script>

<template>
  <section class="view-section content-hotspots-view">
    <div class="section-toolbar">
      <div><h2>内容热点</h2><p>从帖子标题识别具体内容词，结合标题数、作者覆盖、节点覆盖和过去 12 个月相对热度观察议题变化。</p></div>
    </div>

    <div v-if="loading" class="loading profile-loading"><span class="loading-spinner"></span><span>正在加载内容热点</span></div>
    <div v-else-if="error" class="empty-state">{{ error }}</div>
    <template v-else>
      <article class="analysis-block full">
        <header class="block-header-with-control">
          <div><h2>内容演变</h2><p>每列独立展示当月或当年的热点内容，颜色表示标题数；点击词条可查看趋势和代表帖子。</p></div>
          <div class="segmented compact-segmented" aria-label="内容热点数量">
            <button :class="{ active: topLimit === 10 }" @click="emit('update:topLimit', 10)">Top 10</button>
            <button :class="{ active: topLimit === 20 }" @click="emit('update:topLimit', 20)">Top 20</button>
            <button :class="{ active: topLimit === 30 }" @click="emit('update:topLimit', 30)">Top 30</button>
          </div>
        </header>
        <div id="content-hotspot-heatmap" class="chart content-hotspot-heatmap" :style="{ height: `${Math.max(360, 112 + topLimit * 30)}px` }"></div>
        <RankedColumns :columns="rankingColumns" @select="selectRankedItem" />
        <p class="method-note">自动分词用于补充标签无法覆盖的具体事件和产品名；已过滤推广节点、问句模板及高频泛词，词条仍可能存在语义歧义。</p>
      </article>

      <article v-if="selectedTerm" id="content-term-detail" class="analysis-block full topic-detail-block content-term-detail">
        <header class="block-header-with-control">
          <div><h2>内容详情：{{ selectedTerm }}</h2><p>趋势与规模使用当前筛选范围；关联标签、节点结构按全历史累计。</p></div>
          <SearchSelect v-model="selectedTermModel" class="topic-detail-select" label="选择内容词" icon="tag" hide-label :options="searchOptions" />
        </header>
        <div v-if="detailLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="detail">
          <div class="metric-grid four topic-detail-metrics">
            <article class="metric"><span>相关标题</span><strong>{{ formatNumber(detailStats.total) }}</strong><em>当前筛选范围</em></article>
            <article class="metric"><span>同期份额</span><strong>{{ detailStats.share.toFixed(2) }}%</strong><em>占有效帖子标题</em></article>
            <article class="metric"><span>活跃峰值</span><strong class="metric-date">{{ detailStats.peak }}</strong><em>标题数最高的{{ grain === 'month' ? '月份' : '年份' }}</em></article>
            <article class="metric"><span>最新相对热度</span><strong>{{ detailStats.burst > 0 ? '+' : '' }}{{ detailStats.burst.toFixed(2) }}</strong><em>相对过去 12 个月</em></article>
          </div>
          <section class="topic-detail-trend">
            <header><h3>{{ selectedTerm }} 内容趋势</h3><p>统计标题中出现该词的帖子数量；同一标题对单个词只计一次。</p></header>
            <div id="content-term-trend" class="chart compact-chart"></div>
          </section>
          <p class="topic-detail-scope-note">全历史共有 {{ formatNumber(detail.total) }} 个标题包含“{{ selectedTerm }}”；关联标签和节点数量均为相关主题数。</p>
          <RankedColumns :columns="detailColumns" @select="selectRankedItem" />
          <section class="topic-detail-posts content-hotspot-posts">
            <header class="content-section-header">
              <div><h3>代表帖子</h3><p>每年保留综合互动得分最高的 3 个相关帖子，当前按互动得分排序。</p></div>
            </header>
            <div class="post-list">
              <article v-for="post in displayedPosts" :key="post.id" class="post-row">
                <div class="post-main">
                  <div class="post-meta"><span>{{ formatDateTime(post.create_at) }}</span><button class="text-action" @click="emit('node', post.node)">{{ nodeLabel(post.node) }}</button><span>#{{ post.id }}</span></div>
                  <a :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">{{ post.title }}</a>
                  <div class="post-tags"><button v-for="tag in post.tags.slice(0, 6)" :key="tag" @click="emit('topic', tag)">{{ tag }}</button></div>
                </div>
                <dl>
                  <div><dt>点击</dt><dd>{{ formatNumber(post.clicks) }}</dd></div>
                  <div><dt>回复</dt><dd>{{ formatNumber(post.reply_count) }}</dd></div>
                  <div><dt>收藏</dt><dd>{{ formatNumber(post.favorite_count) }}</dd></div>
                  <div><dt>感谢</dt><dd>{{ formatNumber(post.thank_count) }}</dd></div>
                </dl>
              </article>
              <div v-if="!detailPosts.length" class="empty-state compact-empty">当前筛选范围内没有该内容词的代表帖子。</div>
              <footer v-else-if="detailPosts.length > pageSize" class="ranking-pagination detail-pagination">
                <span>共 {{ formatNumber(detailPosts.length) }} 帖 · 第 {{ postPage }} / {{ postPageCount }} 页</span>
                <nav aria-label="内容代表帖子分页">
                  <button class="pagination-arrow" aria-label="上一页" :disabled="postPage <= 1" @click="postPage--">‹</button>
                  <template v-for="item in postPagination" :key="item">
                    <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === postPage }" :aria-current="item === postPage ? 'page' : undefined" @click="postPage = item">{{ item }}</button>
                    <span v-else class="pagination-gap" aria-hidden="true">…</span>
                  </template>
                  <button class="pagination-arrow" aria-label="下一页" :disabled="postPage >= postPageCount" @click="postPage++">›</button>
                </nav>
              </footer>
            </div>
          </section>
        </template>
      </article>
    </template>
  </section>
</template>

<style scoped>
.content-hotspots-view { min-width: 0; }
.content-hotspot-heatmap { min-height: 360px; }
.content-term-detail { scroll-margin-top: 156px; }
.content-hotspot-posts { margin-top: 2px; }
@media (max-width: 680px) {
  .content-hotspot-heatmap { min-height: 360px; }
  .content-term-detail .block-header-with-control { align-items: stretch; }
  .content-term-detail .topic-detail-select { width: 100%; }
}
</style>
