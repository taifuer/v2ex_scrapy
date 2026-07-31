<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import ComparisonSelect from "../components/ComparisonSelect.vue"
import RankedColumns from "../components/RankedColumns.vue"
import SearchSelect from "../components/SearchSelect.vue"
import PageHeader from "../components/PageHeader.vue"
import { getJson } from "../services/dataClient"
import type { DashboardChart } from "../chartRuntime"
import { chartTheme, comparisonColors, heatmapColors } from "../chartTheme"
import type { Grain, RankedColumn, RankedItem, SearchOption } from "../types/analytics"
import { paginationItems } from "../utils/pagination"
import { clearLegendHoverAfterSelection, wrappedLegendLayout } from "../utils/chartLayout"

type HotspotRow = [string, string, number, number, number, number, number, number, number, number, number, boolean]
type HotspotItem = {
  period: string
  term: string
  count: number
  authors: number
  nodes: number
  share: number
  burst: number
  score: number
  tagCount: number
  contentRank: number
  tagRank: number
  isNew: boolean
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
  comparedTerms: string[]
  topLimit: number
  nodeLabel: (node: string) => string
}>()
const emit = defineEmits<{
  "update:selectedTerm": [term: string]
  "update:comparedTerms": [terms: string[]]
  "update:topLimit": [limit: number]
  topic: [tag: string]
  node: [node: string]
  member: [username: string]
}>()

const index = shallowRef<any>(null)
const rows = shallowRef<HotspotRow[]>([])
const annualRows = shallowRef<HotspotRow[]>([])
const detail = shallowRef<any>(null)
const comparisonDetails = shallowRef<Record<string, any>>({})
const loading = ref(true)
const detailLoading = ref(false)
const comparisonLoading = ref(false)
const comparisonError = ref("")
const error = ref("")
const postPage = ref(1)
const relationMode = ref<"terms" | "topics">("terms")
const pageSize = 10
const yearCache = new Map<string, { rows: HotspotRow[]; annualRows: HotspotRow[] }>()
const detailCache = new Map<string, any>()
const detailRequests = new Map<string, Promise<any>>()
let heatmapChart: DashboardChart | null = null
let trendChart: DashboardChart | null = null
let chartRuntime: typeof import("../chartRuntime") | null = null
let detailRequestId = 0
let comparisonRequestId = 0
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

function escapeHtml(value: unknown) {
  const element = document.createElement("span")
  element.textContent = String(value ?? "")
  return element.innerHTML
}

function toItem(row: HotspotRow): HotspotItem {
  return {
    period: row[0], term: row[1], count: row[2], authors: row[3], nodes: row[4],
    share: row[5], burst: row[6], score: row[7], tagCount: row[8],
    contentRank: row[9], tagRank: row[10], isNew: Boolean(row[11]),
  }
}

const selectedTermModel = computed({
  get: () => props.selectedTerm,
  set: (value: string) => emit("update:selectedTerm", value),
})
const comparedTermsModel = computed({
  get: () => props.comparedTerms,
  set: (values: string[]) => emit("update:comparedTerms", values),
})

const availablePeriods = computed(() => Object.keys(index.value?.period_totals || {})
  .filter(period => period >= props.fromPeriod && period <= props.toPeriod))

const displayRows = computed<HotspotItem[]>(() => {
  if (props.grain === "month") {
    return rows.value.map(toItem).filter(item => item.period >= props.fromPeriod && item.period <= props.toPeriod)
  }
  const startYear = props.fromPeriod.slice(0, 4)
  const endYear = props.toPeriod.slice(0, 4)
  return annualRows.value.map(toItem).filter(item => item.period >= startYear && item.period <= endYear)
})

const displayPeriods = computed(() => props.grain === "month"
  ? availablePeriods.value
  : [...new Set(availablePeriods.value.map(period => period.slice(0, 4)))])

const rankings = computed(() => {
  const grouped = new Map<string, HotspotItem[]>()
  for (const item of displayRows.value) {
    if (!item.contentRank) continue
    if (!grouped.has(item.period)) grouped.set(item.period, [])
    grouped.get(item.period)!.push(item)
  }
  for (const values of grouped.values()) values.sort((a, b) => b.count - a.count || b.score - a.score || a.term.localeCompare(b.term, "zh-CN"))
  return grouped
})

