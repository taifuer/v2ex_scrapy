<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import AggregateGroupCards from "../components/AggregateGroupCards.vue"
import ComparisonSelect from "../components/ComparisonSelect.vue"
import PeriodSelect from "../components/PeriodSelect.vue"
import RankedColumns from "../components/RankedColumns.vue"
import SearchSelect from "../components/SearchSelect.vue"
import PageHeader from "../components/PageHeader.vue"
import ViewSectionNav from "../components/ViewSectionNav.vue"
import { getJson } from "../services/dataClient"
import type { DashboardChart } from "../chartRuntime"
import { categoricalColors, chartTheme, comparisonColors, heatmapColors } from "../chartTheme"
import type { Grain, RankedColumn, RankedItem, SearchOption } from "../types/analytics"
import { aggregateItemDisplayMinimum } from "../utils/aggregateGroups"
import { paginationItems } from "../utils/pagination"
import { clearLegendHoverAfterSelection, wrappedLegendLayout } from "../utils/chartLayout"
import { scrollToSection } from "../utils/scroll"

type HotspotRow = [string, string, number, number, number, number, number, number, number, number, number, boolean]
type ContentGroupRow = [string, string, number]
type ContentGroupTermRow = [string, string, string, number]
type ContentGroupDefinition = {
  id: string
  label: string
  description: string
  terms: string[]
}
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
type ContentMomentumItem = { term: string; count: number; delta: number }
type ContentPost = {
  id: number
  period?: string
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
  mode: "evolution" | "detail"
  fromPeriod: string
  toPeriod: string
  grain: Grain
  selectedTerm: string
  comparedTerms: string[]
  selectedPeriod: string
  topLimit: number
  trendLimit: number
  nodeLabel: (node: string) => string
}>()
const emit = defineEmits<{
  "update:selectedTerm": [term: string]
  "update:comparedTerms": [terms: string[]]
  "update:selectedPeriod": [period: string]
  "update:topLimit": [limit: number]
  "update:trendLimit": [limit: number]
  openDetail: [term: string]
  topic: [tag: string]
  node: [node: string]
  member: [username: string]
}>()

const index = shallowRef<any>(null)
const rows = shallowRef<HotspotRow[]>([])
const annualRows = shallowRef<HotspotRow[]>([])
const groupRows = shallowRef<ContentGroupRow[]>([])
const groupTermRows = shallowRef<ContentGroupTermRow[]>([])
const detail = shallowRef<any>(null)
const comparisonDetails = shallowRef<Record<string, any>>({})
const loading = ref(true)
const detailLoading = ref(false)
const comparisonLoading = ref(false)
const comparisonError = ref("")
const periodPosts = shallowRef<ContentPost[]>([])
const periodPostsLoading = ref(false)
const periodPostsError = ref("")
const error = ref("")
const postPage = ref(1)
const relationMode = ref<"terms" | "topics">("terms")
const pageSize = 10
const yearCache = new Map<string, {
  rows: HotspotRow[]
  annualRows: HotspotRow[]
  groupRows: ContentGroupRow[]
  groupTermRows: ContentGroupTermRow[]
}>()
const detailCache = new Map<string, any>()
const detailRequests = new Map<string, Promise<any>>()
const periodPostCache = new Map<string, any>()
const periodPostRequests = new Map<string, Promise<any>>()
let heatmapChart: DashboardChart | null = null
let contentTrendChart: DashboardChart | null = null
let trendChart: DashboardChart | null = null
let chartRuntime: typeof import("../chartRuntime") | null = null
let detailRequestId = 0
let comparisonRequestId = 0
let periodPostRequestId = 0
let rowsRequestId = 0
let heatmapRenderId = 0
let contentTrendRenderId = 0
let trendRenderId = 0
let mountingDetail = false
let scrollToPostsAfterPeriodChange = false
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