const latestPeriod = computed(() => displayPeriods.value[displayPeriods.value.length - 1] || "")
const latestRows = computed(() => rankings.value.get(latestPeriod.value) || [])
const searchOptions = computed<SearchOption[]>(() => Object.entries(index.value?.terms || {})
  .map(([term, raw]) => {
    const entry = raw as any
    return { value: term, label: term, meta: `${formatNumber(entry.total)} 个标题 · ${entry.first_period} 至 ${entry.last_period}` }
  })
  .sort((a, b) => a.label.localeCompare(b.label, "zh-CN")))
const comparisonOptions = computed<SearchOption[]>(() => Object.entries(index.value?.terms || {})
  .map(([term, raw]) => {
    const entry = raw as any
    return {
      value: term,
      label: term,
      total: Number(entry.total || 0),
      meta: `${formatNumber(entry.total)} 个标题 · ${entry.first_period} 至 ${entry.last_period}`,
    }
  })
  .sort((left, right) => right.total - left.total || left.label.localeCompare(right.label, "zh-CN"))
  .map(({ value, label, meta }) => ({ value, label, meta })))

function rowsForDetail(rawDetail: any): HotspotItem[] {
  return ((rawDetail?.rows || []) as HotspotRow[])
    .map(toItem)
    .filter((item: HotspotItem) => item.period >= props.fromPeriod && item.period <= props.toPeriod)
}

function buildDetailSeries(term: string, rawDetail: any): HotspotItem[] {
  const termRows = rowsForDetail(rawDetail)
  const source = new Map(termRows.map((item: HotspotItem) => [item.period, item]))
  if (props.grain === "month") return availablePeriods.value.map(period => source.get(period) || {
    period, term, count: 0, authors: 0, nodes: 0, share: 0, burst: 0, score: 0,
    tagCount: 0, contentRank: 0, tagRank: 0, isNew: false,
  })
  return displayPeriods.value.map(period => {
    const values = termRows.filter((item: HotspotItem) => item.period.startsWith(period))
    const annual = displayRows.value.find(item => item.period === period && item.term === term)
    const count = values.reduce((sum, item) => sum + item.count, 0)
    const total = availablePeriods.value.filter(month => month.startsWith(period))
      .reduce((sum, month) => sum + Number(index.value.period_totals[month] || 0), 0)
    return {
      period, term, count,
      authors: Math.max(0, ...values.map(item => item.authors)),
      nodes: Math.max(0, ...values.map(item => item.nodes)),
      share: count / Math.max(1, total) * 100,
      burst: count ? values.reduce((sum, item) => sum + item.burst * item.count, 0) / count : 0,
      score: values.reduce((sum, item) => sum + item.score, 0),
      tagCount: values.reduce((sum, item) => sum + item.tagCount, 0),
      contentRank: annual?.contentRank || 0, tagRank: annual?.tagRank || 0,
      isNew: annual?.isNew || values.some(item => item.isNew),
    }
  })
}

const detailRows = computed<HotspotItem[]>(() => rowsForDetail(detail.value))
const detailSeries = computed(() => buildDetailSeries(props.selectedTerm, detail.value))

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
    contentRank: latest?.contentRank || 0,
  }
})