function shiftMonth(period: string, offset: number) {
  const [year, month] = period.split("-").map(Number)
  const monthIndex = year * 12 + month - 1 + offset
  const shiftedYear = Math.floor(monthIndex / 12)
  const shiftedMonth = monthIndex - shiftedYear * 12 + 1
  return `${shiftedYear}-${String(shiftedMonth).padStart(2, "0")}`
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
const selectedPeriodModel = computed({
  get: () => props.selectedPeriod,
  set: (value: string) => emit("update:selectedPeriod", value),
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

const monthlyItems = computed(() => rows.value.map(toItem))
const evolutionMonthlyItems = computed(() => monthlyItems.value
  .filter(item => index.value?.terms?.[item.term]?.ranked !== false))
const selectedMonthlyItems = computed(() => evolutionMonthlyItems.value
  .filter(item => item.period >= props.fromPeriod && item.period <= props.toPeriod))

const contentTotals = computed(() => {
  const totals = new Map<string, number>()
  for (const item of selectedMonthlyItems.value) {
    totals.set(item.term, (totals.get(item.term) || 0) + item.count)
  }
  return [...totals]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "zh-CN"))
})

const contentTrendTerms = computed(() => contentTotals.value
  .slice(0, props.trendLimit)
  .map(([term]) => term))

const contentTrendValues = computed(() => {
  const values = new Map<string, Map<string, number>>()
  for (const period of displayPeriods.value) values.set(period, new Map())
  for (const item of selectedMonthlyItems.value) {
    const bucket = props.grain === "month" ? item.period : item.period.slice(0, 4)
    const periodValues = values.get(bucket)
    if (!periodValues) continue
    periodValues.set(item.term, (periodValues.get(item.term) || 0) + item.count)
  }
  return values
})

const contentPeriodTotals = computed(() => {
  const totals = new Map<string, number>()
  for (const period of availablePeriods.value) {
    const bucket = props.grain === "month" ? period : period.slice(0, 4)
    totals.set(bucket, (totals.get(bucket) || 0) + Number(index.value?.period_totals?.[period] || 0))
  }
  return totals
})

const contentGroupCards = computed(() => {
  const definitions = (index.value?.content_groups || []) as ContentGroupDefinition[]
  const counts = new Map<string, number>()
  const termCounts = new Map<string, Map<string, number>>()
  for (const [period, groupId, count] of groupRows.value) {
    if (period < props.fromPeriod || period > props.toPeriod) continue
    counts.set(groupId, (counts.get(groupId) || 0) + count)
  }
  for (const [period, groupId, term, count] of groupTermRows.value) {
    if (period < props.fromPeriod || period > props.toPeriod) continue
    if (!termCounts.has(groupId)) termCounts.set(groupId, new Map())
    const values = termCounts.get(groupId)!
    values.set(term, (values.get(term) || 0) + count)
  }
  const periodTotals = index.value?.period_totals || {}
  const rangeTotal = Object.entries(periodTotals)
    .filter(([period]) => period >= props.fromPeriod && period <= props.toPeriod)
    .reduce((sum, [, value]) => sum + Number(value || 0), 0)
  const currentStart = shiftMonth(props.toPeriod, -11)
  const previousStart = shiftMonth(props.toPeriod, -23)
  const previousEnd = shiftMonth(props.toPeriod, -12)
  const groupWindowCount = (groupId: string, start: string, end: string) => groupRows.value
    .filter(row => row[0] >= start && row[0] <= end && row[1] === groupId)
    .reduce((sum, row) => sum + row[2], 0)
  const totalWindowCount = (start: string, end: string) => Object.entries(periodTotals)
    .filter(([period]) => period >= start && period <= end)
    .reduce((sum, [, value]) => sum + Number(value || 0), 0)
  const currentTotal = totalWindowCount(currentStart, props.toPeriod)
  const previousTotal = totalWindowCount(previousStart, previousEnd)

  return definitions.map(group => {
    const count = counts.get(group.id) || 0
    const minimumTermCount = aggregateItemDisplayMinimum(
      count,
      index.value?.content_group_metadata?.item_display_rule,
    )
    const currentShare = currentTotal ? groupWindowCount(group.id, currentStart, props.toPeriod) / currentTotal * 100 : 0
    const previousShare = previousTotal ? groupWindowCount(group.id, previousStart, previousEnd) / previousTotal * 100 : 0
    const terms = [...(termCounts.get(group.id) || new Map())]
      .filter(([, termCount]) => termCount >= minimumTermCount)
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "zh-CN"))
    return {
      ...group,
      count,
      share: rangeTotal ? count / rangeTotal * 100 : 0,
      shareDelta: currentTotal && previousTotal ? currentShare - previousShare : null,
      topTerms: terms,
    }
  }).sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, "zh-CN"))
})

const contentGroupDisplayCards = computed(() => contentGroupCards.value.map(group => ({
  id: group.id,
  label: group.label,
  description: group.description,
  count: group.count,
  share: group.share,
  shareDelta: group.shareDelta,
  items: group.topTerms.map(([term, count]) => ({
    key: term,
    label: term,
    count,
    clickable: groupTermHasDetail(term),
  })),
})))

const contentMomentum = computed<{ rising: ContentMomentumItem[]; falling: ContentMomentumItem[] }>(() => {
  if (!props.toPeriod) return { rising: [], falling: [] }
  const currentStart = shiftMonth(props.toPeriod, -11)
  const previousStart = shiftMonth(props.toPeriod, -23)
  const previousEnd = shiftMonth(props.toPeriod, -12)
  const currentCounts = new Map<string, number>()
  const previousCounts = new Map<string, number>()
  for (const item of evolutionMonthlyItems.value) {
    if (item.period >= currentStart && item.period <= props.toPeriod) {
      currentCounts.set(item.term, (currentCounts.get(item.term) || 0) + item.count)
    } else if (item.period >= previousStart && item.period <= previousEnd) {
      previousCounts.set(item.term, (previousCounts.get(item.term) || 0) + item.count)
    }
  }
  const periodTotals = index.value?.period_totals || {}
  const currentTotal = Object.entries(periodTotals)
    .filter(([period]) => period >= currentStart && period <= props.toPeriod)
    .reduce((sum, [, total]) => sum + Number(total || 0), 0)
  const previousTotal = Object.entries(periodTotals)
    .filter(([period]) => period >= previousStart && period <= previousEnd)
    .reduce((sum, [, total]) => sum + Number(total || 0), 0)
  if (!currentTotal || !previousTotal) return { rising: [], falling: [] }
  const values = [...currentCounts].map(([term, count]) => ({
    term,
    count,
    delta: count / currentTotal * 100 - (previousCounts.get(term) || 0) / previousTotal * 100,
  })).filter(item => item.count >= 20)
  return {
    rising: [...values].filter(item => item.delta > 0)
      .sort((left, right) => right.delta - left.delta || right.count - left.count).slice(0, 20),
    falling: [...values].filter(item => item.delta < 0)
      .sort((left, right) => left.delta - right.delta || right.count - left.count).slice(0, 20),
  }
})

const contentEvolutionColumns = computed<RankedColumn[]>(() => [
  {
    key: "hot", title: "热点关键词", items: contentTotals.value.slice(0, 20).map(([term, count]) => ({
      key: term, label: term, value: formatNumber(count), action: `term:${term}`,
    })),
  },
  {
    key: "rising", title: "上升关键词", items: contentMomentum.value.rising.map(item => ({
      key: item.term, label: item.term, value: `+${item.delta.toFixed(2)}pp`, action: `term:${item.term}`,
    })),
  },
  {
    key: "falling", title: "下降关键词", items: contentMomentum.value.falling.map(item => ({
      key: item.term, label: item.term, value: `${item.delta.toFixed(2)}pp`, action: `term:${item.term}`,
    })),
  },
])

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

const rankedTermOptions = computed(() => Object.entries(index.value?.terms || {})
  .map(([term, raw]) => {
    const entry = raw as any
    return {
      value: term,
      label: term,
      total: Number(entry.total || 0),
      meta: `${formatNumber(entry.total)} 个标题 · ${entry.first_period} 至 ${entry.last_period}`,
    }
  })
  .sort((left, right) => right.total - left.total || left.label.localeCompare(right.label, "zh-CN")))
const searchOptions = computed<SearchOption[]>(() => rankedTermOptions.value
  .map(({ value, label, meta }) => ({ value, label, meta })))
const comparisonOptions = computed<SearchOption[]>(() => rankedTermOptions.value
  .map(({ value, label, meta }) => ({ value, label, meta })))

function rowsForDetail(rawDetail: any): HotspotItem[] {
  return ((rawDetail?.rows || []) as HotspotRow[])
    .map(toItem)
    .filter((item: HotspotItem) => item.period >= props.fromPeriod && item.period <= props.toPeriod)
}

function annualRowsForDetail(rawDetail: any): HotspotItem[] {
  return ((rawDetail?.annual_rows || []) as HotspotRow[]).map(toItem)
}

function buildDetailSeries(term: string, rawDetail: any): HotspotItem[] {
  const termRows = rowsForDetail(rawDetail)
  const source = new Map(termRows.map((item: HotspotItem) => [item.period, item]))
  if (props.grain === "month") return availablePeriods.value.map(period => source.get(period) || {
    period, term, count: 0, authors: 0, nodes: 0, share: 0, burst: 0, score: 0,
    tagCount: 0, contentRank: 0, tagRank: 0, isNew: false,
  })
  const annualSource = new Map(annualRowsForDetail(rawDetail).map(item => [item.period, item]))
  return displayPeriods.value.map(period => {
    const values = termRows.filter((item: HotspotItem) => item.period.startsWith(period))
    const annual = annualSource.get(period)
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
    title: relationMode.value === "terms" ? "关联关键词" : "关联话题",
    items: (relationMode.value === "terms" ? detail.value.related_terms || [] : detail.value.topics || [])
      .slice(0, 20)
      .map((item: any[]) => ({
        key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`,
        action: relationMode.value === "terms" ? `term:${item[0]}` : `tag:${item[0]}`,
      })),
  },
  {
    key: "nodes", title: "主要节点", items: (detail.value.nodes || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: props.nodeLabel(item[0]), value: `${formatNumber(item[1])} 帖子`, action: `node:${item[0]}`,
    })),
  },
  {
    key: "authors", title: "活跃用户", items: (detail.value.authors || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`, action: `member:${item[0]}`,
    })),
  },
] : [])