const detailColumns = computed<RankedColumn[]>(() => detail.value ? [
  {
    key: relationMode.value === "terms" ? "related-terms" : "related-topics",
    title: relationMode.value === "terms" ? "共现热词" : "关联话题",
    items: (relationMode.value === "terms" ? detail.value.related_terms || [] : detail.value.topics || [])
      .slice(0, 20)
      .map((item: any[]) => ({
        key: item[0], label: item[0], value: `${formatNumber(item[1])} 主题`,
        action: relationMode.value === "terms" ? `term:${item[0]}` : `tag:${item[0]}`,
      })),
  },
  {
    key: "nodes", title: "主要节点", items: (detail.value.nodes || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: props.nodeLabel(item[0]), value: `${formatNumber(item[1])} 主题`, action: `node:${item[0]}`,
    })),
  },
  {
    key: "authors", title: "活跃用户", items: (detail.value.authors || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 主题`, action: `member:${item[0]}`,
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
      chartRows.push([
        x, rank, item.count, item.term, item.count, item.authors, item.nodes, item.burst, item.share,
        item.tagCount, item.contentRank, item.tagRank, item.isNew ? 1 : 0,
      ])
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
        const contentRank = item[10] ? `#${formatNumber(item[10])}` : "未入榜"
        return `<strong>${displayPeriods.value[item[0]]} · ${item[3]}</strong><br>相关主题：${formatNumber(item[4])} · 排名 ${contentRank}<br>同期占比：${Number(item[8]).toFixed(2)}%<br>${authorLabel}：${formatNumber(item[5])}<br>节点：${formatNumber(item[6])}<br>相对热度：${item[7] > 0 ? "+" : ""}${Number(item[7]).toFixed(2)}`
      },
    },
    grid: { top: 18, right: 24, bottom: 92, left: 24 },
    xAxis: {
      type: "category", data: displayPeriods.value, position: "bottom",
      axisLabel: { interval: 0, rotate: 45, color: "#667085", fontSize: 10 },
      axisLine: { lineStyle: { color: chartTheme.axisLine } }, axisTick: { alignWithLabel: true },
    },
    yAxis: { type: "category", data: Array.from({ length: props.topLimit }, (_, index) => `Top ${index + 1}`), inverse: true, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false } },
    visualMap: {
      show: false, min: 0, max, dimension: 2, calculable: false,
      inRange: { color: heatmapColors },
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
  const seriesDetails = [
    { name: props.selectedTerm, detail: detail.value, color: chartTheme.selected, main: true },
    ...props.comparedTerms.map((term, comparisonIndex) => ({
      name: term,
      detail: comparisonDetails.value[term],
      color: comparisonColors[comparisonIndex],
      main: false,
    })),
  ].filter(item => Boolean(item.detail))
  const seriesValues = new Map(seriesDetails.map(item => [item.name, buildDetailSeries(item.name, item.detail)]))
  const periods = detailSeries.value.map(item => item.period)
  const legendLayout = seriesDetails.length > 1
    ? wrappedLegendLayout(element, seriesDetails.map(item => item.name))
    : null
  if (!legendLayout) element.style.height = "300px"
  trendChart.resize()
  trendChart.setOption({
    aria: { enabled: true }, animation: false,
    color: seriesDetails.map(item => item.color),
    tooltip: {
      trigger: "axis", confine: true,
      formatter: (params: any[]) => {
        const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
        const rows = items.map(item => {
          const point = seriesValues.get(item.seriesName)?.[item.dataIndex]
          const rank = point?.contentRank ? `#${formatNumber(point.contentRank)}` : "未入榜"
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:210px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${formatNumber(point?.count)} <small style="color:#667085;font-weight:400">${rank} · ${Number(point?.share || 0).toFixed(2)}%</small></strong></span>`
        }).join("")
        return `<div><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;gap:6px;margin-top:8px">${rows}</div></div>`
      },
    },
    legend: legendLayout?.option || { show: false },
    grid: { top: 24, left: 68, right: 24, bottom: legendLayout?.gridBottom || 54 },
    xAxis: { type: "category", data: periods, axisLabel: { color: chartTheme.axis, fontSize: 10, hideOverlap: true, showMinLabel: true, showMaxLabel: true }, axisLine: { lineStyle: { color: chartTheme.axisLine } } },
    yAxis: { type: "value", name: "主题数", axisLabel: { color: chartTheme.axis, fontSize: 10 }, splitLine: { lineStyle: { color: chartTheme.gridLine } } },
    series: seriesDetails.map(item => ({
      name: item.name,
      type: "line",
      showSymbol: periods.length <= 24,
      symbolSize: 6,
      smooth: false,
      data: (seriesValues.get(item.name) || []).map(point => point.count),
      lineStyle: { width: item.main ? 3 : 2.2, color: item.color },
      itemStyle: { color: item.color },
      areaStyle: item.main && seriesDetails.length === 1 ? { color: "rgba(217,72,65,.08)" } : undefined,
      emphasis: { focus: "series", lineStyle: { width: item.main ? 4 : 3.5 } },
    })),
  } as any, true)
  clearLegendHoverAfterSelection(trendChart)
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
      yearCache.set(year, { rows: payload.rows || [], annualRows: payload.annual_rows || [] })
    }))
    if (requestId !== rowsRequestId) return
    rows.value = years.flatMap(year => yearCache.get(year)?.rows || [])
    annualRows.value = years.flatMap(year => yearCache.get(year)?.annualRows || [])
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
  await renderTrend()
}