function contentPostPeriod(post: ContentPost) {
  if (post.period) return post.period
  return new Date(post.create_at * 1000)
    .toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" })
    .slice(0, 7)
}

const detailPeriodOptions = computed(() => {
  if (!detail.value) return [""]
  const periods = new Set<string>()
  for (const row of detail.value.rows || []) {
    const month = String(row[0] || "")
    if (month < props.fromPeriod || month > props.toPeriod || Number(row[2] || 0) <= 0) continue
    periods.add(props.grain === "month" ? month : month.slice(0, 4))
  }
  return [...periods].sort().concat("")
})
const detailPeriodLabels = { "": "全部区间" }

const detailPosts = computed<ContentPost[]>(() => {
  const candidates = props.grain === "month" && props.selectedPeriod
    ? periodPosts.value
    : detail.value?.posts || []
  return candidates
    .filter((post: ContentPost) => {
      const period = contentPostPeriod(post)
      return period >= props.fromPeriod && period <= props.toPeriod
    })
    .filter((post: ContentPost) => (
      !props.selectedPeriod
      || (props.grain === "month" ? contentPostPeriod(post) : contentPostPeriod(post).slice(0, 4)) === props.selectedPeriod
    ))
    .sort((a: ContentPost, b: ContentPost) => b.score - a.score || b.create_at - a.create_at)
})
const detailPostsTitle = computed(() => props.selectedPeriod
  ? `${props.selectedPeriod} 代表帖子`
  : "代表帖子")
const detailPostsDescription = computed(() => {
  if (!props.selectedPeriod) {
    return "每年保留综合互动得分最高的 10 个相关帖子，当前按互动得分排序并分页展示。"
  }
  return props.grain === "month"
    ? "按综合互动得分展示该月代表帖子：相关帖子不少于 100 个时显示 Top 10，不少于 20 个时显示 Top 5，其余显示 Top 3。"
    : "按综合互动得分展示该自然年 Top 10；再次点击实心圆点或选择全部区间可恢复。"
})
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
        return `<strong>${displayPeriods.value[item[0]]} · ${item[3]}</strong><br>相关帖子：${formatNumber(item[4])} · 排名 ${contentRank}<br>同期占比：${Number(item[8]).toFixed(2)}%<br>${authorLabel}：${formatNumber(item[5])}<br>节点：${formatNumber(item[6])}<br>相对热度：${item[7] > 0 ? "+" : ""}${Number(item[7]).toFixed(2)}`
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

async function renderContentTrend() {
  const renderId = ++contentTrendRenderId
  await nextTick()
  const element = document.getElementById("content-hotspot-trend")
  if (!element) return
  const runtime = await ensureRuntime()
  if (renderId !== contentTrendRenderId || !element.isConnected) return
  if (!contentTrendChart || contentTrendChart.getDom() !== element) {
    contentTrendChart?.dispose()
    contentTrendChart = runtime.initChart(element)
  }
  const terms = contentTrendTerms.value
  const periods = displayPeriods.value
  const targetLabels = element.clientWidth <= 680 ? 5 : 12
  const labelStep = Math.max(1, Math.ceil(periods.length / targetLabels))
  const legendLayout = wrappedLegendLayout(element, terms)
  contentTrendChart.resize()
  contentTrendChart.setOption({
    aria: { enabled: true }, animation: false, color: categoricalColors,
    tooltip: {
      trigger: "axis", confine: true,
      axisPointer: { type: "line", lineStyle: { color: chartTheme.pointer, width: 1 } },
      formatter: (params: any[]) => {
        const items = [...params].sort((left, right) => Number(right.value) - Number(left.value))
        const total = contentPeriodTotals.value.get(String(items[0]?.axisValue || "")) || 0
        const values = items.map(item => {
          const count = Number(item.value || 0)
          const share = count / Math.max(1, total) * 100
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:10px;min-width:135px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${formatNumber(count)} <small style="color:#667085;font-weight:400">${share.toFixed(2)}%</small></strong></span>`
        }).join("")
        return `<div style="min-width:300px"><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 16px;margin-top:8px">${values}</div></div>`
      },
    },
    legend: legendLayout.option,
    grid: { top: 24, right: 24, bottom: legendLayout.gridBottom, left: 68 },
    xAxis: {
      type: "category", boundaryGap: false, data: periods,
      axisLabel: {
        color: chartTheme.axis, fontSize: 10, hideOverlap: false, showMinLabel: true, showMaxLabel: true,
        interval: (index: number) => index === 0 || index === periods.length - 1 || index % labelStep === 0,
      },
      axisLine: { lineStyle: { color: chartTheme.axisLine } },
    },
    yAxis: {
      type: "value", name: "帖子数", min: 0,
      nameTextStyle: { color: chartTheme.axis, fontSize: 11 },
      axisLabel: { color: chartTheme.axis, fontSize: 10 },
      splitLine: { lineStyle: { color: chartTheme.gridLine } },
    },
    series: terms.map((term, index) => ({
      name: term,
      type: "line",
      data: periods.map(period => contentTrendValues.value.get(period)?.get(term) || 0),
      showSymbol: false,
      symbolSize: 7,
      lineStyle: { color: categoricalColors[index], width: 2 },
      itemStyle: { color: categoricalColors[index] },
      emphasis: { focus: "series", lineStyle: { width: 4 } },
    })),
  } as any, true)
  contentTrendChart.off("click")
  contentTrendChart.on("click", (params: any) => {
    if (params.seriesName) selectTerm(params.seriesName)
  })
  clearLegendHoverAfterSelection(contentTrendChart)
  contentTrendChart.resize()
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
  const selectablePeriods = new Set(detailPeriodOptions.value)
  const legendLayout = seriesDetails.length > 1
    ? wrappedLegendLayout(element, seriesDetails.map(item => item.name))
    : null
  if (!legendLayout) element.style.height = "300px"
  element.dataset.selectedPeriod = props.selectedPeriod
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
    yAxis: { type: "value", name: "帖子数", axisLabel: { color: chartTheme.axis, fontSize: 10 }, splitLine: { lineStyle: { color: chartTheme.gridLine } } },
    series: seriesDetails.map(item => {
      const values = seriesValues.get(item.name) || []
      return {
        name: item.name,
        type: "line",
        showSymbol: item.main || periods.length <= 24,
        symbol: "circle",
        symbolSize: 6,
        smooth: false,
        cursor: item.main ? "pointer" : "default",
        data: values.map(point => {
          if (!item.main) return point.count
          const selected = props.selectedPeriod === point.period
          const selectable = point.count > 0 && selectablePeriods.has(point.period)
          return {
            value: point.count,
            symbolSize: selectable ? (selected ? 9 : 5) : 0,
            itemStyle: {
              color: selected ? item.color : "#ffffff",
              borderColor: item.color,
              borderWidth: selected ? 2 : 1.5,
            },
            emphasis: {
              scale: 1.3,
              itemStyle: {
                color: selected ? item.color : "#ffffff",
                borderColor: item.color,
                borderWidth: 2,
              },
            },
          }
        }),
        lineStyle: { width: item.main ? 3 : 2.2, color: item.color },
        itemStyle: { color: item.color },
        areaStyle: item.main && seriesDetails.length === 1 ? { color: "rgba(217,72,65,.08)" } : undefined,
        emphasis: { focus: "series", lineStyle: { width: item.main ? 4 : 3.5 } },
      }
    }),
  } as any, true)
  clearLegendHoverAfterSelection(trendChart)
  trendChart.off("click")
  trendChart.on("click", (params: any) => {
    const period = String(params.name || "")
    if (
      params.componentType === "series"
      && params.seriesName === props.selectedTerm
      && selectablePeriods.has(period)
    ) {
      scrollToPostsAfterPeriodChange = true
      emit("update:selectedPeriod", props.selectedPeriod === period ? "" : period)
    }
  })
  trendChart.resize()
}