async function getDetailBucket(bucket: string) {
  const cached = detailCache.get(bucket)
  if (cached) return cached
  let request = detailRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-content-term-details-${bucket}.json`)
      .then(payload => {
        detailCache.set(bucket, payload)
        return payload
      })
      .finally(() => detailRequests.delete(bucket))
    detailRequests.set(bucket, request)
  }
  return request
}

async function getTermDetail(term: string) {
  const entry = index.value?.terms?.[term]
  if (!entry) return null
  const payload = await getDetailBucket(entry.bucket)
  return payload.details?.[term] || null
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
    const termDetail = await getTermDetail(term)
    if (requestId === detailRequestId) detail.value = termDetail
  } catch (cause) {
    if (requestId === detailRequestId) error.value = cause instanceof Error ? cause.message : "内容详情加载失败"
  } finally {
    if (requestId === detailRequestId) detailLoading.value = false
  }
  await nextTick()
  if (requestId === detailRequestId) await renderTrend()
}

async function loadComparisonDetails(values = props.comparedTerms) {
  const requestId = ++comparisonRequestId
  if (!index.value) return
  comparisonError.value = ""
  const normalized = values
    .filter((term, termIndex) => term !== props.selectedTerm && values.indexOf(term) === termIndex && Boolean(index.value.terms?.[term]))
    .slice(0, 4)
  if (normalized.length !== props.comparedTerms.length || normalized.some((term, termIndex) => term !== props.comparedTerms[termIndex])) {
    emit("update:comparedTerms", normalized)
  }
  if (!normalized.length) {
    comparisonDetails.value = {}
    comparisonLoading.value = false
    await renderTrend()
    return
  }
  comparisonLoading.value = true
  try {
    const details = await Promise.all(normalized.map(async term => [term, await getTermDetail(term)] as const))
    if (requestId === comparisonRequestId) {
      comparisonDetails.value = Object.fromEntries(details.filter(([, termDetail]) => Boolean(termDetail)))
    }
  } catch {
    if (requestId === comparisonRequestId) comparisonError.value = "对比热词加载失败，请稍后重试。"
  } finally {
    if (requestId === comparisonRequestId) comparisonLoading.value = false
  }
  if (requestId === comparisonRequestId) await renderTrend()
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
  else if (item.action?.startsWith("member:")) emit("member", item.action.slice(7))
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
watch(() => props.selectedTerm, term => {
  if (props.comparedTerms.includes(term)) {
    emit("update:comparedTerms", props.comparedTerms.filter(value => value !== term))
  }
  loadDetail(term)
})
watch(() => props.comparedTerms, values => loadComparisonDetails(values))
watch(detailPosts, () => { postPage.value = Math.min(postPage.value, postPageCount.value) })

onMounted(async () => {
  window.addEventListener("resize", handleResize)
  try {
    index.value = await getJson("dynamic-content-hotspots-index.json")
    await loadRows()
    await loadDetail(props.selectedTerm || latestRows.value[0]?.term || "")
    await loadComparisonDetails()
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
    <PageHeader title="内容热点" description="统计主题标题中的高频词，观察产品、事件和概念随时间的变化。" />

    <div v-if="loading" class="loading profile-loading"><span class="loading-spinner"></span><span>正在加载内容热点</span></div>
    <div v-else-if="error" class="empty-state">{{ error }}</div>
    <template v-else>
      <article class="analysis-block full">
        <header class="block-header-with-control">
          <div><h2>逐期热词排名</h2><p>按标题中包含各热词的主题数展示每期 Top；同一主题对同一热词只计一次。</p></div>
          <div class="segmented compact-segmented" aria-label="内容热点数量">
            <button :class="{ active: topLimit === 10 }" @click="emit('update:topLimit', 10)">Top 10</button>
            <button :class="{ active: topLimit === 20 }" @click="emit('update:topLimit', 20)">Top 20</button>
            <button :class="{ active: topLimit === 30 }" @click="emit('update:topLimit', 30)">Top 30</button>
          </div>
        </header>
        <div id="content-hotspot-heatmap" class="chart content-hotspot-heatmap" :style="{ height: `${Math.max(360, 112 + topLimit * 30)}px` }"></div>
        <p class="method-note">颜色表示相关主题数量，点击词条可查看趋势和代表帖子。自动分词已过滤推广节点、交易描述、问句模板及高频泛词。</p>
      </article>

      <article v-if="selectedTerm" id="content-term-detail" class="analysis-block full topic-detail-block content-term-detail">
        <header class="block-header-with-control">
          <div><h2>内容详情：{{ selectedTerm }}</h2><p>趋势与规模使用当前筛选范围；共现热词、关联话题、主要节点和活跃用户按全历史累计。</p></div>
          <SearchSelect v-model="selectedTermModel" class="topic-detail-select" label="选择内容热词" icon="tag" hide-label :options="searchOptions" />
        </header>
        <div v-if="detailLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="detail">
          <div class="metric-grid four topic-detail-metrics">
            <article class="metric"><span>相关主题</span><strong>{{ formatNumber(detailStats.total) }}</strong><em>标题包含该词</em></article>
            <article class="metric"><span>区间占比</span><strong>{{ detailStats.share.toFixed(2) }}%</strong><em>占有效主题</em></article>
            <article class="metric"><span>活跃峰值</span><strong class="metric-date">{{ detailStats.peak }}</strong><em>相关主题最多</em></article>
            <article class="metric"><span>最新标题排名</span><strong>{{ detailStats.contentRank ? `#${formatNumber(detailStats.contentRank)}` : '未入榜' }}</strong><em>{{ grain === 'month' ? '当月' : '当年' }}标题热度</em></article>
          </div>
          <section class="topic-detail-trend">
            <header class="detail-trend-header">
              <div><h3>{{ selectedTerm }} 内容趋势</h3><p>展示所选区间内标题包含各热词的主题数量；对比项仅加入趋势图。</p></div>
              <ComparisonSelect v-model="comparedTermsModel" label="对比热词" :options="comparisonOptions" :exclude="[selectedTerm]" :loading="comparisonLoading" />
            </header>
            <p v-if="comparisonError" class="comparison-error">{{ comparisonError }}</p>
            <div id="content-term-trend" class="chart compact-chart"></div>
          </section>
          <p class="topic-detail-scope-note">全历史共有 {{ formatNumber(detail.total) }} 个主题标题包含“{{ selectedTerm }}”。共现热词表示同一标题包含两个热词的主题数；关联话题表示相关主题携带该话题的数量，以下各栏最多显示 Top 20。</p>
          <div class="content-relation-toolbar">
            <span>关联维度</span>
            <div class="segmented compact-segmented" aria-label="内容关联维度">
              <button :class="{ active: relationMode === 'terms' }" @click="relationMode = 'terms'">共现热词</button>
              <button :class="{ active: relationMode === 'topics' }" @click="relationMode = 'topics'">关联话题</button>
            </div>
          </div>
          <RankedColumns :columns="detailColumns" @select="selectRankedItem" />
          <section class="topic-detail-posts content-hotspot-posts">
            <header class="content-section-header">
              <div><h3>代表帖子</h3><p>每年保留综合互动得分最高的 10 个相关帖子，当前按互动得分排序并分页展示。</p></div>
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
              <div v-if="!detailPosts.length" class="empty-state compact-empty">当前筛选范围内没有该内容热词的代表帖子。</div>
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
.content-relation-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; }
.content-relation-toolbar > span { color: #475467; font-size: 12px; font-weight: 650; }
.content-relation-toolbar + :deep(.ranked-columns) { margin-top: 8px; }

@media (max-width: 680px) {
  .content-relation-toolbar { align-items: stretch; flex-direction: column; gap: 6px; }
  .content-relation-toolbar .segmented { width: 100%; }
  .content-relation-toolbar .segmented button { flex: 1; }
}
@media (max-width: 680px) {
  .content-hotspot-heatmap { min-height: 360px; }
  .content-term-detail .block-header-with-control { align-items: stretch; }
  .content-term-detail .topic-detail-select { width: 100%; }
}
</style>