async function loadRows() {
  if (props.mode !== "evolution") return
  if (!index.value || !props.fromPeriod || !props.toPeriod) return
  const requestId = ++rowsRequestId
  const initialLoad = rows.value.length === 0
  if (initialLoad) loading.value = true
  error.value = ""
  try {
    const momentumStart = shiftMonth(props.toPeriod, -23)
    const loadFrom = props.fromPeriod < momentumStart ? props.fromPeriod : momentumStart
    const start = Number(loadFrom.slice(0, 4))
    const end = Number(props.toPeriod.slice(0, 4))
    const years = Array.from({ length: end - start + 1 }, (_, offset) => String(start + offset))
    await Promise.all(years.map(async year => {
      if (yearCache.has(year) || !index.value.year_shards?.[year]) return
      const payload = await getJson(index.value.year_shards[year])
      yearCache.set(year, {
        rows: payload.rows || [],
        annualRows: payload.annual_rows || [],
        groupRows: payload.group_rows || [],
        groupTermRows: payload.group_term_rows || [],
      })
    }))
    if (requestId !== rowsRequestId) return
    rows.value = years.flatMap(year => yearCache.get(year)?.rows || [])
    annualRows.value = years.flatMap(year => yearCache.get(year)?.annualRows || [])
    groupRows.value = years.flatMap(year => yearCache.get(year)?.groupRows || [])
    groupTermRows.value = years.flatMap(year => yearCache.get(year)?.groupTermRows || [])
  } catch (cause) {
    if (requestId === rowsRequestId) error.value = cause instanceof Error ? cause.message : "标题关键词演变加载失败"
  } finally {
    if (requestId === rowsRequestId && initialLoad) loading.value = false
  }
  if (requestId !== rowsRequestId) return
  await nextTick()
  await renderHeatmap()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  if (requestId === rowsRequestId) await renderContentTrend()
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

async function getPeriodPostBucket(bucket: string) {
  const cached = periodPostCache.get(bucket)
  if (cached) return cached
  let request = periodPostRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-content-period-posts-${bucket}.json`)
      .then(payload => {
        periodPostCache.set(bucket, payload)
        return payload
      })
      .finally(() => periodPostRequests.delete(bucket))
    periodPostRequests.set(bucket, request)
  }
  return request
}

async function loadPeriodPosts(period = props.selectedPeriod) {
  const requestId = ++periodPostRequestId
  periodPostsError.value = ""
  if (props.grain !== "month" || !props.selectedTerm || !period) {
    periodPosts.value = []
    periodPostsLoading.value = false
    return
  }
  const entry = index.value?.terms?.[props.selectedTerm]
  if (!entry?.period_post_bucket) {
    periodPosts.value = []
    periodPostsLoading.value = false
    return
  }
  periodPostsLoading.value = true
  try {
    const payload = await getPeriodPostBucket(entry.period_post_bucket)
    if (requestId === periodPostRequestId) {
      periodPosts.value = payload.posts?.[props.selectedTerm]?.[period] || []
    }
  } catch {
    if (requestId === periodPostRequestId) {
      periodPosts.value = []
      periodPostsError.value = "该月代表帖子加载失败，请稍后重试。"
    }
  } finally {
    if (requestId === periodPostRequestId) periodPostsLoading.value = false
  }
}

async function loadDetail(term: string) {
  if (props.mode !== "detail") return
  const requestId = ++detailRequestId
  postPage.value = 1
  if (!term || !index.value?.terms?.[term]) {
    detail.value = null
    return
  }
  detailLoading.value = true
  try {
    const termDetail = await getTermDetail(term)
    if (requestId === detailRequestId) {
      detail.value = termDetail
      let period = props.selectedPeriod
      if (period && !detailPeriodOptions.value.includes(period)) {
        period = ""
        emit("update:selectedPeriod", "")
      }
      await loadPeriodPosts(period)
    }
  } catch (cause) {
    if (requestId === detailRequestId) error.value = cause instanceof Error ? cause.message : "标题关键词详情加载失败"
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
    if (requestId === comparisonRequestId) comparisonError.value = "对比关键词加载失败，请稍后重试。"
  } finally {
    if (requestId === comparisonRequestId) comparisonLoading.value = false
  }
  if (requestId === comparisonRequestId) await renderTrend()
}

function selectTerm(term: string) {
  if (!term) return
  if (props.mode === "evolution") {
    emit("openDetail", term)
    return
  }
  emit("update:selectedTerm", term)
}

function groupTermHasDetail(term: string) {
  return Boolean(index.value?.terms?.[term])
}

function selectRankedItem(item: RankedItem) {
  if (item.action?.startsWith("term:")) selectTerm(item.action.slice(5))
  else if (item.action?.startsWith("tag:")) emit("topic", item.action.slice(4))
  else if (item.action?.startsWith("node:")) emit("node", item.action.slice(5))
  else if (item.action?.startsWith("member:")) emit("member", item.action.slice(7))
}

function handleResize() {
  heatmapChart?.resize()
  contentTrendChart?.resize()
  trendChart?.resize()
}

watch(() => [props.fromPeriod, props.toPeriod], async () => {
  if (props.mode === "evolution") await loadRows()
  else {
    postPage.value = 1
    await renderTrend()
  }
})
watch(() => props.grain, async () => {
  if (props.mode === "evolution") {
    await renderHeatmap()
    await renderContentTrend()
  } else await renderTrend()
})
watch(() => props.topLimit, async () => {
  if (props.mode === "evolution") await renderHeatmap()
})
watch(() => props.trendLimit, async () => {
  if (props.mode === "evolution") await renderContentTrend()
})
watch(() => props.selectedTerm, term => {
  if (props.mode !== "detail" || mountingDetail) return
  if (props.comparedTerms.includes(term)) {
    emit("update:comparedTerms", props.comparedTerms.filter(value => value !== term))
  }
  loadDetail(term)
})
watch(() => props.comparedTerms, values => {
  if (props.mode === "detail") loadComparisonDetails(values)
})
watch(() => props.selectedPeriod, async period => {
  if (props.mode !== "detail" || mountingDetail) return
  postPage.value = 1
  await loadPeriodPosts(period)
  await nextTick()
  await renderTrend()
  if (scrollToPostsAfterPeriodChange) {
    scrollToPostsAfterPeriodChange = false
    await nextTick()
    scrollToSection("content-representative-posts")
  }
})
watch(detailPosts, () => { postPage.value = Math.min(postPage.value, postPageCount.value) })

onMounted(async () => {
  window.addEventListener("resize", handleResize)
  try {
    index.value = await getJson("dynamic-content-hotspots-index.json")
    if (props.mode === "evolution") {
      await loadRows()
    } else {
      mountingDetail = true
      const selected = index.value.terms?.[props.selectedTerm]
        ? props.selectedTerm
        : rankedTermOptions.value[0]?.value || ""
      if (selected !== props.selectedTerm) emit("update:selectedTerm", selected)
      await nextTick()
      loading.value = false
      await nextTick()
      await loadDetail(selected)
      await loadComparisonDetails()
      mountingDetail = false
    }
  } catch (cause) {
    mountingDetail = false
    error.value = cause instanceof Error ? cause.message : "标题关键词视图加载失败"
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize)
  heatmapChart?.dispose()
  contentTrendChart?.dispose()
  trendChart?.dispose()
})
</script>

<template>
  <section class="view-section content-hotspots-view">
    <PageHeader
      :title="mode === 'evolution' ? '标题关键词演变' : '标题关键词详情'"
      :description="mode === 'evolution'
        ? '按帖子标题中的高频词观察产品、事件和概念随时间的变化。'
        : '选择标题关键词，查看其规模、趋势、关联结构和代表帖子。'"
    />

    <div v-if="loading" class="loading profile-loading"><span class="loading-spinner"></span><span>正在加载{{ mode === 'evolution' ? '标题关键词演变' : '标题关键词详情' }}</span></div>
    <div v-else-if="error" class="empty-state">{{ error }}</div>
    <template v-else>
      <template v-if="mode === 'evolution'">
        <ViewSectionNav :items="[
          { id: 'content-evolution-panel', label: '关键词排名' },
          { id: 'content-trend-panel', label: '关键词趋势' },
          { id: 'content-groups-panel', label: '关键词板块' },
        ]" />
        <article id="content-evolution-panel" class="analysis-block full section-anchor">
          <header class="block-header-with-control">
            <div><h2>逐期关键词排名</h2><p>按标题包含各关键词的帖子数展示每期 Top；同一帖子对同一关键词只计一次。</p></div>
            <div class="segmented compact-segmented" aria-label="关键词排名数量">
              <button :class="{ active: topLimit === 10 }" @click="emit('update:topLimit', 10)">Top 10</button>
              <button :class="{ active: topLimit === 20 }" @click="emit('update:topLimit', 20)">Top 20</button>
              <button :class="{ active: topLimit === 30 }" @click="emit('update:topLimit', 30)">Top 30</button>
            </div>
          </header>
          <div id="content-hotspot-heatmap" class="chart content-hotspot-heatmap" :style="{ height: `${Math.max(360, 112 + topLimit * 30)}px` }"></div>
          <p class="method-note">颜色表示相关帖子数量；热点关键词按筛选区间累计，上升与下降关键词按截至结束月份的最近 12 个月相较此前 12 个月的帖子占比变化排序，至少包含 20 个相关帖子。自动分词已过滤推广节点、交易描述、问句模板及高频泛词；达到基础频次的人工确认实体可在详情中搜索，但不改变逐期 Top 排名。点击条目进入标题关键词详情。</p>
          <RankedColumns :columns="contentEvolutionColumns" @select="selectRankedItem" />
        </article>

        <article id="content-trend-panel" class="analysis-block full section-anchor">
          <header class="block-header-with-control">
            <div><h2>关键词趋势</h2><p>展示筛选区间内出现次数最高的标题关键词变化；点击折线可进入标题关键词详情。</p></div>
            <div class="segmented compact-segmented" aria-label="关键词趋势数量">
              <button :class="{ active: trendLimit === 10 }" @click="emit('update:trendLimit', 10)">Top 10</button>
              <button :class="{ active: trendLimit === 20 }" @click="emit('update:trendLimit', 20)">Top 20</button>
              <button :class="{ active: trendLimit === 30 }" @click="emit('update:trendLimit', 30)">Top 30</button>
            </div>
          </header>
          <div id="content-hotspot-trend" class="chart tall" :data-latest-period="displayPeriods[displayPeriods.length - 1] || ''"></div>
        </article>

        <article id="content-groups-panel" class="analysis-block full aggregate-group-panel content-group-section section-anchor">
          <header>
            <h2>关键词板块</h2>
            <p>将标题关键词按固定词表归入可复核板块，补充单个关键词之外的结构视角。</p>
          </header>
          <AggregateGroupCards
            embedded
            :cards="contentGroupDisplayCards"
            count-label="相关帖子"
            item-label="关键词"
            empty-text="暂无达到门槛的关键词"
            @select="selectTerm"
          />
          <p class="method-note content-group-note">板块帖子数对同一帖子去重，但一个标题可同时进入多个板块，因此各板块数量不可相加。关键词至少出现 3 次且达到本板块帖子数的 1%，或绝对出现次数达到 100，即予显示；符合条件的关键词不再固定截断。推广、交易和免费赠送等节点已排除。</p>
        </article>
      </template>

      <article v-else-if="selectedTerm" id="content-term-detail" class="analysis-block full topic-detail-block content-term-detail">
        <header class="block-header-with-control">
          <div><h2>标题关键词详情：{{ selectedTerm }}</h2><p>趋势与规模使用当前筛选范围；关联关键词、关联话题、主要节点和活跃用户按全历史累计。</p></div>
          <SearchSelect v-model="selectedTermModel" class="topic-detail-select" label="选择标题关键词" icon="tag" hide-label :options="searchOptions" />
        </header>
        <div v-if="detailLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="detail">
          <div class="metric-grid four topic-detail-metrics">
            <article class="metric"><span>相关帖子</span><strong>{{ formatNumber(detailStats.total) }}</strong><em>标题包含该词</em></article>
            <article class="metric"><span>区间占比</span><strong>{{ detailStats.share.toFixed(2) }}%</strong><em>占有效帖子</em></article>
            <article class="metric"><span>活跃峰值</span><strong class="metric-date">{{ detailStats.peak }}</strong><em>相关帖子最多</em></article>
            <article class="metric"><span>最新关键词排名</span><strong>{{ detailStats.contentRank ? `#${formatNumber(detailStats.contentRank)}` : '未入榜' }}</strong><em>{{ grain === 'month' ? '当月' : '当年' }}关键词排名</em></article>
          </div>
          <section class="topic-detail-trend">
            <header class="detail-trend-header">
              <div><h3>{{ selectedTerm }} 关键词趋势</h3><p>展示所选区间内标题包含各关键词的帖子数量；主关键词空心圆点可筛选同期代表帖子，实心圆点表示当前选择。</p></div>
              <ComparisonSelect v-model="comparedTermsModel" label="对比关键词" :options="comparisonOptions" :exclude="[selectedTerm]" :loading="comparisonLoading" />
            </header>
            <p v-if="comparisonError" class="comparison-error">{{ comparisonError }}</p>
            <div id="content-term-trend" class="chart compact-chart"></div>
          </section>
          <p class="topic-detail-scope-note">全历史共有 {{ formatNumber(detail.total) }} 个帖子标题包含“{{ selectedTerm }}”。关联关键词表示同一标题包含两个关键词的帖子数；关联话题表示相关帖子携带该话题的数量，以下各栏最多显示 Top 20。</p>
          <div class="content-relation-toolbar">
            <span>关联维度</span>
            <div class="segmented compact-segmented" aria-label="关键词关联维度">
              <button :class="{ active: relationMode === 'terms' }" @click="relationMode = 'terms'">关联关键词</button>
              <button :class="{ active: relationMode === 'topics' }" @click="relationMode = 'topics'">关联话题</button>
            </div>
          </div>
          <RankedColumns :columns="detailColumns" @select="selectRankedItem" />
          <section id="content-representative-posts" class="topic-detail-posts content-hotspot-posts representative-posts-anchor">
            <header class="content-section-header">
              <div><h3>{{ detailPostsTitle }}</h3><p>{{ detailPostsDescription }}</p></div>
              <PeriodSelect
                v-model="selectedPeriodModel"
                class="topic-post-period-select"
                label="代表帖子时间"
                hide-label
                :periods="detailPeriodOptions"
                :option-labels="detailPeriodLabels"
              />
            </header>
            <div v-if="periodPostsLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
            <p v-else-if="periodPostsError" class="empty-state compact-empty">{{ periodPostsError }}</p>
            <div v-else class="post-list content-representative-list">
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
              <div v-if="!detailPosts.length" class="empty-state compact-empty">当前筛选范围内没有该标题关键词的代表帖子。</div>
              <footer v-else-if="detailPosts.length > pageSize" class="ranking-pagination detail-pagination">
                <span>共 {{ formatNumber(detailPosts.length) }} 帖 · 第 {{ postPage }} / {{ postPageCount }} 页</span>
                <nav aria-label="标题关键词代表帖子分页">
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
.content-group-section { margin-bottom: 16px; }
.content-group-note { margin-top: 12px; }
@media (max-width: 680px) {
  .content-hotspot-heatmap { min-height: 360px; }
  .content-term-detail .block-header-with-control { align-items: stretch; }
  .content-term-detail .topic-detail-select { width: 100%; }
}
</style>
