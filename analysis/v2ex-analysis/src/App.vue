<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import { CalendarRange, ChevronDown, SlidersHorizontal } from "@lucide/vue"
import AggregateGroupTrend from "./components/AggregateGroupTrend.vue"
import AggregateGroupCards from "./components/AggregateGroupCards.vue"
import ComparisonSelect from "./components/ComparisonSelect.vue"
import DashboardFooter from "./components/DashboardFooter.vue"
import DashboardHeader from "./components/DashboardHeader.vue"
import GlobalEntitySearch from "./components/GlobalEntitySearch.vue"
import GroupedSubtabNav from "./components/GroupedSubtabNav.vue"
import LoadingState from "./components/LoadingState.vue"
import MonthlyDataView from "./components/MonthlyDataView.vue"
import PageHeader from "./components/PageHeader.vue"
import PeriodSelect from "./components/PeriodSelect.vue"
import RankedColumns from "./components/RankedColumns.vue"
import RepresentativeComments from "./components/RepresentativeComments.vue"
import SearchSelect from "./components/SearchSelect.vue"
import SubtabNav from "./components/SubtabNav.vue"
import ViewSectionNav from "./components/ViewSectionNav.vue"
import { clearJsonCache, getJson } from "./services/dataClient"
import { aggregateItemDisplayMinimum } from "./utils/aggregateGroups"
import { paginationItems } from "./utils/pagination"
import { buildPeriodInsights } from "./utils/periodInsights"
import { commentsForPeriod, commentsForRange } from "./utils/representativeComments"
import { clearLegendHoverAfterSelection, responsiveChartSides, wrappedLegendLayout } from "./utils/chartLayout"
import { scrollToSection } from "./utils/scroll"
import { formatDateTime, formatNumber } from "./utils/format"
import {
  dashboardQueryKeys,
  integerParam,
  safeComparisonParams,
  safeMemberParam,
  safeNodeParam,
  safeTagParam,
} from "./utils/dashboardUrl"
import type { DashboardChart } from "./chartRuntime"
import { categoricalColors, chartTheme, comparisonColors, heatmapColors } from "./chartTheme"
import type {
  CommunityView, ContentView, Grain, MemberRankingMetric, OverviewView,
  PeriodMetric, RankedColumn, RankedItem, RepresentativeComment,
  RepresentativeCommentSummary, RepresentativePost,
  SearchOption, TabId,
} from "./types/analytics"

const NodeDetailView = defineAsyncComponent(() => import("./views/NodeDetailView.vue"))
const ContentHotspotsView = defineAsyncComponent(() => import("./views/ContentHotspotsView.vue"))
const AnalysisCatalogView = defineAsyncComponent(() => import("./views/AnalysisCatalogView.vue"))
const ObservationsView = defineAsyncComponent(() => import("./views/ObservationsView.vue"))
const AboutView = defineAsyncComponent(() => import("./views/AboutView.vue"))
const EngagementView = defineAsyncComponent(() => import("./views/EngagementView.vue"))
const OverviewTrendView = defineAsyncComponent(() => import("./views/OverviewTrendView.vue"))
const ScaleDistributionView = defineAsyncComponent(() => import("./views/ScaleDistributionView.vue"))
const LifecycleView = defineAsyncComponent(() => import("./views/LifecycleView.vue"))

const tabs: { id: TabId; label: string }[] = [
  { id: "overview", label: "概览" },
  { id: "content", label: "帖子" },
  { id: "community", label: "成员" },
  { id: "engagement", label: "互动" },
  { id: "observations", label: "观察" },
]

const activeTab = ref<TabId>("overview")
const loading = ref(true)
const tabLoading = ref(false)
const overview = shallowRef<any>({ periods: [], activity: [], metadata: {} })
const topics = shallowRef<any>({
  tags: [], rows: [], groups: [], group_rows: [], group_topic_rows: [], group_topic_match_rows: [],
})
const tagDetailIndex = shallowRef<any>({ tags: {} })
const selectedTagDetail = shallowRef<any>(null)
const tagDetailLoading = ref(false)
const nodes = shallowRef<any>({ rows: [] })
const nodeDetailIndex = shallowRef<any>({ criteria: {}, nodes: {} })
const nodeLabels = shallowRef<Record<string, string>>({})
const analyzedNodeNames = shallowRef<Set<string>>(new Set())
const selectedNode = ref("")
const selectedNodeDetail = shallowRef<any>(null)
const nodeDetailLoading = ref(false)
const selectedNodeDetailPeriod = ref("")
const nodePeriodPosts = shallowRef<RepresentativePost[]>([])
const nodePeriodPostsLoading = ref(false)
const nodePeriodPostsError = ref("")
const nodePeriodComments = shallowRef<RepresentativeComment[]>([])
const nodePeriodCommentSummary = shallowRef<RepresentativeCommentSummary>({})
const nodePeriodCommentsLoading = ref(false)
const nodePeriodCommentsError = ref("")
const lifecycle = shallowRef<any>({ first_reply_rows: [], comment_age_rows: [], long_tail_rows: [], discussion_structure_rows: [] })
const community = shallowRef<any>({ rows: [], rank_rows: [], top_topic_authors: [], top_commenters: [], top_thanked: [] })
const memberProfileIndex = shallowRef<any>({ criteria: {}, members: {} })
const selectedMember = ref("")
const selectedMemberProfile = shallowRef<any>(null)
const memberProfileLoading = ref(false)
const selectedMemberComments = shallowRef<any[]>([])
const memberCommentsLoading = ref(false)
const memberPostsExpanded = ref(false)
const memberCommentsExpanded = ref(false)
const engagement = shallowRef<any>({ rows: [], top_posts: {}, top_comments: [] })
const observations = shallowRef<any>({ metadata: {}, headline: { metrics: [] }, observations: [], notes: [] })
const loadedData = new Set<string>()
const contentView = ref<ContentView>("topics")
const overviewView = ref<OverviewView>("trend")
const aboutView = ref<"about" | "catalog">("about")
const catalogType = ref<"topics" | "content" | "nodes">("topics")
const catalogSort = ref<"count" | "name">("count")
const catalogGroup = ref("")
const overviewActivityMetric = ref<"topics" | "comments">("comments")
const communityView = ref<CommunityView>("trends")
const fromPeriod = ref("")
const toPeriod = ref("")
const grain = ref<Grain>("month")
const topLimit = ref(20)
const trendLimit = ref(10)
const nodeTrendLimit = ref(10)
const memberRankingMetric = ref<MemberRankingMetric>("topics")
const memberRankingLimit = ref(20)
const selectedTag = ref("")
const comparedTags = ref<string[]>([])
const selectedTopicDetailPeriod = ref("")
const topicPeriodPosts = shallowRef<RepresentativePost[]>([])
const topicPeriodPostsLoading = ref(false)
const topicPeriodPostsError = ref("")
const topicPeriodComments = shallowRef<RepresentativeComment[]>([])
const topicPeriodCommentSummary = shallowRef<RepresentativeCommentSummary>({})
const topicPeriodCommentsLoading = ref(false)
const topicPeriodCommentsError = ref("")
const topicRelationMode = ref<"topics" | "content">("topics")
const selectedContentTerm = ref("")
const comparedContentTerms = ref<string[]>([])
const selectedContentDetailPeriod = ref("")
const contentHotspotLimit = ref(20)
const contentTrendLimit = ref(10)
const selectedPeriod = ref("")
const monthlyDataLoading = ref(false)
const monthlyRankings = shallowRef<Record<string, any>>({})
const selectedYear = ref("")
const annualDataLoading = ref(false)
const annualRankings = shallowRef<Record<string, any>>({})
const communityEvents = shallowRef<any[]>([])
const interactionRanking = ref<"favorite_count" | "thank_count" | "votes" | "clicks">("favorite_count")
const topicDetailPostPage = ref(1)
const postRankingPage = ref(1)
const commentRankingPage = ref(1)
const filterExpanded = ref(false)
const rankingPageSize = 10
const footerYear = new Date().getFullYear()
const quickRanges = [
  { id: "ytd", label: "今年来" },
  { id: "1y", label: "近1年", months: 12 },
  { id: "3y", label: "近3年", months: 36 },
  { id: "5y", label: "近5年", months: 60 },
  { id: "10y", label: "近10年", months: 120 },
  { id: "all", label: "全部" },
] as const
const overviewSubtabs = [
  { id: "trend", label: "数据概览" },
  { id: "distribution", label: "规模分布" },
  { id: "month", label: "月度" },
  { id: "year", label: "年度" },
]
const contentSubtabGroups = [
  { id: "topics", label: "话题", items: [
    { id: "topics", label: "演变" },
    { id: "topic-detail", label: "详情" },
  ] },
  { id: "content-analysis", label: "标题关键词", items: [
    { id: "content-evolution", label: "演变" },
    { id: "content-detail", label: "详情" },
  ] },
  { id: "nodes", label: "节点", items: [
    { id: "nodes", label: "分布" },
    { id: "node-detail", label: "详情" },
  ] },
  { id: "lifecycle", items: [
    { id: "lifecycle", label: "生命周期" },
  ] },
]
const communitySubtabs = [
  { id: "trends", label: "成员演变" },
  { id: "member-detail", label: "成员详情" },
]

let chartRuntime: typeof import("./chartRuntime") | null = null
let chartRuntimeRequest: Promise<typeof import("./chartRuntime")> | null = null
let topicEvolutionChart: DashboardChart | null = null
let topicTrendChart: DashboardChart | null = null
const managedCharts = new Map<string, DashboardChart>()
const topicEvolutionTagIndices = new Map<string, number[]>()
const tagDetailBuckets = new Map<string, any>()
const tagDetailBucketRequests = new Map<string, Promise<any>>()
const tagPeriodPostBuckets = new Map<string, any>()
const tagPeriodPostBucketRequests = new Map<string, Promise<any>>()
const tagPeriodCommentBuckets = new Map<string, any>()
const tagPeriodCommentBucketRequests = new Map<string, Promise<any>>()
const tagComparisonDetails = shallowRef<Record<string, any>>({})
const tagComparisonLoading = ref(false)
const tagComparisonError = ref("")
const memberProfileBuckets = new Map<string, any>()
const memberCommentBuckets = new Map<string, any>()
const loadedMonthlyRankingPeriods = new Set<string>()
const loadedAnnualRankingYears = new Set<string>()
const loadedTopicRowYears = new Set<string>()
const loadedNodeRowYears = new Set<string>()
const loadedActivityRowYears = new Set<string>()
const nodeDetailBuckets = new Map<string, any>()
const nodePeriodPostBuckets = new Map<string, any>()
const nodePeriodPostBucketRequests = new Map<string, Promise<any>>()
const nodePeriodCommentBuckets = new Map<string, any>()
const nodePeriodCommentBucketRequests = new Map<string, Promise<any>>()
let monthlyRankingIndex: any = null
let annualRankingIndex: any = null
let tagDetailRequestId = 0
let topicPeriodPostRequestId = 0
let tagComparisonRequestId = 0
let nodeDetailRequestId = 0
let nodePeriodPostRequestId = 0
let memberProfileRequestId = 0
let memberCommentRequestId = 0
let hoveredEvolutionTag = ""
let scrollToTopicPostsAfterPeriodChange = false
let scrollToNodePostsAfterPeriodChange = false
let tagDetailIndexRequest: Promise<void> | null = null
let nodeIndexRequest: Promise<void> | null = null
let overviewActivityIndexRequest: Promise<void> | null = null
let nodeDetailIndexRequest: Promise<void> | null = null
let nodeDetailController: AbortController | null = null
let applyingUrlState = false
let urlStateReady = false
const loadError = ref("")

function formatCompactNumber(value: number | undefined) {
  const number = Number(value || 0)
  if (number < 10_000) return formatNumber(number)
  return `${(number / 10_000).toFixed(1).replace(/\.0$/, "")}万`
}

function displayIndex(index: string | number) {
  return Number(index) + 1
}

function formatPercent(value: number | undefined, signed = false) {
  const number = Number(value || 0)
  return `${signed && number > 0 ? "+" : ""}${number.toFixed(1)}%`
}

function escapeHtml(value: unknown) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character] || character)
}

function timeAxisLabel(overrides: Record<string, unknown> = {}) {
  return { color: chartTheme.axis, fontSize: 11, showMaxLabel: true, ...overrides }
}

async function ensureChartRuntime() {
  if (chartRuntime) return chartRuntime
  chartRuntimeRequest ||= import("./chartRuntime")
  chartRuntime = await chartRuntimeRequest
  return chartRuntime
}

function managedChart(id: string) {
  const element = document.getElementById(id)
  if (!element || !chartRuntime) return null
  const current = managedCharts.get(id)
  if (current?.getDom() === element) return current
  current?.dispose()
  const chart = chartRuntime.initChart(element)
  managedCharts.set(id, chart)
  return chart
}

type LineDefinition = {
  name: string
  data: number[]
  color: string
  role?: "primary" | "secondary" | "peer"
  yAxisIndex?: number
  suffix?: string
  secondaryData?: number[]
  secondarySuffix?: string
  areaColor?: string
}

type OverviewLaneDefinition = {
  name: string
  data: number[]
  color: string
  unit: string
}

const overviewLaneColors = ["#0f766e", "#2563eb", "#d94841"] as const

function renderLineChart(
  id: string,
  periods: string[],
  definitions: LineDefinition[],
  yAxes: Array<{ name: string; max?: number }> = [{ name: "数量" }],
) {
  const chart = managedChart(id)
  if (!chart) return
  const element = chart.getDom()
  const legendLayout = definitions.length > 1
    ? wrappedLegendLayout(element, definitions.map((definition) => definition.name))
    : null
  const chartSides = responsiveChartSides(element, yAxes.length > 1)
  chart.resize()
  const annual = periods[0]?.length === 4
  const eventMarkers = communityEvents.value
    .map((event: any) => ({ ...event, axisPeriod: annual ? event.period.slice(0, 4) : event.period }))
    .filter((event: any, index: number, values: any[]) => periods.includes(event.axisPeriod)
      && values.findIndex((candidate) => candidate.axisPeriod === event.axisPeriod && candidate.title === event.title) === index)
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { color: chartTheme.pointer, width: 1 } },
      formatter(params: any[]) {
        const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
        const rows = items.map((item) => {
          const definition = definitions.find((candidate) => candidate.name === item.seriesName)
          const value = `${formatNumber(Number(item.value), 2)}${definition?.suffix || ""}`
          const secondary = definition?.secondaryData?.[item.dataIndex]
          const detail = secondary === undefined ? "" : ` <small style="color:#667085;font-weight:400">${Number(secondary).toFixed(2)}${definition?.secondarySuffix || ""}</small>`
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:145px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${value}${detail}</strong></span>`
        }).join("")
        return `<div style="min-width:320px"><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 18px;margin-top:8px">${rows}</div></div>`
      },
    },
    legend: legendLayout?.option || { show: false },
    grid: { top: 28, ...chartSides, bottom: legendLayout?.gridBottom || 48 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: periods,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: chartTheme.axisLine } },
    },
    yAxis: yAxes.map((axis, index) => ({
      type: "value",
      name: axis.name,
      min: 0,
      max: axis.max,
      position: index === 1 ? "right" : "left",
      nameTextStyle: { color: chartTheme.axis, fontSize: 12 },
      axisLabel: { color: chartTheme.axis, fontSize: 11 },
      splitLine: { show: index === 0, lineStyle: { color: chartTheme.gridLine } },
    })),
    series: definitions.map((definition, index) => {
      const secondary = definition.role === "secondary"
      return {
        name: definition.name,
        type: "line",
        data: definition.data,
        yAxisIndex: definition.yAxisIndex || 0,
        showSymbol: periods.length <= 1,
        symbolSize: 7,
        lineStyle: {
          color: definition.color,
          width: secondary ? 1.6 : 2.2,
          type: secondary ? "dashed" : "solid",
          opacity: secondary ? 0.78 : 1,
        },
        itemStyle: { color: definition.color, opacity: secondary ? 0.78 : 1 },
        areaStyle: definition.areaColor ? { color: definition.areaColor } : undefined,
        emphasis: { focus: "series", lineStyle: { width: secondary ? 2.8 : 4, opacity: 1 } },
        markLine: index === 0 && eventMarkers.length ? {
          silent: true,
          symbol: ["none", "none"],
          lineStyle: { color: chartTheme.pointer, type: "dashed", width: 1 },
          label: { color: chartTheme.axis, fontSize: 11, formatter: "{b}", position: "insideEndTop" },
          data: eventMarkers.map((event: any) => ({ name: event.short_label, xAxis: event.axisPeriod })),
        } : undefined,
      }
    }),
  } as any, true)
}

function renderOverviewMetricGroup(
  id: string,
  periods: string[],
  definitions: OverviewLaneDefinition[],
  showEvents = false,
) {
  const chart = managedChart(id)
  if (!chart || !periods.length) return
  const element = chart.getDom()
  chart.resize()

  const annual = periods[0]?.length === 4
  const eventMarkers = showEvents
    ? communityEvents.value
      .map((event: any) => ({ ...event, axisPeriod: annual ? event.period.slice(0, 4) : event.period }))
      .filter((event: any, index: number, values: any[]) => periods.includes(event.axisPeriod)
        && values.findIndex((candidate) => candidate.axisPeriod === event.axisPeriod && candidate.title === event.title) === index)
    : []
  const chartHeight = Math.max(360, element.clientHeight)
  const top = 26
  const bottom = 44
  const gap = 30
  const laneHeight = Math.max(66, Math.floor((chartHeight - top - bottom - gap * 2) / definitions.length))
  const grids = definitions.map((_, index) => ({
    top: top + index * (laneHeight + gap),
    height: laneHeight,
    left: 58,
    right: 16,
    containLabel: false,
  }))

  chart.setOption({
    aria: { enabled: true },
    animation: false,
    axisPointer: {
      link: [{ xAxisIndex: "all" }],
      label: { show: false },
    },
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { color: chartTheme.pointer, width: 1 } },
      formatter(params: any[]) {
        const dataIndex = Number(params[0]?.dataIndex || 0)
        const rows = definitions.map((definition) => (
          `<span style="display:flex;align-items:center;justify-content:space-between;gap:18px;min-width:190px">`
          + `<span style="display:flex;align-items:center;gap:7px">`
          + `<i style="display:inline-block;width:9px;height:9px;border-radius:50%;background:${definition.color}"></i>`
          + `${escapeHtml(definition.name)}</span>`
          + `<strong>${formatNumber(definition.data[dataIndex])} ${escapeHtml(definition.unit)}</strong></span>`
        )).join("")
        return `<div><strong>${escapeHtml(periods[dataIndex] || "")}</strong><div style="display:grid;gap:6px;margin-top:8px">${rows}</div></div>`
      },
    },
    grid: grids,
    xAxis: definitions.map((_, index) => ({
      type: "category",
      gridIndex: index,
      boundaryGap: false,
      data: periods,
      axisLabel: index === definitions.length - 1 ? timeAxisLabel() : { show: false },
      axisTick: { show: false },
      axisLine: { lineStyle: { color: chartTheme.axisLine } },
      axisPointer: { show: true, snap: true },
    })),
    yAxis: definitions.map((definition, index) => ({
      type: "value",
      gridIndex: index,
      min: 0,
      splitNumber: 2,
      name: definition.name,
      nameLocation: "end",
      nameGap: 7,
      nameTextStyle: { color: definition.color, fontSize: 12, fontWeight: 600, align: "left" },
      axisLabel: {
        color: chartTheme.axis,
        fontSize: 11,
        formatter: (value: number) => formatCompactNumber(value),
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: chartTheme.gridLine } },
    })),
    series: definitions.map((definition, index) => ({
      name: definition.name,
      type: "line",
      xAxisIndex: index,
      yAxisIndex: index,
      data: definition.data,
      showSymbol: periods.length <= 1,
      symbolSize: 7,
      lineStyle: { color: definition.color, width: 2.2 },
      itemStyle: { color: definition.color },
      emphasis: { focus: "series", lineStyle: { width: 3.5 } },
      markLine: eventMarkers.length ? {
        silent: true,
        symbol: ["none", "none"],
        lineStyle: { color: chartTheme.pointer, type: "dashed", width: 1 },
        label: {
          show: index === 0,
          color: chartTheme.axis,
          fontSize: 11,
          formatter: "{b}",
          position: "insideEndTop",
        },
        data: eventMarkers.map((event: any) => ({ name: event.short_label, xAxis: event.axisPeriod })),
      } : undefined,
    })),
  } as any, true)
}

function inRange(period: string) {
  return period >= fromPeriod.value && period <= toPeriod.value
}

function shiftMonth(period: string, offset: number) {
  if (!period) return ""
  const [year, month] = period.split("-").map(Number)
  const monthIndex = year * 12 + month - 1 + offset
  const shiftedYear = Math.floor(monthIndex / 12)
  const shiftedMonth = monthIndex - shiftedYear * 12 + 1
  return `${shiftedYear}-${String(shiftedMonth).padStart(2, "0")}`
}

function bucketFor(period: string) {
  return grain.value === "year" ? period.slice(0, 4) : period
}

function aggregateMetrics(rows: PeriodMetric[]) {
  const result = new Map<string, PeriodMetric>()
  for (const row of rows) {
    const bucket = bucketFor(row.period)
    const current = result.get(bucket) || {
      period: bucket,
      topic_count: 0,
      comment_count: 0,
      member_count: 0,
      reply_count: 0,
      zero_reply_count: 0,
      click_sum: 0,
      favorite_sum: 0,
      thank_sum: 0,
    }
    for (const key of ["topic_count", "comment_count", "member_count", "reply_count", "zero_reply_count", "click_sum", "favorite_sum", "thank_sum"] as const) {
      current[key] += row[key]
    }
    result.set(bucket, current)
  }
  return [...result.values()].sort((a, b) => a.period.localeCompare(b.period))
}

const periodOptions = computed<string[]>(() => overview.value.periods.map((item: PeriodMetric) => item.period))
const topicPeriodTotals = computed<Record<string, number>>(() => Object.fromEntries(
  overview.value.periods.map((item: PeriodMetric) => [item.period, item.topic_count]),
))
const monthlyPeriodOptions = computed<string[]>(() => periodOptions.value.filter((period) => (
  period <= overview.value.metadata.default_end_period && !incompletePeriods.value.includes(period)
)))
const annualPeriodOptions = computed<string[]>(() => [...new Set(
  monthlyPeriodOptions.value.map((period) => period.slice(0, 4)),
)].sort())
const defaultAnnualPeriod = computed(() => {
  const currentYear = overview.value.metadata.default_end_period?.slice(0, 4) || ""
  const currentYearMonths = monthlyPeriodOptions.value.filter((period) => period.startsWith(`${currentYear}-`)).length
  if (currentYear && currentYearMonths >= 2) return currentYear
  return [...annualPeriodOptions.value].reverse().find((year) => (
    monthlyPeriodOptions.value.filter((period) => period.startsWith(`${year}-`)).length === 12
  )) || annualPeriodOptions.value[annualPeriodOptions.value.length - 1] || ""
})
const fromPeriodOptions = computed<string[]>(() => monthlyPeriodOptions.value.filter((period) => (
  !toPeriod.value || period <= toPeriod.value
)))
const toPeriodOptions = computed<string[]>(() => monthlyPeriodOptions.value.filter((period) => (
  !fromPeriod.value || period >= fromPeriod.value
)))
const selectedRawPeriods = computed<PeriodMetric[]>(() =>
  overview.value.periods.filter((item: PeriodMetric) => inRange(item.period)),
)
const selectedMetrics = computed(() => aggregateMetrics(selectedRawPeriods.value))
const incompletePeriods = computed<string[]>(() => overview.value.metadata.incomplete_periods || [])

function quickRangeBounds(preset: (typeof quickRanges)[number]) {
  const periods = monthlyPeriodOptions.value
  if (!periods.length) return null
  const end = overview.value.metadata.default_end_period || periods[periods.length - 1]
  const foundEndIndex = periods.indexOf(end)
  const endIndex = foundEndIndex >= 0 ? foundEndIndex : periods.length - 1
  let startIndex = 0
  if (preset.id === "all") {
    startIndex = 0
  } else if (preset.id === "ytd") {
    const januaryIndex = periods.indexOf(`${end.slice(0, 4)}-01`)
    startIndex = januaryIndex >= 0 ? januaryIndex : 0
  } else if ("months" in preset) {
    startIndex = Math.max(0, endIndex - preset.months + 1)
  }
  return { start: periods[startIndex], end: periods[endIndex] }
}

function applyQuickRange(preset: (typeof quickRanges)[number]) {
  const range = quickRangeBounds(preset)
  if (!range) return
  fromPeriod.value = range.start
  toPeriod.value = range.end
  if (window.matchMedia("(max-width: 680px)").matches) filterExpanded.value = false
}

function isQuickRangeActive(preset: (typeof quickRanges)[number]) {
  const range = quickRangeBounds(preset)
  if (!range) return false
  return fromPeriod.value === range.start && toPeriod.value === range.end
}

function applyUrlState() {
  const params = new URLSearchParams(window.location.search)
  const defaultRange = quickRanges.find((preset) => preset.id === "5y")
  if (defaultRange) applyQuickRange(defaultRange)
  activeTab.value = ["overview", "content", "community", "engagement", "observations", "about"].includes(params.get("tab") || "")
    ? params.get("tab") as TabId
    : "overview"
  aboutView.value = activeTab.value === "about" && params.get("about") === "catalog" ? "catalog" : "about"
  catalogType.value = ["topics", "content", "nodes"].includes(params.get("catalogType") || "")
    ? params.get("catalogType") as typeof catalogType.value
    : "topics"
  catalogSort.value = params.get("catalogSort") === "name" ? "name" : "count"
  catalogGroup.value = safeTagParam(params.get("catalogGroup"))
  const requestedContentView = params.get("view") || ""
  const requestedContentTerm = safeTagParam(params.get("term"))
  const contentViews: ContentView[] = [
    "topics", "topic-detail", "content-evolution", "content-detail", "nodes", "node-detail", "lifecycle",
  ]
  if (requestedContentView === "posts") contentView.value = "topic-detail"
  else if (requestedContentView === "content-hotspots") {
    contentView.value = requestedContentTerm ? "content-detail" : "content-evolution"
  } else {
    contentView.value = contentViews.includes(requestedContentView as ContentView)
      ? requestedContentView as ContentView
      : "topics"
  }
  overviewView.value = ["distribution", "month", "year"].includes(params.get("overview") || "")
    ? params.get("overview") as OverviewView
    : "trend"
  grain.value = params.get("grain") === "year" ? "year" : "month"
  topLimit.value = integerParam(params, "topicTop", [10, 20, 30]) || 20
  trendLimit.value = integerParam(params, "trendTop", [10, 20, 30]) || 10
  contentHotspotLimit.value = integerParam(params, "contentTop", [10, 20, 30]) || 20
  contentTrendLimit.value = integerParam(params, "contentTrendTop", [10, 20, 30]) || 10
  nodeTrendLimit.value = integerParam(params, "nodeTop", [5, 10, 20]) || 10
  memberRankingMetric.value = ["topics", "comments", "thanks"].includes(params.get("memberMetric") || "")
    ? params.get("memberMetric") as MemberRankingMetric
    : "topics"
  memberRankingLimit.value = integerParam(params, "memberTop", [10, 20, 30]) || 20
  interactionRanking.value = ["favorite_count", "thank_count", "votes", "clicks"].includes(params.get("postSort") || "")
    ? params.get("postSort") as typeof interactionRanking.value
    : "favorite_count"
  selectedTag.value = safeTagParam(params.get("tag"))
  selectedContentTerm.value = requestedContentTerm
  comparedTags.value = safeComparisonParams(params, "tagCompare", selectedTag.value)
  comparedContentTerms.value = safeComparisonParams(params, "termCompare", selectedContentTerm.value)
  selectedNode.value = safeNodeParam(params.get("node"))
  selectedMember.value = safeMemberParam(params.get("member"))
  communityView.value = params.get("community") === "member-detail" || selectedMember.value ? "member-detail" : "trends"
  const requestedPeriod = params.get("period") || ""
  selectedPeriod.value = overviewView.value === "month" && monthlyPeriodOptions.value.includes(requestedPeriod)
    ? requestedPeriod
    : overview.value.metadata.default_end_period || ""
  selectedYear.value = overviewView.value === "year" && annualPeriodOptions.value.includes(requestedPeriod)
    ? requestedPeriod
    : defaultAnnualPeriod.value
  topicDetailPostPage.value = integerParam(params, "topicPage") || 1
  postRankingPage.value = integerParam(params, "postPage") || 1
  commentRankingPage.value = integerParam(params, "commentPage") || 1

  const requestedFrom = params.get("from") || ""
  const requestedTo = params.get("to") || ""
  if (monthlyPeriodOptions.value.includes(requestedFrom) && monthlyPeriodOptions.value.includes(requestedTo) && requestedFrom <= requestedTo) {
    fromPeriod.value = requestedFrom
    toPeriod.value = requestedTo
  }
  const requestedTopicPeriod = params.get("topicPeriod") || ""
  const validTopicPeriod = grain.value === "month"
    ? /^\d{4}-\d{2}$/.test(requestedTopicPeriod)
      && requestedTopicPeriod >= fromPeriod.value
      && requestedTopicPeriod <= toPeriod.value
    : /^\d{4}$/.test(requestedTopicPeriod)
      && requestedTopicPeriod >= fromPeriod.value.slice(0, 4)
      && requestedTopicPeriod <= toPeriod.value.slice(0, 4)
  selectedTopicDetailPeriod.value = contentView.value === "topic-detail" && validTopicPeriod
    ? requestedTopicPeriod
    : ""
  const requestedContentPeriod = params.get("contentPeriod") || ""
  const validContentPeriod = grain.value === "month"
    ? /^\d{4}-\d{2}$/.test(requestedContentPeriod)
      && requestedContentPeriod >= fromPeriod.value
      && requestedContentPeriod <= toPeriod.value
    : /^\d{4}$/.test(requestedContentPeriod)
      && requestedContentPeriod >= fromPeriod.value.slice(0, 4)
      && requestedContentPeriod <= toPeriod.value.slice(0, 4)
  selectedContentDetailPeriod.value = contentView.value === "content-detail" && validContentPeriod
    ? requestedContentPeriod
    : ""
  const requestedNodePeriod = params.get("nodePeriod") || ""
  const validNodePeriod = grain.value === "month"
    ? /^\d{4}-\d{2}$/.test(requestedNodePeriod)
      && requestedNodePeriod >= fromPeriod.value
      && requestedNodePeriod <= toPeriod.value
    : /^\d{4}$/.test(requestedNodePeriod)
      && requestedNodePeriod >= fromPeriod.value.slice(0, 4)
      && requestedNodePeriod <= toPeriod.value.slice(0, 4)
  selectedNodeDetailPeriod.value = contentView.value === "node-detail" && validNodePeriod
    ? requestedNodePeriod
    : ""
}

function dashboardUrl() {
  const url = new URL(window.location.href)
  for (const key of dashboardQueryKeys) url.searchParams.delete(key)
  const defaultRange = quickRanges.find((preset) => preset.id === "5y")
  const bounds = defaultRange ? quickRangeBounds(defaultRange) : null
  if (activeTab.value !== "overview") url.searchParams.set("tab", activeTab.value)
  if (activeTab.value === "about" && aboutView.value === "catalog") {
    url.searchParams.set("about", "catalog")
    if (catalogType.value !== "topics") url.searchParams.set("catalogType", catalogType.value)
    if (catalogSort.value !== "count") url.searchParams.set("catalogSort", catalogSort.value)
    if (catalogGroup.value) url.searchParams.set("catalogGroup", catalogGroup.value)
  }
  if (activeTab.value === "overview" && overviewView.value !== "trend") {
    url.searchParams.set("overview", overviewView.value)
    if (overviewView.value === "month") url.searchParams.set("period", selectedPeriod.value)
    if (overviewView.value === "year") url.searchParams.set("period", selectedYear.value)
  }
  if (activeTab.value === "content" && contentView.value !== "topics") url.searchParams.set("view", contentView.value)
  if (!bounds || fromPeriod.value !== bounds.start || toPeriod.value !== bounds.end) {
    url.searchParams.set("from", fromPeriod.value)
    url.searchParams.set("to", toPeriod.value)
  }
  if (grain.value !== "month") url.searchParams.set("grain", grain.value)
  if (activeTab.value === "content") {
    if ((contentView.value === "topics" || contentView.value === "topic-detail") && selectedTag.value) url.searchParams.set("tag", selectedTag.value)
    if (contentView.value === "content-detail" && selectedContentTerm.value) url.searchParams.set("term", selectedContentTerm.value)
    if (contentView.value === "topic-detail") comparedTags.value.forEach(tag => url.searchParams.append("tagCompare", tag))
    if (contentView.value === "topic-detail" && selectedTopicDetailPeriod.value) {
      url.searchParams.set("topicPeriod", selectedTopicDetailPeriod.value)
    }
    if (contentView.value === "content-detail") comparedContentTerms.value.forEach(term => url.searchParams.append("termCompare", term))
    if (contentView.value === "content-detail" && selectedContentDetailPeriod.value) {
      url.searchParams.set("contentPeriod", selectedContentDetailPeriod.value)
    }
    if (contentView.value === "node-detail" && selectedNode.value) {
      url.searchParams.set("node", selectedNode.value)
      if (selectedNodeDetailPeriod.value) url.searchParams.set("nodePeriod", selectedNodeDetailPeriod.value)
    }
    if (topLimit.value !== 20) url.searchParams.set("topicTop", String(topLimit.value))
    if (trendLimit.value !== 10) url.searchParams.set("trendTop", String(trendLimit.value))
    if (contentView.value === "content-evolution" && contentHotspotLimit.value !== 20) url.searchParams.set("contentTop", String(contentHotspotLimit.value))
    if (contentView.value === "content-evolution" && contentTrendLimit.value !== 10) url.searchParams.set("contentTrendTop", String(contentTrendLimit.value))
    if (nodeTrendLimit.value !== 10) url.searchParams.set("nodeTop", String(nodeTrendLimit.value))
    if (contentView.value === "topic-detail" && topicDetailPostPage.value > 1) url.searchParams.set("topicPage", String(topicDetailPostPage.value))
  }
  if (activeTab.value === "community") {
    if (communityView.value === "member-detail") url.searchParams.set("community", communityView.value)
    if (communityView.value === "member-detail" && selectedMember.value) url.searchParams.set("member", selectedMember.value)
    if (memberRankingMetric.value !== "topics") url.searchParams.set("memberMetric", memberRankingMetric.value)
    if (memberRankingLimit.value !== 20) url.searchParams.set("memberTop", String(memberRankingLimit.value))
  }
  if (activeTab.value === "engagement") {
    if (interactionRanking.value !== "favorite_count") url.searchParams.set("postSort", interactionRanking.value)
    if (postRankingPage.value > 1) url.searchParams.set("postPage", String(postRankingPage.value))
    if (commentRankingPage.value > 1) url.searchParams.set("commentPage", String(commentRankingPage.value))
  }
  return `${url.pathname}${url.search}${url.hash}`
}

function syncDashboardUrl(mode: "push" | "replace" = "replace") {
  if (!urlStateReady || applyingUrlState) return
  const nextUrl = dashboardUrl()
  const currentUrl = `${window.location.pathname}${window.location.search}${window.location.hash}`
  if (nextUrl === currentUrl) return
  window.history[mode === "push" ? "pushState" : "replaceState"]({}, "", nextUrl)
}

async function restoreDashboardUrl() {
  applyingUrlState = true
  applyUrlState()
  await nextTick()
  applyingUrlState = false
  await loadActiveData()
  if (activeTab.value === "overview" && overviewView.value === "month") await ensureMonthlyData()
  if (activeTab.value === "overview" && overviewView.value === "year") await ensureAnnualData()
  await renderActiveTab()
  await scrollToUrlAnchor()
  syncDashboardUrl("replace")
}

async function scrollToUrlAnchor() {
  const anchor = window.location.hash.slice(1)
  if (!anchor) return
  await nextTick()
  document.getElementById(anchor)?.scrollIntoView({ block: "start" })
  window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}`)
}

const previousRawPeriods = computed<PeriodMetric[]>(() => {
  const rows: PeriodMetric[] = overview.value.periods
  const fromIndex = rows.findIndex((item) => item.period === fromPeriod.value)
  const toIndex = rows.findIndex((item) => item.period === toPeriod.value)
  if (fromIndex < 0 || toIndex < fromIndex) return []
  const length = toIndex - fromIndex + 1
  return rows.slice(Math.max(0, fromIndex - length), fromIndex)
})

function summarize(rows: PeriodMetric[]) {
  const summary = rows.reduce(
    (result, row) => {
      result.topics += row.topic_count
      result.comments += row.comment_count
      result.members += row.member_count
      result.replies += row.reply_count
      result.zeroReplies += row.zero_reply_count
      result.clicks += row.click_sum
      result.favorites += row.favorite_sum
      result.thanks += row.thank_sum
      return result
    },
    { topics: 0, comments: 0, members: 0, replies: 0, zeroReplies: 0, clicks: 0, favorites: 0, thanks: 0 },
  )
  return {
    ...summary,
    commentsPerTopic: summary.topics ? summary.comments / summary.topics : 0,
    zeroReplyRate: summary.topics ? (summary.zeroReplies / summary.topics) * 100 : 0,
  }
}

const currentSummary = computed(() => summarize(selectedRawPeriods.value))
const previousSummary = computed(() => summarize(previousRawPeriods.value))
const defaultScopeSummary = computed(() => summarize(
  overview.value.periods.filter((item: PeriodMetric) => item.period <= overview.value.metadata.default_end_period),
))
const headerParticipantCount = computed(() => (
  overview.value.metadata.participant_count ?? defaultScopeSummary.value.members
))
const headerDataScope = computed(() => overview.value.metadata.start_period
  ? `${overview.value.metadata.start_period} 至 ${overview.value.metadata.default_end_period} · ${formatCompactNumber(headerParticipantCount.value)}用户 · ${formatCompactNumber(defaultScopeSummary.value.topics)}帖子 · ${formatCompactNumber(defaultScopeSummary.value.comments)}评论`
  : "正在读取数据范围")
const compactHeaderDataScope = computed(() => overview.value.metadata.start_period
  ? `${overview.value.metadata.start_period} 至 ${overview.value.metadata.default_end_period} · ${formatCompactNumber(headerParticipantCount.value)}用户 · ${formatCompactNumber(defaultScopeSummary.value.topics)}帖子`
  : "正在读取数据范围")
const narrowHeaderDataScope = computed(() => overview.value.metadata.start_period
  ? `${overview.value.metadata.start_period} 至 ${overview.value.metadata.default_end_period} · ${formatCompactNumber(headerParticipantCount.value)}用户`
  : "正在读取数据范围")
const aboutSummary = computed(() => ({
  startPeriod: overview.value.metadata.start_period || "",
  endPeriod: overview.value.metadata.default_end_period || "",
  participants: headerParticipantCount.value,
  topics: defaultScopeSummary.value.topics,
  comments: defaultScopeSummary.value.comments,
  coverage: {
    topics: Number(overview.value.metadata.analysis_coverage?.topics || 0),
    contentTerms: Number(overview.value.metadata.analysis_coverage?.content_terms || 0),
    nodes: Number(overview.value.metadata.analysis_coverage?.nodes || 0),
    members: Number(overview.value.metadata.analysis_coverage?.members || 0),
  },
}))
const catalogCounts = computed(() => ({
  topics: aboutSummary.value.coverage.topics,
  content: aboutSummary.value.coverage.contentTerms,
  nodes: aboutSummary.value.coverage.nodes,
}))
const filterSummary = computed(() => `${fromPeriod.value} 至 ${toPeriod.value} · 按${grain.value === "month" ? "月" : "年"}`)

function selectTab(id: string) {
  activeTab.value = id as TabId
}

async function openAbout() {
  activeTab.value = "about"
  aboutView.value = "about"
  await nextTick()
  window.scrollTo({ top: 0 })
}

async function openCatalog() {
  activeTab.value = "about"
  aboutView.value = "catalog"
  await nextTick()
  window.scrollTo({ top: 0 })
}

function selectOverviewView(id: string) {
  overviewView.value = id as OverviewView
}

async function selectOverviewActivityMetric(metric: "topics" | "comments") {
  if (overviewActivityMetric.value === metric) return
  overviewActivityMetric.value = metric
  await nextTick()
  renderHeatmap()
}

function selectContentView(id: string) {
  contentView.value = id as ContentView
}

function selectCommunityView(id: string) {
  communityView.value = id as CommunityView
}

function periodDelta(current: number, previous: number | undefined) {
  return previous ? ((current - previous) / previous) * 100 : null
}

function monthlyMetric(current: number, previous?: number, yearAgo?: number) {
  return {
    value: current,
    monthDelta: periodDelta(current, previous),
    yearDelta: periodDelta(current, yearAgo),
  }
}

const monthlyData = computed(() => {
  if (!selectedPeriod.value) return null
  const currentIndex = overview.value.periods.findIndex((row: PeriodMetric) => row.period === selectedPeriod.value)
  if (currentIndex < 0) return null
  const current = overview.value.periods[currentIndex] as PeriodMetric
  const previous = overview.value.periods[currentIndex - 1] as PeriodMetric | undefined
  const yearAgo = overview.value.periods.find((row: PeriodMetric) => row.period === `${Number(selectedPeriod.value.slice(0, 4)) - 1}-${selectedPeriod.value.slice(5)}`)
  const metric = (key: keyof PeriodMetric) => monthlyMetric(
    Number(current[key] || 0),
    previous ? Number(previous[key] || 0) : undefined,
    yearAgo ? Number(yearAgo[key] || 0) : undefined,
  )
  const ratioMetric = (row: PeriodMetric | undefined) => row?.topic_count ? row.comment_count / row.topic_count : 0
  const ranking = monthlyRankings.value[selectedPeriod.value] || { posts: [], post_rankings: {}, comments: [] }
  const summary = ranking.summary || { tags: [], content: [], nodes: [], activity: {} }
  const activityMetric = (values: Array<number | null> | undefined) => monthlyMetric(
    Number(values?.[0] || 0),
    values?.[1] == null ? undefined : Number(values[1]),
    values?.[2] == null ? undefined : Number(values[2]),
  )
  const metrics = {
    topics: metric("topic_count"),
    comments: metric("comment_count"),
    members: metric("member_count"),
    favorites: metric("favorite_sum"),
    thanks: metric("thank_sum"),
    authors: activityMetric(summary.activity?.authors),
    commenters: activityMetric(summary.activity?.commenters),
    commentsPerTopic: monthlyMetric(ratioMetric(current), ratioMetric(previous), ratioMetric(yearAgo)),
  }
  const yearAgoRanking = yearAgo ? monthlyRankings.value[yearAgo.period] : null
  const posts = ranking.posts.map((post: RepresentativePost) => ({ ...post, nodeLabel: nodeLabel(post.node) }))
  return {
    period: selectedPeriod.value,
    metrics,
    insights: buildPeriodInsights({
      metrics,
      currentSummary: summary,
      baselineSummary: yearAgoRanking?.summary || {},
      currentTopics: current.topic_count,
      baselineTopics: yearAgo?.topic_count || 0,
      periodType: "month",
      comparableRankings: Boolean(yearAgoRanking && yearAgo),
      nodeLabel,
    }),
    tags: summary.tags || [],
    content: summary.content || [],
    nodes: (summary.nodes || []).map((item: any) => ({ ...item, label: nodeLabel(item.name) })),
    posts,
    postRankings: ranking.post_rankings,
    comments: ranking.comments,
    events: communityEvents.value.filter((event: any) => event.period === selectedPeriod.value),
  }
})

const annualData = computed(() => {
  if (!selectedYear.value) return null
  const currentRows = overview.value.periods.filter((row: PeriodMetric) => (
    row.period.startsWith(`${selectedYear.value}-`) && monthlyPeriodOptions.value.includes(row.period)
  )) as PeriodMetric[]
  if (!currentRows.length) return null
  const monthCount = currentRows.length
  const previousYear = String(Number(selectedYear.value) - 1)
  const previousRows = overview.value.periods.filter((row: PeriodMetric) => (
    row.period.startsWith(`${previousYear}-`) && Number(row.period.slice(5)) <= monthCount
  )) as PeriodMetric[]
  const current = summarize(currentRows)
  const previous = summarize(previousRows)
  const annualMetric = (value: number, previousValue: number) => ({
    value,
    monthDelta: null,
    yearDelta: periodDelta(value, previousValue),
  })
  const ranking = annualRankings.value[selectedYear.value] || { posts: [], post_rankings: {}, comments: [] }
  const summary = ranking.summary || { tags: [], content: [], nodes: [], activity: {} }
  const activityMetric = (values: Array<number | null> | undefined) => annualMetric(
    Number(values?.[0] || 0), Number(values?.[2] || 0),
  )
  const metrics = {
    topics: annualMetric(current.topics, previous.topics),
    comments: annualMetric(current.comments, previous.comments),
    members: annualMetric(current.members, previous.members),
    favorites: annualMetric(current.favorites, previous.favorites),
    thanks: annualMetric(current.thanks, previous.thanks),
    authors: activityMetric(summary.activity?.authors),
    commenters: activityMetric(summary.activity?.commenters),
    commentsPerTopic: annualMetric(current.commentsPerTopic, previous.commentsPerTopic),
  }
  const previousRanking = annualRankings.value[previousYear]
  const comparableRankings = monthCount === 12 && previousRows.length === 12 && Boolean(previousRanking)
  const posts = (ranking.posts || []).map((post: RepresentativePost) => ({ ...post, nodeLabel: nodeLabel(post.node) }))
  return {
    period: selectedYear.value,
    periodNote: monthCount < 12 ? `截至 ${monthCount} 月` : "",
    metrics,
    insights: buildPeriodInsights({
      metrics,
      currentSummary: summary,
      baselineSummary: previousRanking?.summary || {},
      currentTopics: current.topics,
      baselineTopics: previous.topics,
      periodType: "year",
      comparableRankings,
      nodeLabel,
    }),
    tags: summary.tags || [],
    content: summary.content || [],
    nodes: (summary.nodes || []).map((item: any) => ({ ...item, label: nodeLabel(item.name) })),
    posts,
    postRankings: ranking.post_rankings || {},
    comments: ranking.comments || [],
    events: communityEvents.value.filter((event: any) => event.period.startsWith(`${selectedYear.value}-`)),
  }
})

async function ensureMonthlyRankingData(period: string) {
  if (loadedMonthlyRankingPeriods.has(period)) return
  if (!monthlyRankingIndex) monthlyRankingIndex = await getJson("dynamic-monthly-rankings-index.json")
  const shard = monthlyRankingIndex.periods?.[period]
  if (!shard) return
  const payload = await getJson(shard)
  monthlyRankings.value = { ...monthlyRankings.value, [period]: payload.ranking }
  loadedMonthlyRankingPeriods.add(period)
}

async function ensureMonthlyData() {
  monthlyDataLoading.value = true
  try {
    const yearAgoPeriod = `${Number(selectedPeriod.value.slice(0, 4)) - 1}-${selectedPeriod.value.slice(5)}`
    const periods = [selectedPeriod.value]
    if (monthlyPeriodOptions.value.includes(yearAgoPeriod)) periods.push(yearAgoPeriod)
    await Promise.all(periods.map(ensureMonthlyRankingData))
  } catch (error) {
    reportLoadError(error)
  } finally {
    monthlyDataLoading.value = false
  }
}

async function ensureAnnualData() {
  annualDataLoading.value = true
  try {
    const year = selectedYear.value
    const previousYear = String(Number(year) - 1)
    if (!annualRankingIndex) annualRankingIndex = await getJson("dynamic-annual-rankings-index.json")
    const selectedYearMonthCount = monthlyPeriodOptions.value.filter(period => period.startsWith(`${year}-`)).length
    const years = [year]
    if (selectedYearMonthCount === 12 && annualPeriodOptions.value.includes(previousYear)) years.push(previousYear)
    const missingYears = years.filter(candidate => !loadedAnnualRankingYears.has(candidate))
    const payloads = await Promise.all(missingYears.map(async candidate => {
      const shard = annualRankingIndex.years?.[candidate]
      if (!shard) return null
      const payload = await getJson(shard)
      return { year: candidate, ranking: payload.ranking }
    }))
    const nextRankings = { ...annualRankings.value }
    for (const payload of payloads) {
      if (!payload) continue
      nextRankings[payload.year] = payload.ranking
      loadedAnnualRankingYears.add(payload.year)
    }
    annualRankings.value = nextRankings
  } catch (error) {
    reportLoadError(error)
  } finally {
    annualDataLoading.value = false
  }
}

async function selectMonthlyPeriod(period: string) {
  if (!monthlyPeriodOptions.value.includes(period)) return
  selectedPeriod.value = period
  await ensureMonthlyData()
}

async function selectAnnualPeriod(year: string) {
  if (!annualPeriodOptions.value.includes(year)) return
  selectedYear.value = year
  await ensureAnnualData()
}

async function selectPeriodTag(tag: string) {
  await openTopicDetail(tag)
}

async function openGlobalEntity(result: { type: "tag" | "term" | "node" | "member"; value: string }) {
  if (result.type === "tag") {
    await openTopicDetail(result.value)
    return
  }
  if (result.type === "node") {
    await openNodeDetail(result.value)
    return
  }
  if (result.type === "member") {
    await openMemberProfile(result.value)
    return
  }
  activeTab.value = "content"
  contentView.value = "content-detail"
  selectedContentTerm.value = result.value
}

const postSummary = computed(() => {
  const periods = selectedRawPeriods.value.length
  const activeTags = new Set(
    topics.value.rows
      .filter((row: any[]) => inRange(row[0]) && row[2] > 0)
      .map((row: any[]) => row[1]),
  ).size
  return {
    monthlyTopics: periods ? currentSummary.value.topics / periods : 0,
    activeTags,
  }
})

const memberSummary = computed(() => {
  const rows = community.value.rows.filter((row: any[]) => inRange(row[0]))
  return {
    newMembers: sumRows(rows, 1),
    averageAuthors: rows.length ? sumRows(rows, 2) / rows.length : 0,
    averageCommenters: rows.length ? sumRows(rows, 3) / rows.length : 0,
    peakAuthors: rows.reduce((best: any[], row: any[]) => !best.length || row[2] > best[2] ? row : best, []),
    peakCommenters: rows.reduce((best: any[], row: any[]) => !best.length || row[3] > best[3] ? row : best, []),
  }
})

const engagementSummary = computed(() => {
  const rows = engagement.value.rows.filter((row: any[]) => inRange(row[0]))
  const topicsCount = sumRows(rows, 1)
  const clicks = sumRows(rows, 2)
  const favorites = sumRows(rows, 3)
  const topicThanks = sumRows(rows, 4)
  const votes = sumRows(rows, 5)
  const replies = sumRows(rows, 6)
  const commentThanks = sumRows(rows, 8)
  return {
    clicks, favorites, topicThanks, votes, commentThanks,
    favoriteRate: clicks ? favorites / clicks * 1000 : 0,
    topicThankRate: replies ? topicThanks / replies * 1000 : 0,
    voteRate: topicsCount ? votes / topicsCount * 1000 : 0,
  }
})

const topInteractionPosts = computed(() => engagement.value.top_posts?.[interactionRanking.value] || [])
const postPageCount = computed(() => Math.max(1, Math.ceil(topInteractionPosts.value.length / rankingPageSize)))
const commentPageCount = computed(() => Math.max(1, Math.ceil(engagement.value.top_comments.length / rankingPageSize)))
const displayedInteractionPosts = computed(() => topInteractionPosts.value.slice(
  (postRankingPage.value - 1) * rankingPageSize,
  postRankingPage.value * rankingPageSize,
).map((post: any) => ({ ...post, node_label: nodeLabel(post.node) })))
const displayedTopComments = computed(() => engagement.value.top_comments.slice(
  (commentRankingPage.value - 1) * rankingPageSize,
  commentRankingPage.value * rankingPageSize,
))

const postPaginationItems = computed(() => paginationItems(postRankingPage.value, postPageCount.value))
const commentPaginationItems = computed(() => paginationItems(commentRankingPage.value, commentPageCount.value))

const memberEvolutionRows = computed(() => community.value.rank_rows.filter((row: any[]) => {
  if (row[0] !== grain.value || row[2] !== memberRankingMetric.value || row[3] > memberRankingLimit.value) return false
  if (grain.value === "month") return inRange(row[1])
  return row[1] >= fromPeriod.value.slice(0, 4) && row[1] <= toPeriod.value.slice(0, 4)
}))
const memberEvolutionPeriods = computed(() => [...new Set<string>(
  memberEvolutionRows.value.map((row: any[]) => row[1] as string),
)].sort())
function evolutionHeatmapChartStyle(limit: number) {
  return { height: `${Math.max(360, 112 + limit * 30)}px` }
}

const memberEvolutionChartStyle = computed(() => evolutionHeatmapChartStyle(memberRankingLimit.value))

const memberProfileRowsInRange = computed<any[][]>(() => {
  if (!selectedMemberProfile.value) return []
  return selectedMemberProfile.value.periods.filter((row: any[]) => inRange(row[0]))
})
const memberProfileSummary = computed(() => {
  const rows = memberProfileRowsInRange.value
  const topics = sumRows(rows, 1)
  const comments = sumRows(rows, 2)
  const topicThanks = sumRows(rows, 3)
  const commentThanks = sumRows(rows, 4)
  return {
    topics,
    comments,
    topicThanks,
    commentThanks,
    totalThanks: topicThanks + commentThanks,
    activePeriods: rows.filter((row: any[]) => row[1] > 0 || row[2] > 0).length,
  }
})
const memberEvolutionRankingColumns = computed(() => [
  {
    key: "topics", title: "发送帖子", items: community.value.top_topic_authors.slice(0, 20).map((member: any) => ({
      key: member.username, label: member.username, value: formatNumber(member.topic_count), action: `member:${member.username}`,
    })),
  },
  {
    key: "comments", title: "发送评论", items: community.value.top_commenters.slice(0, 20).map((member: any) => ({
      key: member.username, label: member.username, value: formatNumber(member.comment_count), action: `member:${member.username}`,
    })),
  },
  {
    key: "thanks", title: "收到感谢", items: community.value.top_thanked.slice(0, 20).map((member: any) => ({
      key: member.username, label: member.username, value: formatNumber(member.total_thanks), action: `member:${member.username}`,
    })),
  },
])
const memberProfileRankingColumns = computed(() => selectedMemberProfile.value ? [
  {
    key: "participation-nodes", title: "主要参与节点", items: [], groups: [
      {
        key: "topic-nodes", title: "发帖", items: selectedMemberProfile.value.topic_nodes.slice(0, 10).map((item: any[]) => ({
          key: `topic-${item[0]}`, label: nodeLabel(item[0]), value: formatNumber(item[1]),
          action: hasNodeDetail(item[0]) ? `node:${item[0]}` : undefined,
          clickable: hasNodeDetail(item[0]),
        })),
      },
      {
        key: "comment-nodes", title: "评论", items: selectedMemberProfile.value.comment_nodes.slice(0, 10).map((item: any[]) => ({
          key: `comment-${item[0]}`, label: nodeLabel(item[0]), value: formatNumber(item[1]),
          action: hasNodeDetail(item[0]) ? `node:${item[0]}` : undefined,
          clickable: hasNodeDetail(item[0]),
        })),
      },
    ],
  },
  {
    key: "tags", title: "主要发帖话题", subtitle: "按发帖数", items: selectedMemberProfile.value.tags.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`, action: `topic:${item[0]}`,
    })),
  },
  {
    key: "content-terms", title: "主要标题关键词", subtitle: "按标题数", items: (selectedMemberProfile.value.content_terms || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 标题`, action: `content:${item[0]}`,
    })),
  },
] : [])

function sumRows(rows: any[][], valueIndex: number) {
  return rows.reduce((sum, row) => sum + row[valueIndex], 0)
}

const lifecycleSummary = computed(() => {
  const firstRows = lifecycle.value.first_reply_rows.filter((row: any[]) => lifecycleInRange(row[0], "first"))
  const firstCounts = new Map<string, number>()
  for (const row of firstRows) firstCounts.set(row[1], (firstCounts.get(row[1]) || 0) + row[2])
  const eligibleTopics = sumRows(firstRows, 2)
  const within1h = (firstCounts.get("10m") || 0) + (firstCounts.get("1h") || 0)
  const within24h = within1h + (firstCounts.get("6h") || 0) + (firstCounts.get("24h") || 0)
  const ageRows = lifecycle.value.comment_age_rows.filter((row: any[]) => lifecycleInRange(row[0], "first"))
  const first7dComments = sumRows(ageRows, 2)
  const firstHourComments = ageRows
    .filter((row: any[]) => row[1] === "10m" || row[1] === "1h")
    .reduce((sum: number, row: any[]) => sum + row[2], 0)
  const tailRows = lifecycle.value.long_tail_rows.filter((row: any[]) => lifecycleInRange(row[0], "tail"))
  const comments30d = sumRows(tailRows, 1)
  const after7d = sumRows(tailRows, 3)
  const structureRows = lifecycle.value.discussion_structure_rows.filter(
    (row: any[]) => lifecycleInRange(row[0], "first"),
  )
  const repliedTopics = sumRows(structureRows, 1)
  const structureComments = sumRows(structureRows, 2)
  const commenters = sumRows(structureRows, 3)
  const authorParticipated = sumRows(structureRows, 4)
  const mentionComments = sumRows(structureRows, 5)
  return {
    eligibleTopics,
    responseRate: eligibleTopics ? ((eligibleTopics - (firstCounts.get("none") || 0)) / eligibleTopics) * 100 : 0,
    within1hRate: eligibleTopics ? (within1h / eligibleTopics) * 100 : 0,
    within24hRate: eligibleTopics ? (within24h / eligibleTopics) * 100 : 0,
    firstHourShare: first7dComments ? (firstHourComments / first7dComments) * 100 : 0,
    after7dShare: comments30d ? (after7d / comments30d) * 100 : 0,
    averageParticipants: repliedTopics ? commenters / repliedTopics : 0,
    commentsPerParticipant: commenters ? structureComments / commenters : 0,
    authorParticipationRate: repliedTopics ? authorParticipated / repliedTopics * 100 : 0,
    mentionRate: structureComments ? mentionComments / structureComments * 100 : 0,
  }
})

function lifecycleInRange(period: string, window: "first" | "tail") {
  const cutoff = window === "first"
    ? lifecycle.value.metadata?.first_reply_complete_through
    : lifecycle.value.metadata?.long_tail_complete_through
  return inRange(period) && (!cutoff || period <= cutoff)
}

function change(current: number, previous: number) {
  return previous ? ((current - previous) / previous) * 100 : 0
}

function periodsByBucket() {
  const result = new Map<string, number>()
  for (const row of selectedRawPeriods.value) {
    const bucket = bucketFor(row.period)
    result.set(bucket, (result.get(bucket) || 0) + row.topic_count)
  }
  return result
}

function aggregateSeriesRows(rows: any[], nameIndex: number, countIndex: number, replyIndex: number) {
  const values = new Map<string, Map<string, { count: number; replies: number }>>()
  for (const row of rows) {
    if (!inRange(row[0])) continue
    const bucket = bucketFor(row[0])
    if (!values.has(bucket)) values.set(bucket, new Map())
    const names = values.get(bucket)!
    const name = row[nameIndex]
    const current = names.get(name) || { count: 0, replies: 0 }
    current.count += row[countIndex]
    current.replies += row[replyIndex]
    names.set(name, current)
  }
  return values
}

function selectTopNames(values: Map<string, Map<string, { count: number }>>, limit: number) {
  const totals = new Map<string, number>()
  for (const names of values.values()) {
    for (const [name, item] of names) {
      totals.set(name, (totals.get(name) || 0) + item.count)
    }
  }
  return [...totals].sort((a, b) => b[1] - a[1]).slice(0, limit).map(([name]) => name)
}

const tagValues = computed(() => aggregateSeriesRows(topics.value.rows, 1, 2, 3))
const topicBuckets = computed(() => [...tagValues.value.keys()].sort())
const trendTags = computed(() => {
  const tags = selectTopNames(tagValues.value, trendLimit.value)
  if (!selectedTag.value || tags.includes(selectedTag.value)) return tags
  return [selectedTag.value, ...tags.slice(0, Math.max(0, trendLimit.value - 1))]
})
const topicEvolutionChartStyle = computed(() => evolutionHeatmapChartStyle(topLimit.value))

function heatmapDataZoom(periods: string[], element: HTMLElement) {
  const availableWidth = Math.max(320, element.clientWidth)
  const maxVisible = grain.value === "month" ? 14 : 12
  const visibleCount = Math.max(4, Math.min(periods.length, maxVisible, Math.floor(availableWidth / 76)))
  const startValue = Math.max(0, periods.length - visibleCount)
  const endValue = Math.max(0, periods.length - 1)
  return [
    {
      type: "inside",
      xAxisIndex: 0,
      startValue,
      endValue,
      zoomOnMouseWheel: false,
      moveOnMouseWheel: false,
      moveOnMouseMove: true,
    },
    {
      type: "slider",
      xAxisIndex: 0,
      startValue,
      endValue,
      height: 18,
      bottom: 8,
      brushSelect: false,
      showDetail: false,
      borderColor: "#d9dee7",
      backgroundColor: "#f7f8fa",
      fillerColor: "rgba(47, 143, 131, 0.18)",
      handleStyle: { color: "#ffffff", borderColor: "#667085" },
      moveHandleStyle: { color: "#667085" },
      selectedDataBackground: { lineStyle: { color: "#2f8f83" }, areaStyle: { color: "#b9d8d0" } },
    },
  ]
}

function tagTotalsFor(periods: PeriodMetric[]) {
  if (!periods.length) return { counts: new Map<string, number>(), total: 0 }
  const start = periods[0].period
  const end = periods[periods.length - 1].period
  const counts = new Map<string, number>()
  for (const row of topics.value.rows) {
    if (row[0] < start || row[0] > end) continue
    counts.set(row[1], (counts.get(row[1]) || 0) + row[2])
  }
  return { counts, total: periods.reduce((sum, item) => sum + item.topic_count, 0) }
}

const momentum = computed(() => {
  const selected = selectedRawPeriods.value
  const windowLength = Math.min(12, selected.length)
  const currentPeriods = selected.slice(-windowLength)
  const allPeriods = overview.value.periods as PeriodMetric[]
  const currentStart = allPeriods.findIndex((item) => item.period === currentPeriods[0]?.period)
  const previousPeriods = currentStart < 0
    ? []
    : allPeriods.slice(Math.max(0, currentStart - windowLength), currentStart)
  const current = tagTotalsFor(currentPeriods)
  const previous = tagTotalsFor(previousPeriods)
  const rows = topics.value.tags.map((item: any) => {
    const currentCount = current.counts.get(item.tag) || 0
    const previousCount = previous.counts.get(item.tag) || 0
    const currentShare = current.total ? (currentCount / current.total) * 100 : 0
    const previousShare = previous.total ? (previousCount / previous.total) * 100 : 0
    return { tag: item.tag, count: currentCount, delta: currentShare - previousShare }
  }).filter((item: any) => item.count >= 20)
  return {
    rising: [...rows].sort((a, b) => b.delta - a.delta).slice(0, 20),
    falling: [...rows].sort((a, b) => a.delta - b.delta).slice(0, 20),
  }
})

function tagStats(tag: string, sourceRows: any[] = topics.value.rows) {
  const rows = sourceRows.filter((row: any[]) => row[1] === tag && inRange(row[0]))
  const count = rows.reduce((sum: number, row: any[]) => sum + row[2], 0)
  const replies = rows.reduce((sum: number, row: any[]) => sum + row[3], 0)
  const peak = [...rows].sort((a, b) => b[2] - a[2])[0]
  return {
    tag,
    count,
    share: currentSummary.value.topics ? (count / currentSummary.value.topics) * 100 : 0,
    repliesPerTopic: count ? replies / count : 0,
    peak: peak?.[0] || "-",
  }
}

const hotTopics = computed(() => selectTopNames(tagValues.value, 20).map((tag) => tagStats(tag)))
const topicDetailTagOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const row of topics.value.rows) {
    if (inRange(row[0]) && row[2] > 0) counts.set(row[1], (counts.get(row[1]) || 0) + row[2])
  }
  if (counts.size) {
    return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-CN"))
  }
  return topics.value.tags
    .map((item: any) => [item.tag, item.total] as [string, number])
    .sort((a: [string, number], b: [string, number]) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-CN"))
})
const topicSearchOptions = computed<SearchOption[]>(() => topicDetailTagOptions.value.map(([tag, count]: [string, number]) => ({
  value: tag,
  label: tag,
  meta: `${formatNumber(count)} 个帖子`,
})))
const topicComparisonRelatedCounts = computed(() => new Map<string, number>(
  (selectedTagDetail.value?.related || []).map((item: any[]) => [String(item[0]), Number(item[1] || 0)]),
))
const topicComparisonSuggestedValues = computed(() =>
  (selectedTagDetail.value?.related || []).slice(0, 20).map((item: any[]) => String(item[0])),
)
const topicComparisonOptions = computed<SearchOption[]>(() => Object.entries(tagDetailIndex.value.tags || {})
  .map(([tag, rawEntry]) => ({
    value: tag,
    label: tag,
    total: Number((rawEntry as any).total || 0),
  }))
  .sort((left, right) => right.total - left.total || left.label.localeCompare(right.label, "zh-CN"))
  .map(item => {
    const relatedCount = topicComparisonRelatedCounts.value.get(item.value)
    return {
      value: item.value,
      label: item.label,
      meta: relatedCount
        ? `共同出现于 ${formatNumber(relatedCount)} 个帖子`
        : `${formatNumber(item.total)} 个帖子`,
    }
  }))
const selectedTagStats = computed(() => (
  selectedTag.value && selectedTagDetail.value
    ? tagStats(selectedTag.value, selectedTagDetail.value.rows || [])
    : null
))
const memberSearchOptions = computed<SearchOption[]>(() => Object.entries(memberProfileIndex.value.members || {})
  .sort(([left], [right]) => left.localeCompare(right, "en", { sensitivity: "base", numeric: true }))
  .map(([username, rawEntry]) => {
    const entry = rawEntry as any
    return {
      value: username,
      label: username,
      meta: `${formatNumber(entry.topics)} 帖子 · ${formatNumber(entry.comments)} 评论`,
    }
  }))
const topicEvolutionRankingColumns = computed(() => [
  {
    key: "hot", title: "热点话题", items: hotTopics.value.map((item) => ({
      key: item.tag, label: item.tag, value: formatNumber(item.count), action: `topic:${item.tag}`,
    })),
  },
  {
    key: "rising", title: "上升话题", items: momentum.value.rising.map((item: any) => ({
      key: item.tag, label: item.tag, value: `+${item.delta.toFixed(2)}pp`, action: `topic:${item.tag}`,
    })),
  },
  {
    key: "falling", title: "下降话题", items: momentum.value.falling.map((item: any) => ({
      key: item.tag, label: item.tag, value: `${item.delta.toFixed(2)}pp`, action: `topic:${item.tag}`,
    })),
  },
])
const topicGroupCards = computed(() => {
  const groupCounts = new Map<string, number>()
  const groupTopicMatchCounts = new Map<string, number>()
  const groupTopicCounts = new Map<string, Map<string, number>>()
  const topicDetails = new Map<string, string>((topics.value.tags || []).map((item: any) => [
    String(item.tag).toLocaleLowerCase(),
    String(item.tag),
  ]))
  for (const [period, groupName, count] of topics.value.group_rows || []) {
    if (!inRange(period)) continue
    groupCounts.set(groupName, (groupCounts.get(groupName) || 0) + Number(count || 0))
  }
  for (const [period, groupName, count] of topics.value.group_topic_match_rows || []) {
    if (!inRange(period)) continue
    groupTopicMatchCounts.set(groupName, (groupTopicMatchCounts.get(groupName) || 0) + Number(count || 0))
  }
  for (const [period, groupName, topic, count] of topics.value.group_topic_rows || []) {
    if (!inRange(period)) continue
    if (!groupTopicCounts.has(groupName)) groupTopicCounts.set(groupName, new Map())
    const values = groupTopicCounts.get(groupName)!
    values.set(topic, (values.get(topic) || 0) + Number(count || 0))
  }
  const currentStart = shiftMonth(toPeriod.value, -11)
  const previousStart = shiftMonth(toPeriod.value, -23)
  const previousEnd = shiftMonth(toPeriod.value, -12)
  const totalWindowCount = (start: string, end: string) => overview.value.periods
    .filter((row: PeriodMetric) => row.period >= start && row.period <= end)
    .reduce((sum: number, row: PeriodMetric) => sum + row.topic_count, 0)
  const groupWindowCount = (groupName: string, start: string, end: string) => (topics.value.group_rows || [])
    .filter((row: any[]) => row[0] >= start && row[0] <= end && row[1] === groupName)
    .reduce((sum: number, row: any[]) => sum + Number(row[2] || 0), 0)
  const currentTotal = totalWindowCount(currentStart, toPeriod.value)
  const previousTotal = totalWindowCount(previousStart, previousEnd)

  return (topics.value.groups || []).map((group: any) => {
    const count = groupCounts.get(group.name) || 0
    const minimumTopicCount = aggregateItemDisplayMinimum(
      count,
      topics.value.group_metadata?.item_display_rule,
    )
    const currentShare = currentTotal
      ? groupWindowCount(group.name, currentStart, toPeriod.value) / currentTotal * 100
      : 0
    const previousShare = previousTotal
      ? groupWindowCount(group.name, previousStart, previousEnd) / previousTotal * 100
      : 0
    const topicItems = [...(groupTopicCounts.get(group.name) || new Map<string, number>())]
      .filter(([, topicCount]) => topicCount >= minimumTopicCount)
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0], "zh-CN"))
      .map(([configuredTopic, topicCount]) => {
        const indexedTopic = topicDetails.get(configuredTopic.toLocaleLowerCase())
        return {
          key: `topic:${configuredTopic}`,
          label: indexedTopic || configuredTopic,
          count: topicCount,
          action: indexedTopic ? `topic:${indexedTopic}` : "",
          clickable: Boolean(indexedTopic),
          hint: indexedTopic ? "查看话题详情" : "该原始话题未纳入详情索引",
        }
      })
    return {
      id: group.name,
      label: group.label,
      description: group.description || "",
      count,
      share: currentSummary.value.topics ? count / currentSummary.value.topics * 100 : 0,
      shareDelta: currentTotal && previousTotal ? currentShare - previousShare : null,
      coverage: count ? (groupTopicMatchCounts.get(group.name) || 0) / count * 100 : 0,
      items: topicItems,
    }
  }).sort((left: any, right: any) => right.count - left.count || left.label.localeCompare(right.label, "zh-CN"))
})
const topicDetailRankingColumns = computed(() => selectedTagDetail.value ? [
  {
    key: topicRelationMode.value === "topics" ? "related-topics" : "related-content",
    title: topicRelationMode.value === "topics" ? "关联话题" : "关联标题关键词",
    items: (topicRelationMode.value === "topics"
      ? selectedTagDetail.value.related || []
      : selectedTagDetail.value.related_content || []).slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`,
      action: topicRelationMode.value === "topics" ? `topic:${item[0]}` : `content:${item[0]}`,
    })),
  },
  {
    key: "nodes", title: "主要节点", items: selectedTagDetail.value.nodes.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: nodeLabel(item[0]), value: `${formatNumber(item[1])} 帖子`,
      action: hasNodeDetail(item[0]) ? `node:${item[0]}` : undefined,
      clickable: hasNodeDetail(item[0]),
    })),
  },
  {
    key: "authors", title: "活跃用户", items: selectedTagDetail.value.authors.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`,
      action: `member:${item[0]}`,
    })),
  },
] : [])

const topicDetailPeriodOptions = computed(() => {
  if (!selectedTagDetail.value) return [""]
  const periods = new Set<string>()
  for (const row of selectedTagDetail.value.rows || []) {
    if (inRange(row[0]) && Number(row[2]) > 0) periods.add(bucketFor(row[0]))
  }
  return [...periods].sort().concat("")
})
const topicDetailPeriodLabels = { "": "全部时间" }

const topicDetailPosts = computed<RepresentativePost[]>(() => {
  if (!selectedTag.value || !selectedTagDetail.value) return []
  const candidates = grain.value === "month" && selectedTopicDetailPeriod.value
    ? topicPeriodPosts.value
    : selectedTagDetail.value.posts || []
  return candidates
    .filter((post: RepresentativePost) => inRange(post.period))
    .filter((post: RepresentativePost) => (
      !selectedTopicDetailPeriod.value
      || bucketFor(post.period) === selectedTopicDetailPeriod.value
    ))
    .sort((a: RepresentativePost, b: RepresentativePost) => b.score - a.score || b.create_at - a.create_at)
})
const topicDetailPostsTitle = computed(() => (
  selectedTopicDetailPeriod.value
    ? `${selectedTopicDetailPeriod.value} 代表帖子`
    : "代表帖子"
))
const topicDetailPostsDescription = computed(() => {
  if (!selectedTopicDetailPeriod.value) {
    return "每年保留综合互动得分最高的 10 个相关帖子，当前按互动得分排序并分页展示。"
  }
  return grain.value === "month"
    ? "按综合互动得分展示该月代表帖子：相关帖子不少于 100 个时显示 Top 10，不少于 20 个时显示 Top 5，其余显示 Top 3。"
    : "按综合互动得分展示该年度 Top 10，可选择其他年份或恢复全部时间。"
})
const topicDetailCommentsDescription = computed(() => {
  if (selectedTopicDetailPeriod.value) return ""
  return `每年保留感谢数最高的 10 条相关评论，合并展示 ${fromPeriod.value} 至 ${toPeriod.value} 范围内的 ${formatNumber(topicPeriodComments.value.length)} 条；仅收录至少获得 1 次感谢的评论。`
})
const topicDetailPostPageCount = computed(() => Math.max(1, Math.ceil(topicDetailPosts.value.length / rankingPageSize)))
const displayedTopicDetailPosts = computed(() => topicDetailPosts.value.slice(
  (topicDetailPostPage.value - 1) * rankingPageSize,
  topicDetailPostPage.value * rankingPageSize,
))
const topicDetailPostPaginationItems = computed(() => paginationItems(
  topicDetailPostPage.value,
  topicDetailPostPageCount.value,
))
const displayedMemberPosts = computed(() => (
  selectedMemberProfile.value?.posts || []
).slice(0, memberPostsExpanded.value ? 20 : 10))
const displayedMemberComments = computed(() => selectedMemberComments.value.slice(
  0,
  memberCommentsExpanded.value ? 20 : 10,
))

async function openTopicDetail(tag: string) {
  activeTab.value = "content"
  contentView.value = "topic-detail"
  selectedTag.value = tag
}

async function openContentDetail(term: string) {
  activeTab.value = "content"
  contentView.value = "content-detail"
  selectedContentTerm.value = term
}

async function openTopicGroupTopic(_key: string, action?: string) {
  if (action?.startsWith("topic:")) await openTopicDetail(action.slice(6))
}

async function selectRankedItem(item: any) {
  if (item.action?.startsWith("topic:")) await openTopicDetail(item.action.slice(6))
  if (item.action?.startsWith("node:")) await openNodeDetail(item.action.slice(5))
  if (item.action?.startsWith("member:")) await openMemberProfile(item.action.slice(7))
  if (item.action?.startsWith("content:")) await openContentDetail(item.action.slice(8))
}

function hasMemberProfile(username: string) {
  return Boolean(memberProfileIndex.value.members?.[username])
}

async function loadMemberComments(username: string) {
  const requestId = ++memberCommentRequestId
  selectedMemberComments.value = []
  memberCommentsExpanded.value = false
  if (!username) {
    memberCommentsLoading.value = false
    return
  }
  const bucket = memberProfileIndex.value.members?.[username]?.comment_bucket
  if (!bucket) {
    memberCommentsLoading.value = false
    return
  }
  memberCommentsLoading.value = true
  try {
    let payload = memberCommentBuckets.get(bucket)
    if (!payload) {
      payload = await getJson(`dynamic-member-comments-${bucket}.json`)
      memberCommentBuckets.set(bucket, payload)
    }
    if (requestId === memberCommentRequestId) {
      selectedMemberComments.value = payload.comments?.[username] || []
    }
  } finally {
    if (requestId === memberCommentRequestId) memberCommentsLoading.value = false
  }
}

async function loadMemberProfile(username: string) {
  const requestId = ++memberProfileRequestId
  memberPostsExpanded.value = false
  void loadMemberComments(username)
  if (!username) {
    selectedMemberProfile.value = null
    memberProfileLoading.value = false
    return
  }
  const entry = memberProfileIndex.value.members?.[username]
  if (!entry) {
    selectedMemberProfile.value = null
    memberProfileLoading.value = false
    return
  }
  memberProfileLoading.value = true
  try {
    let payload = memberProfileBuckets.get(entry.bucket)
    if (!payload) {
      payload = await getJson(`dynamic-member-profiles-${entry.bucket}.json`)
      memberProfileBuckets.set(entry.bucket, payload)
    }
    if (requestId === memberProfileRequestId) selectedMemberProfile.value = payload.profiles?.[username] || null
  } finally {
    if (requestId === memberProfileRequestId) memberProfileLoading.value = false
  }
}

async function openMemberProfile(username: string) {
  await ensureMemberIndex()
  activeTab.value = "community"
  communityView.value = "member-detail"
  selectedMember.value = username
}

async function ensureTagDetailIndex() {
  if (loadedData.has("tag-detail-index")) return
  if (!tagDetailIndexRequest) {
    tagDetailIndexRequest = getJson("dynamic-tag-detail-index.json")
      .then((payload) => {
        tagDetailIndex.value = payload
        loadedData.add("tag-detail-index")
      })
      .finally(() => {
        tagDetailIndexRequest = null
      })
  }
  await tagDetailIndexRequest
}

async function ensureNodesData() {
  if (!loadedData.has("nodes-index")) {
    if (!nodeIndexRequest) {
      nodeIndexRequest = getJson("dynamic-nodes.json")
        .then((payload) => {
          nodes.value = { ...payload, rows: payload.rows || [] }
          if (payload.rows) {
            payload.rows.forEach((row: any[]) => loadedNodeRowYears.add(String(row[0]).slice(0, 4)))
          }
          loadedData.add("nodes-index")
        })
        .finally(() => { nodeIndexRequest = null })
    }
    await nodeIndexRequest
  }
  const periods = [
    ...selectedRawPeriods.value.map((item: PeriodMetric) => item.period),
    ...previousRawPeriods.value.map((item: PeriodMetric) => item.period),
  ]
  const years = [...new Set(periods.map((period) => period.slice(0, 4)))].sort()
  const shards = nodes.value.row_shards || {}
  const missing = years.filter((year) => shards[year] && !loadedNodeRowYears.has(year))
  if (!missing.length) return
  const payloads = await Promise.all(missing.map((year) => getJson(shards[year])))
  const mergedRows = [
    ...(nodes.value.rows || []),
    ...payloads.flatMap((payload: any) => payload.rows || []),
  ]
  const rows = [...new Map(
    mergedRows.map((row: any[]) => [`${row[0]}\u0000${row[1]}`, row]),
  ).values()].sort(
    (left: any[], right: any[]) => left[0].localeCompare(right[0]) || left[1].localeCompare(right[1]),
  )
  missing.forEach((year) => loadedNodeRowYears.add(year))
  nodes.value = { ...nodes.value, rows }
}

async function ensureOverviewActivityData() {
  if (!loadedData.has("overview-activity-index")) {
    if (!overviewActivityIndexRequest) {
      overviewActivityIndexRequest = getJson("dynamic-overview-activity.json")
        .then((payload) => {
          overview.value = {
            ...overview.value,
            activity: payload.rows || [],
            activityIndex: payload,
          }
          if (payload.rows) {
            payload.rows.forEach((row: any[]) => loadedActivityRowYears.add(String(row[0]).slice(0, 4)))
          }
          loadedData.add("overview-activity-index")
        })
        .finally(() => { overviewActivityIndexRequest = null })
    }
    await overviewActivityIndexRequest
  }
  const years = [...new Set(
    selectedRawPeriods.value.map((item: PeriodMetric) => item.period.slice(0, 4)),
  )].sort()
  const shards = overview.value.activityIndex?.row_shards || {}
  const missing = years.filter((year) => shards[year] && !loadedActivityRowYears.has(year))
  if (!missing.length) return
  const payloads = await Promise.all(missing.map((year) => getJson(shards[year])))
  const mergedRows = [
    ...(overview.value.activity || []),
    ...payloads.flatMap((payload: any) => payload.rows || []),
  ]
  const rows = [...new Map(
    mergedRows.map((row: any[]) => [`${row[0]}\u0000${row[1]}\u0000${row[2]}`, row]),
  ).values()].sort(
    (left: any[], right: any[]) => left[0].localeCompare(right[0]) || left[1] - right[1] || left[2] - right[2],
  )
  missing.forEach((year) => loadedActivityRowYears.add(year))
  overview.value = { ...overview.value, activity: rows }
}

async function ensureNodeDetailIndex() {
  if (loadedData.has("node-detail-index")) return
  if (!nodeDetailIndexRequest) {
    nodeDetailIndexRequest = getJson("dynamic-node-detail-index.json")
      .then((payload) => {
        nodeDetailIndex.value = payload
        loadedData.add("node-detail-index")
      })
      .finally(() => { nodeDetailIndexRequest = null })
  }
  await nodeDetailIndexRequest
}

async function loadNodeDetail(node: string) {
  const requestId = ++nodeDetailRequestId
  nodeDetailController?.abort()
  nodeDetailController = new AbortController()
  if (!node) {
    selectedNodeDetail.value = null
    nodeDetailLoading.value = false
    return
  }
  await ensureNodeDetailIndex()
  if (requestId !== nodeDetailRequestId) return
  const entry = nodeDetailIndex.value.nodes?.[node]
  if (!entry) {
    selectedNodeDetail.value = null
    nodeDetailLoading.value = false
    return
  }
  nodeDetailLoading.value = true
  try {
    let payload = nodeDetailBuckets.get(entry.bucket)
    if (!payload) {
      payload = await getJson(`dynamic-node-details-${entry.bucket}.json`, { signal: nodeDetailController.signal })
      nodeDetailBuckets.set(entry.bucket, payload)
    }
    if (requestId === nodeDetailRequestId) {
      selectedNodeDetail.value = payload.details?.[node] || null
      if (
        selectedNodeDetailPeriod.value
        && !nodeDetailPeriodOptions.value.includes(selectedNodeDetailPeriod.value)
      ) {
        selectedNodeDetailPeriod.value = ""
      }
    }
  } catch (error) {
    if (!(error instanceof DOMException && error.name === "AbortError")) throw error
  } finally {
    if (requestId === nodeDetailRequestId) nodeDetailLoading.value = false
  }
}

async function getNodePeriodPostBucket(bucket: string) {
  const cached = nodePeriodPostBuckets.get(bucket)
  if (cached) return cached
  let request = nodePeriodPostBucketRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-node-period-posts-${bucket}.json`)
      .then(payload => {
        nodePeriodPostBuckets.set(bucket, payload)
        return payload
      })
      .finally(() => nodePeriodPostBucketRequests.delete(bucket))
    nodePeriodPostBucketRequests.set(bucket, request)
  }
  return request
}

async function getNodePeriodCommentBucket(bucket: string) {
  const cached = nodePeriodCommentBuckets.get(bucket)
  if (cached) return cached
  let request = nodePeriodCommentBucketRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-node-period-comments-${bucket}.json`)
      .then(payload => {
        nodePeriodCommentBuckets.set(bucket, payload)
        return payload
      })
      .finally(() => nodePeriodCommentBucketRequests.delete(bucket))
    nodePeriodCommentBucketRequests.set(bucket, request)
  }
  return request
}

async function loadNodePeriodPosts() {
  const requestId = ++nodePeriodPostRequestId
  nodePeriodPostsError.value = ""
  nodePeriodCommentsError.value = ""
  if (!selectedNode.value) {
    nodePeriodPosts.value = []
    nodePeriodComments.value = []
    nodePeriodCommentSummary.value = {}
    nodePeriodPostsLoading.value = false
    nodePeriodCommentsLoading.value = false
    return
  }
  await ensureNodeDetailIndex()
  if (requestId !== nodePeriodPostRequestId) return
  const entry = nodeDetailIndex.value.nodes?.[selectedNode.value]
  const shouldLoadPosts = Boolean(selectedNodeDetailPeriod.value)
  if (!entry?.period_comment_bucket || (shouldLoadPosts && !entry?.period_post_bucket)) {
    nodePeriodPosts.value = []
    nodePeriodComments.value = []
    nodePeriodCommentSummary.value = {}
    nodePeriodPostsLoading.value = false
    nodePeriodCommentsLoading.value = false
    return
  }
  nodePeriodPostsLoading.value = shouldLoadPosts
  nodePeriodCommentsLoading.value = true
  const [postResult, commentResult] = await Promise.allSettled([
    shouldLoadPosts
      ? getNodePeriodPostBucket(entry.period_post_bucket)
      : Promise.resolve(null),
    getNodePeriodCommentBucket(entry.period_comment_bucket),
  ])
  if (requestId === nodePeriodPostRequestId) {
    if (shouldLoadPosts && postResult.status === "fulfilled") {
      nodePeriodPosts.value = postResult.value.posts?.[selectedNode.value]?.[selectedNodeDetailPeriod.value] || []
    } else if (shouldLoadPosts) {
      nodePeriodPosts.value = []
      nodePeriodPostsError.value = grain.value === "month"
        ? "该月代表帖子加载失败，请稍后重试。"
        : "该年代表帖子加载失败，请稍后重试。"
    } else {
      nodePeriodPosts.value = []
    }
    if (commentResult.status === "fulfilled") {
      const periodComments = selectedNodeDetailPeriod.value
        ? commentsForPeriod(
          commentResult.value,
          selectedNode.value,
          selectedNodeDetailPeriod.value,
          fromPeriod.value,
          toPeriod.value,
        )
        : commentsForRange(
          commentResult.value,
          selectedNode.value,
          overview.value.metadata.start_period,
          overview.value.metadata.default_end_period,
          100,
        )
      nodePeriodComments.value = periodComments.comments
      nodePeriodCommentSummary.value = periodComments.summary
    } else {
      nodePeriodComments.value = []
      nodePeriodCommentSummary.value = {}
      nodePeriodCommentsError.value = selectedNodeDetailPeriod.value
        ? (grain.value === "month"
          ? "该月代表评论加载失败，请稍后重试。"
          : "该年代表评论加载失败，请稍后重试。")
        : "代表评论加载失败，请稍后重试。"
    }
    nodePeriodPostsLoading.value = false
    nodePeriodCommentsLoading.value = false
  }
}

async function ensureMemberIndex() {
  if (loadedData.has("member-index")) return
  memberProfileIndex.value = await getJson("dynamic-member-profile-index.json")
  loadedData.add("member-index")
}

async function ensureMemberData() {
  if (loadedData.has("member-base")) return
  const [communityData] = await Promise.all([
    getJson("dynamic-community.json"),
    ensureMemberIndex(),
  ])
  community.value = communityData
  loadedData.add("member-base")
}

async function getTagDetailBucket(bucket: string) {
  const cached = tagDetailBuckets.get(bucket)
  if (cached) return cached
  let request = tagDetailBucketRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-tag-details-${bucket}.json`)
      .then(payload => {
        tagDetailBuckets.set(bucket, payload)
        return payload
      })
      .finally(() => tagDetailBucketRequests.delete(bucket))
    tagDetailBucketRequests.set(bucket, request)
  }
  return request
}

async function getTagDetail(tag: string) {
  await ensureTagDetailIndex()
  const entry = tagDetailIndex.value.tags?.[tag]
  if (!entry) return null
  const payload = await getTagDetailBucket(entry.bucket)
  return payload.details?.[tag] || null
}

async function getTagPeriodPostBucket(bucket: string) {
  const cached = tagPeriodPostBuckets.get(bucket)
  if (cached) return cached
  let request = tagPeriodPostBucketRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-tag-period-posts-${bucket}.json`)
      .then(payload => {
        tagPeriodPostBuckets.set(bucket, payload)
        return payload
      })
      .finally(() => tagPeriodPostBucketRequests.delete(bucket))
    tagPeriodPostBucketRequests.set(bucket, request)
  }
  return request
}

async function getTagPeriodCommentBucket(bucket: string) {
  const cached = tagPeriodCommentBuckets.get(bucket)
  if (cached) return cached
  let request = tagPeriodCommentBucketRequests.get(bucket)
  if (!request) {
    request = getJson(`dynamic-tag-period-comments-${bucket}.json`)
      .then(payload => {
        tagPeriodCommentBuckets.set(bucket, payload)
        return payload
      })
      .finally(() => tagPeriodCommentBucketRequests.delete(bucket))
    tagPeriodCommentBucketRequests.set(bucket, request)
  }
  return request
}

async function loadTopicPeriodPosts() {
  const requestId = ++topicPeriodPostRequestId
  topicPeriodPostsError.value = ""
  topicPeriodCommentsError.value = ""
  if (!selectedTag.value) {
    topicPeriodPosts.value = []
    topicPeriodComments.value = []
    topicPeriodCommentSummary.value = {}
    topicPeriodPostsLoading.value = false
    topicPeriodCommentsLoading.value = false
    return
  }
  await ensureTagDetailIndex()
  if (requestId !== topicPeriodPostRequestId) return
  const entry = tagDetailIndex.value.tags?.[selectedTag.value]
  const shouldLoadMonthPosts = grain.value === "month" && Boolean(selectedTopicDetailPeriod.value)
  if (!entry?.period_comment_bucket || (shouldLoadMonthPosts && !entry?.period_post_bucket)) {
    topicPeriodPosts.value = []
    topicPeriodComments.value = []
    topicPeriodCommentSummary.value = {}
    topicPeriodPostsLoading.value = false
    topicPeriodCommentsLoading.value = false
    return
  }
  topicPeriodPostsLoading.value = shouldLoadMonthPosts
  topicPeriodCommentsLoading.value = true
  const [postResult, commentResult] = await Promise.allSettled([
    shouldLoadMonthPosts
      ? getTagPeriodPostBucket(entry.period_post_bucket)
      : Promise.resolve(null),
    getTagPeriodCommentBucket(entry.period_comment_bucket),
  ])
  if (requestId === topicPeriodPostRequestId) {
    if (shouldLoadMonthPosts && postResult.status === "fulfilled") {
      topicPeriodPosts.value = postResult.value?.posts?.[selectedTag.value]?.[selectedTopicDetailPeriod.value] || []
    } else if (shouldLoadMonthPosts) {
      topicPeriodPosts.value = []
      topicPeriodPostsError.value = "该月代表帖子加载失败，请稍后重试。"
    } else {
      topicPeriodPosts.value = []
    }
    if (commentResult.status === "fulfilled") {
      const periodComments = selectedTopicDetailPeriod.value
        ? commentsForPeriod(
          commentResult.value,
          selectedTag.value,
          selectedTopicDetailPeriod.value,
          fromPeriod.value,
          toPeriod.value,
        )
        : commentsForRange(
          commentResult.value,
          selectedTag.value,
          fromPeriod.value,
          toPeriod.value,
        )
      topicPeriodComments.value = periodComments.comments
      topicPeriodCommentSummary.value = periodComments.summary
    } else {
      topicPeriodComments.value = []
      topicPeriodCommentSummary.value = {}
      topicPeriodCommentsError.value = selectedTopicDetailPeriod.value
        ? (grain.value === "month"
          ? "该月代表评论加载失败，请稍后重试。"
          : "该年代表评论加载失败，请稍后重试。")
        : "代表评论加载失败，请稍后重试。"
    }
    topicPeriodPostsLoading.value = false
    topicPeriodCommentsLoading.value = false
  }
}

async function loadTagDetail(tag: string) {
  const requestId = ++tagDetailRequestId
  if (!tag) {
    selectedTagDetail.value = null
    tagDetailLoading.value = false
    return
  }
  tagDetailLoading.value = true
  try {
    const detail = await getTagDetail(tag)
    if (requestId === tagDetailRequestId) {
      selectedTagDetail.value = detail
      if (
        selectedTopicDetailPeriod.value
        && !topicDetailPeriodOptions.value.includes(selectedTopicDetailPeriod.value)
      ) {
        selectedTopicDetailPeriod.value = ""
      }
    }
  } finally {
    if (requestId === tagDetailRequestId) tagDetailLoading.value = false
  }
}

async function loadTagComparisonDetails(values = comparedTags.value) {
  const requestId = ++tagComparisonRequestId
  tagComparisonError.value = ""
  await ensureTagDetailIndex()
  if (requestId !== tagComparisonRequestId) return
  const normalized = values
    .filter((tag, index) => tag !== selectedTag.value && values.indexOf(tag) === index && Boolean(tagDetailIndex.value.tags?.[tag]))
    .slice(0, 4)
  if (normalized.length !== comparedTags.value.length || normalized.some((tag, index) => tag !== comparedTags.value[index])) {
    comparedTags.value = normalized
  }
  if (!normalized.length) {
    tagComparisonDetails.value = {}
    tagComparisonLoading.value = false
    return
  }
  tagComparisonLoading.value = true
  try {
    const details = await Promise.all(normalized.map(async tag => [tag, await getTagDetail(tag)] as const))
    if (requestId === tagComparisonRequestId) {
      tagComparisonDetails.value = Object.fromEntries(details.filter(([, detail]) => Boolean(detail)))
    }
  } catch {
    if (requestId === tagComparisonRequestId) tagComparisonError.value = "对比话题加载失败，请稍后重试。"
  } finally {
    if (requestId === tagComparisonRequestId) tagComparisonLoading.value = false
  }
}

function renderOverviewTrend() {
  const periods = selectedMetrics.value.map((item) => item.period)
  renderOverviewMetricGroup("overview-trend", periods, [
    { name: "成员", data: selectedMetrics.value.map((item) => item.member_count), color: overviewLaneColors[0], unit: "人" },
    { name: "帖子", data: selectedMetrics.value.map((item) => item.topic_count), color: overviewLaneColors[1], unit: "个" },
    { name: "评论", data: selectedMetrics.value.map((item) => item.comment_count), color: overviewLaneColors[2], unit: "条" },
  ], true)
}

function renderOverviewParticipation() {
  const periods = selectedMetrics.value.map((item) => item.period)
  renderOverviewMetricGroup("overview-participation", periods, [
    { name: "点击", data: selectedMetrics.value.map((item) => item.click_sum), color: overviewLaneColors[0], unit: "次" },
    { name: "收藏", data: selectedMetrics.value.map((item) => item.favorite_sum), color: overviewLaneColors[1], unit: "次" },
    { name: "感谢", data: selectedMetrics.value.map((item) => item.thank_sum), color: overviewLaneColors[2], unit: "次" },
  ])
}

function renderPostResponseIntensity() {
  const periods = selectedMetrics.value.map((item) => item.period)
  renderLineChart("post-response-intensity", periods, [
    { name: "评论/帖子", data: selectedMetrics.value.map((item) => item.topic_count ? item.comment_count / item.topic_count : 0), color: "#0f766e" },
    { name: "零回复率", data: selectedMetrics.value.map((item) => item.topic_count ? item.zero_reply_count / item.topic_count * 100 : 0), color: "#8c7a68", role: "secondary", yAxisIndex: 1, suffix: "%" },
  ], [{ name: "评论/帖子" }, { name: "零回复率 (%)" }])
}

function renderHeatmap() {
  const metric = new Map<string, number>()
  const valueIndex = overviewActivityMetric.value === "topics" ? 3 : 4
  const metricLabel = overviewActivityMetric.value === "topics" ? "发帖" : "评论"
  for (const row of overview.value.activity) {
    if (!inRange(row[0])) continue
    const key = `${row[1]}-${row[2]}`
    metric.set(key, (metric.get(key) || 0) + row[valueIndex])
  }
  const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
  const chart = managedChart("activity-heatmap")
  if (!chart) return
  const chartElement = chart.getDom()
  chartElement.dataset.metric = overviewActivityMetric.value
  chartElement.setAttribute("role", "img")
  chartElement.setAttribute("aria-label", `${metricLabel}活跃时段热力图`)
  const hours = Array.from({ length: 24 }, (_, hour) => `${hour}:00`)
  const data: number[][] = []
  let maxValue = 0
  days.forEach((_, weekday) => hours.forEach((__, hour) => {
    const value = metric.get(`${weekday}-${hour}`) || 0
    data.push([hour, weekday, value])
    maxValue = Math.max(maxValue, value)
  }))
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: { trigger: "item", confine: true, formatter: (params: any) => `${days[params.value[1]]} ${hours[params.value[0]]}<br>${metricLabel} ${formatNumber(params.value[2])}` },
    grid: { top: 18, right: 24, bottom: 42, left: 58 },
    xAxis: { type: "category", data: hours, axisLabel: { color: chartTheme.axis, fontSize: 11 }, axisLine: { lineStyle: { color: chartTheme.axisLine } } },
    yAxis: { type: "category", data: days, axisLabel: { color: chartTheme.axis, fontSize: 12 }, axisLine: { lineStyle: { color: chartTheme.axisLine } } },
    visualMap: { show: false, min: 0, max: maxValue || 1, dimension: 2, inRange: { color: heatmapColors } },
    series: [{ name: metricLabel, type: "heatmap", data, itemStyle: { borderColor: "#fff", borderWidth: 1 }, emphasis: { itemStyle: { borderColor: "#111827", borderWidth: 2 } } }],
  } as any, true)
}

function renderTopicEvolution() {
  const totals = periodsByBucket()
  const element = document.getElementById("topic-evolution")
  if (!element) return
  if (!topicEvolutionChart || topicEvolutionChart.getDom() !== element) {
    topicEvolutionChart?.dispose()
    topicEvolutionChart = chartRuntime?.initChart(element) || null
  }
  if (!topicEvolutionChart) return
  const ranks = Array.from({ length: topLimit.value }, (_, index) => `Top ${index + 1}`)
  const rawData: any[][] = []
  let maxValue = 0
  topicEvolutionTagIndices.clear()
  for (const [bucketIndex, bucket] of topicBuckets.value.entries()) {
    const rankedTags = [...(tagValues.value.get(bucket) || new Map()).entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, topLimit.value)
    for (let rank = 0; rank < topLimit.value; rank += 1) {
      const entry = rankedTags[rank]
      const tag = entry?.[0] || ""
      const values = entry?.[1]
      const count = values?.count || 0
      const replies = values?.replies || 0
      const share = totals.get(bucket) ? count / Math.max(1, totals.get(bucket) || 0) * 100 : 0
      const value = count
      const dataIndex = rawData.length
      rawData.push([bucketIndex, rank, value, tag, count, share, count ? replies / count : 0, bucket])
      if (tag) {
        const indices = topicEvolutionTagIndices.get(tag) || []
        indices.push(dataIndex)
        topicEvolutionTagIndices.set(tag, indices)
      }
      maxValue = Math.max(maxValue, value)
    }
  }
  const data = rawData.map((item) => ({
    value: item,
    label: { color: item[2] > maxValue * 0.55 ? "#ffffff" : "#1d2939" },
  }))
  topicEvolutionChart.resize()
  topicEvolutionChart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter(params: any) {
        const item = params.data?.value || []
        return `${escapeHtml(item[7])} · ${escapeHtml(item[3])}<br>帖子 ${formatNumber(item[4])}<br>同期占比 ${formatPercent(item[5])}<br>平均回复 ${formatNumber(item[6], 1)}`
      },
    },
    grid: { top: 18, right: 24, bottom: 92, left: 24 },
    dataZoom: heatmapDataZoom(topicBuckets.value, element),
    xAxis: {
      type: "category",
      data: topicBuckets.value,
      axisTick: { alignWithLabel: true },
      axisLabel: { interval: 0, rotate: 45, fontSize: 11, color: chartTheme.axis },
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "category",
      data: ranks,
      inverse: true,
      axisLabel: { show: false },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    visualMap: {
      show: false,
      min: 0,
      max: maxValue || 1,
      dimension: 2,
      calculable: false,
      orient: "horizontal",
      left: 72,
      top: 4,
      itemWidth: 12,
      itemHeight: 128,
      text: ["帖子", ""],
      textGap: 6,
      textStyle: { color: chartTheme.axis, fontSize: 12 },
      inRange: { color: heatmapColors },
    },
    series: [{
      type: "heatmap",
      data,
      progressive: 1000,
      label: {
        show: true,
        fontSize: 11,
        width: 78,
        overflow: "truncate",
        formatter(params: any) {
          const item = params.data?.value || []
          return item[3] || ""
        },
      },
      itemStyle: { borderColor: "#ffffff", borderWidth: 1 },
      emphasis: {
        itemStyle: { color: "#d94841", borderColor: "#ffffff", borderWidth: 1 },
        label: { color: "#ffffff", fontWeight: 700 },
      },
    }],
  } as any, true)
  hoveredEvolutionTag = ""
  topicEvolutionChart.off("mouseover")
  topicEvolutionChart.off("globalout")
  topicEvolutionChart.off("click")
  topicEvolutionChart.on("mouseover", (params: any) => {
    const tag = params.data?.value?.[3]
    if (tag) highlightEvolutionTag(tag)
  })
  topicEvolutionChart.on("globalout", clearEvolutionHighlight)
  topicEvolutionChart.on("click", (params: any) => {
    const tag = params.data?.value?.[3]
    if (tag) {
      topicEvolutionChart?.dispatchAction({ type: "hideTip" })
      openTopicDetail(tag)
    }
  })
}

function clearEvolutionHighlight() {
  if (!topicEvolutionChart || !hoveredEvolutionTag) return
  topicEvolutionChart.dispatchAction({
    type: "downplay",
    seriesIndex: 0,
    dataIndex: topicEvolutionTagIndices.get(hoveredEvolutionTag) || [],
  })
  hoveredEvolutionTag = ""
}

function highlightEvolutionTag(tag: string) {
  if (!topicEvolutionChart || !tag || tag === hoveredEvolutionTag) return
  clearEvolutionHighlight()
  hoveredEvolutionTag = tag
  topicEvolutionChart.dispatchAction({
    type: "highlight",
    seriesIndex: 0,
    dataIndex: topicEvolutionTagIndices.get(tag) || [],
  })
}

function renderTopicTrend() {
  const element = document.getElementById("topic-trend")
  if (!element) return
  if (!topicTrendChart || topicTrendChart.getDom() !== element) {
    topicTrendChart?.dispose()
    topicTrendChart = chartRuntime?.initChart(element) || null
  }
  if (!topicTrendChart) return
  const legendLayout = wrappedLegendLayout(element, trendTags.value)
  const chartSides = responsiveChartSides(element)
  topicTrendChart.resize()
  const totals = periodsByBucket()
  const series = trendTags.value.map((tag, index) => ({
    name: tag,
    type: "line",
    data: topicBuckets.value.map((bucket) => {
      return tagValues.value.get(bucket)?.get(tag)?.count || 0
    }),
    showSymbol: false,
    symbolSize: 7,
    lineStyle: { color: selectedTag.value === tag ? chartTheme.selected : categoricalColors[index], width: selectedTag.value === tag ? 3.2 : 2 },
    itemStyle: { color: selectedTag.value === tag ? chartTheme.selected : categoricalColors[index] },
    emphasis: { focus: "series", lineStyle: { width: 4 } },
  }))
  topicTrendChart.setOption({
    aria: { enabled: true },
    animation: false,
    color: categoricalColors,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { color: "#98a2b3", width: 1 } },
      formatter(params: any[]) {
        const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
        const values = items.map((item) => {
          const count = Number(item.value)
          const share = count / Math.max(1, totals.get(String(item.axisValue)) || 0) * 100
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:150px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${formatNumber(count)} <small style="color:#667085;font-weight:400">${share.toFixed(2)}%</small></strong></span>`
        }).join("")
        return `<div style="min-width:330px"><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 18px;margin-top:8px">${values}</div></div>`
      },
    },
    legend: legendLayout.option,
    grid: { top: 24, ...chartSides, bottom: legendLayout.gridBottom },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: topicBuckets.value,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "value",
      name: "帖子数",
      min: 0,
      nameTextStyle: { color: chartTheme.axis, fontSize: 12 },
      axisLabel: { color: chartTheme.axis, fontSize: 11 },
      splitLine: { lineStyle: { color: "#edf0f3" } },
    },
    series,
  } as any, true)
  topicTrendChart.off("click")
  topicTrendChart.on("click", (params: any) => {
    if (params.seriesName) openTopicDetail(params.seriesName)
  })
}

function renderSelectedTopicTrend() {
  if (!selectedTag.value || !selectedTagDetail.value) return
  const chart = managedChart("topic-detail-trend")
  if (!chart) return
  const element = chart.getDom()
  const seriesDetails = [
    { name: selectedTag.value, detail: selectedTagDetail.value, color: chartTheme.selected, main: true },
    ...comparedTags.value.map((tag, index) => ({
      name: tag,
      detail: tagComparisonDetails.value[tag],
      color: comparisonColors[index],
      main: false,
    })),
  ].filter(item => Boolean(item.detail))
  const periods = [...periodsByBucket().keys()]
  const totals = periodsByBucket()
  const selectablePeriods = new Set(topicDetailPeriodOptions.value)
  const chartSeries = seriesDetails.map(item => {
    const detailValues = aggregateSeriesRows(item.detail.rows || [], 1, 2, 3)
    return {
      name: item.name,
      type: "line",
      data: periods.map(period => {
        const count = detailValues.get(period)?.get(item.name)?.count || 0
        if (!item.main) return count
        const selected = selectedTopicDetailPeriod.value === period
        const selectable = count > 0 && selectablePeriods.has(period)
        return {
          value: count,
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
      showSymbol: item.main || periods.length <= 24,
      symbol: "circle",
      symbolSize: 6,
      smooth: false,
      cursor: item.main ? "pointer" : "default",
      lineStyle: { color: item.color, width: item.main ? 3 : 2.2 },
      itemStyle: { color: item.color },
      areaStyle: item.main && seriesDetails.length === 1 ? { color: "rgba(217, 72, 65, 0.08)" } : undefined,
      emphasis: {
        focus: "series",
        lineStyle: { width: item.main ? 4 : 3.5 },
      },
    }
  })
  const legendLayout = seriesDetails.length > 1
    ? wrappedLegendLayout(element, seriesDetails.map(item => item.name))
    : null
  const chartSides = responsiveChartSides(element)
  if (!legendLayout) element.style.height = "300px"
  element.dataset.selectedPeriod = selectedTopicDetailPeriod.value
  chart.resize()
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    color: seriesDetails.map(item => item.color),
    tooltip: {
      trigger: "axis",
      confine: true,
      formatter(params: any[]) {
        const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
        const rows = items.map(item => {
          const count = Number(item.value || 0)
          const share = count / Math.max(1, totals.get(String(item.axisValue)) || 0) * 100
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:180px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${formatNumber(count)} <small style="color:#667085;font-weight:400">${share.toFixed(2)}%</small></strong></span>`
        }).join("")
        return `<div><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;gap:6px;margin-top:8px">${rows}</div></div>`
      },
    },
    legend: legendLayout?.option || { show: false },
    grid: { top: 24, ...chartSides, bottom: legendLayout?.gridBottom || 48 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: periods,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "value",
      name: "帖子数",
      min: 0,
      nameTextStyle: { color: chartTheme.axis, fontSize: 12 },
      axisLabel: { color: chartTheme.axis, fontSize: 11 },
      splitLine: { lineStyle: { color: "#edf0f3" } },
    },
    series: chartSeries,
  } as any, true)
  clearLegendHoverAfterSelection(chart)
  chart.off("click")
  chart.on("click", (params: any) => {
    const period = String(params.name || "")
    if (
      params.componentType === "series"
      && params.seriesName === selectedTag.value
      && topicDetailPeriodOptions.value.includes(period)
    ) {
      scrollToTopicPostsAfterPeriodChange = true
      selectedTopicDetailPeriod.value = selectedTopicDetailPeriod.value === period
        ? ""
        : period
    }
  })
}

function nodeValuesFor(rows: any[]) {
  const values = new Map<string, { count: number; replies: number }>()
  for (const row of rows) {
    const current = values.get(row[1]) || { count: 0, replies: 0 }
    current.count += row[2]
    current.replies += row[3]
    values.set(row[1], current)
  }
  return values
}

function nodeLabel(node: string) {
  const label = nodeLabels.value[node]
  if (!label) return node
  return label.toLocaleLowerCase("zh-CN") === node.toLocaleLowerCase("zh-CN")
    ? label
    : `${label} · ${node}`
}

function hasNodeDetail(node: string) {
  return analyzedNodeNames.value.has(node)
}

function topicTagUrl(tag: string) {
  return `https://www.v2ex.com/tag/${encodeURIComponent(tag)}`
}

function memberUrl(username: string) {
  return `https://www.v2ex.com/member/${encodeURIComponent(username)}`
}

const nodeInsights = computed(() => {
  const currentRows = nodes.value.rows.filter((row: any[]) => inRange(row[0]))
  const previousPeriods = previousRawPeriods.value
  const start = previousPeriods[0]?.period || ""
  const end = previousPeriods[previousPeriods.length - 1]?.period || ""
  const previousRows = nodes.value.rows.filter((row: any[]) => row[0] >= start && row[0] <= end)
  const current = nodeValuesFor(currentRows)
  const previous = nodeValuesFor(previousRows)
  const total = [...current.values()].reduce((sum, item) => sum + item.count, 0)
  const rows = [...current.entries()].map(([node, item]) => {
    const previousCount = previous.get(node)?.count || 0
    return {
      node,
      label: nodeLabel(node),
      count: item.count,
      share: total ? item.count / total * 100 : 0,
      intensity: item.count ? item.replies / item.count : 0,
      growth: previousCount >= 20 ? (item.count - previousCount) / previousCount * 100 : null,
      delta: item.count - previousCount,
      previousCount,
    }
  }).filter((item) => hasNodeDetail(item.node))
  const coreRows = rows.filter((item) => item.count >= 1000)
  return {
    all: [...rows].sort((a, b) => b.count - a.count || a.node.localeCompare(b.node)),
    top: [...rows].sort((a, b) => b.count - a.count).slice(0, 24),
    topShare: [...rows].sort((a, b) => b.count - a.count).slice(0, 5)
      .reduce((sum, item) => sum + item.share, 0),
    rising: [...rows].filter((item) => item.count >= 500 && item.previousCount >= 200 && item.delta >= 100)
      .sort((a, b) => b.delta - a.delta).slice(0, 10),
    coreDiscussed: coreRows
      .sort((a, b) => b.intensity - a.intensity).slice(0, 10),
  }
})

const nodeSearchOptions = computed<SearchOption[]>(() => {
  const current = new Map(nodeInsights.value.all.map((item) => [item.node, item.count]))
  return Object.entries(nodeDetailIndex.value.nodes || {})
    .map(([node, rawEntry]) => {
      const entry = rawEntry as any
      return {
        value: node,
        label: nodeLabel(node),
        meta: current.has(node)
          ? `${formatNumber(current.get(node) || 0)} 所选范围 · ${formatNumber(entry.total)} 历史累计`
          : `${formatNumber(entry.total)} 个帖子`,
        count: current.get(node) ?? entry.total,
      }
    })
    .sort((left, right) => right.count - left.count || left.label.localeCompare(right.label, "zh-CN"))
})

const selectedNodeSummary = computed(() => {
  if (!selectedNode.value || !selectedNodeDetail.value) return null
  const rows = (selectedNodeDetail.value.rows || []).filter((row: any[]) => inRange(row[0]))
  const count = rows.reduce((sum: number, row: any[]) => sum + row[2], 0)
  const replies = rows.reduce((sum: number, row: any[]) => sum + row[3], 0)
  const clicks = rows.reduce((sum: number, row: any[]) => sum + row[4], 0)
  const peak = [...rows].sort((left, right) => right[2] - left[2])[0]
  return {
    count,
    share: currentSummary.value.topics ? count / currentSummary.value.topics * 100 : 0,
    repliesPerTopic: count ? replies / count : 0,
    clicksPerTopic: count ? clicks / count : 0,
    peak: peak?.[0] || "-",
  }
})

const nodeDetailPeriodOptions = computed(() => {
  if (!selectedNodeDetail.value) return [""]
  const periods = new Set<string>()
  for (const row of selectedNodeDetail.value.rows || []) {
    if (inRange(row[0]) && Number(row[2]) > 0) periods.add(bucketFor(row[0]))
  }
  return [...periods].sort().concat("")
})
const nodeDetailPeriodLabels = { "": "全部时间" }

const nodeDetailRankingColumns = computed<RankedColumn[]>(() => selectedNodeDetail.value ? [
  {
    key: "tags",
    title: "主要话题",
    items: selectedNodeDetail.value.tags.map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`, action: `topic:${item[0]}`,
    })),
  },
  {
    key: "content",
    title: "主要标题关键词",
    items: (selectedNodeDetail.value.content_terms || []).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`, action: `content:${item[0]}`,
    })),
  },
  {
    key: "authors",
    title: "活跃用户",
    items: selectedNodeDetail.value.authors.map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 帖子`, action: `member:${item[0]}`,
    })),
  },
] : [])

async function openNodeDetail(node: string) {
  if (!hasNodeDetail(node)) return
  selectedNodeDetailPeriod.value = ""
  nodePeriodPosts.value = []
  activeTab.value = "content"
  contentView.value = "node-detail"
  selectedNode.value = node
}

function renderSelectedNodeTrend() {
  if (!selectedNode.value || !selectedNodeDetail.value) return
  const chart = managedChart("node-detail-trend")
  if (!chart) return
  const element = chart.getDom()
  const values = new Map<string, { count: number; replies: number }>()
  for (const row of selectedNodeDetail.value.rows || []) {
    if (!inRange(row[0])) continue
    const period = bucketFor(row[0])
    const current = values.get(period) || { count: 0, replies: 0 }
    current.count += row[2]
    current.replies += row[3]
    values.set(period, current)
  }
  const periods = [...values.keys()].sort()
  const selectablePeriods = new Set(nodeDetailPeriodOptions.value)
  const eventMarkers = communityEvents.value
    .map((event: any) => ({ ...event, axisPeriod: grain.value === "year" ? event.period.slice(0, 4) : event.period }))
    .filter((event: any, index: number, items: any[]) => periods.includes(event.axisPeriod)
      && items.findIndex((candidate) => candidate.axisPeriod === event.axisPeriod && candidate.title === event.title) === index)
  const legendLayout = wrappedLegendLayout(element, ["帖子", "平均回复"])
  const chartSides = responsiveChartSides(element, true)
  const countColor = chartTheme.primary
  const replyColor = chartTheme.secondary
  element.dataset.selectedPeriod = selectedNodeDetailPeriod.value
  chart.resize()
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    color: [countColor, replyColor],
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { color: chartTheme.pointer, width: 1 } },
      formatter(params: any[]) {
        const period = String(params[0]?.axisValue || "")
        const value = values.get(period)
        return `<div><strong>${escapeHtml(period)}</strong><div style="display:grid;gap:6px;margin-top:8px"><span style="display:flex;justify-content:space-between;gap:18px"><span>帖子</span><strong>${formatNumber(value?.count || 0)}</strong></span><span style="display:flex;justify-content:space-between;gap:18px"><span>平均回复</span><strong>${formatNumber(value?.count ? value.replies / value.count : 0, 2)}</strong></span></div></div>`
      },
    },
    legend: legendLayout.option,
    grid: { top: 28, ...chartSides, bottom: legendLayout.gridBottom },
    xAxis: {
      type: "category", boundaryGap: false, data: periods,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: chartTheme.axisLine } },
    },
    yAxis: [
      {
        type: "value", name: "帖子数", min: 0,
        nameTextStyle: { color: chartTheme.axis, fontSize: 12 },
        axisLabel: { color: chartTheme.axis, fontSize: 11 },
        splitLine: { lineStyle: { color: chartTheme.gridLine } },
      },
      {
        type: "value", name: "平均回复", min: 0, position: "right",
        nameTextStyle: { color: replyColor, fontSize: 12 },
        axisLabel: { color: replyColor, fontSize: 11 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "帖子", type: "line", symbol: "circle", showSymbol: true, cursor: "pointer",
        data: periods.map(period => {
          const selected = selectedNodeDetailPeriod.value === period
          const selectable = selectablePeriods.has(period)
          return {
            value: values.get(period)?.count || 0,
            symbolSize: selectable ? (selected ? 9 : 5) : 0,
            itemStyle: {
              color: selected ? countColor : "#ffffff",
              borderColor: countColor,
              borderWidth: selected ? 2 : 1.5,
            },
            emphasis: {
              scale: 1.3,
              itemStyle: { color: selected ? countColor : "#ffffff", borderColor: countColor, borderWidth: 2 },
            },
          }
        }),
        lineStyle: { color: countColor, width: 3 },
        itemStyle: { color: countColor },
        emphasis: { focus: "series", lineStyle: { width: 4 } },
        markLine: eventMarkers.length ? {
          silent: true, symbol: ["none", "none"],
          lineStyle: { color: chartTheme.pointer, type: "dashed", width: 1 },
          label: { color: chartTheme.axis, fontSize: 11, formatter: "{b}", position: "insideEndTop" },
          data: eventMarkers.map((event: any) => ({ name: event.short_label, xAxis: event.axisPeriod })),
        } : undefined,
      },
      {
        name: "平均回复", type: "line", yAxisIndex: 1,
        data: periods.map(period => {
          const value = values.get(period)
          return value?.count ? value.replies / value.count : 0
        }),
        showSymbol: periods.length <= 24, symbolSize: 6,
        lineStyle: { color: replyColor, width: 1.6, type: "dashed", opacity: 0.78 },
        itemStyle: { color: replyColor, opacity: 0.78 },
        emphasis: { focus: "series", lineStyle: { width: 2.8, opacity: 1 } },
      },
    ],
  } as any, true)
  clearLegendHoverAfterSelection(chart)
  chart.off("click")
  chart.on("click", (params: any) => {
    const period = String(params.name || "")
    if (
      params.componentType === "series"
      && params.seriesName === "帖子"
      && nodeDetailPeriodOptions.value.includes(period)
    ) {
      scrollToNodePostsAfterPeriodChange = true
      selectedNodeDetailPeriod.value = selectedNodeDetailPeriod.value === period ? "" : period
    }
  })
}

function renderNodeStructure() {
  const rows = nodeInsights.value.top
  const chart = managedChart("node-structure")
  if (!chart) return
  const element = chart.getDom()
  const compact = window.innerWidth <= 680 || element.clientWidth <= 420
  element.style.height = compact ? `${Math.max(620, rows.length * 24 + 80)}px` : ""
  chart.resize()
  const sharedOption = {
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter(params: any) {
        const item = rows[params.dataIndex]
        return `${escapeHtml(item.label)}<br>帖子 ${formatNumber(item.count)}<br>份额 ${item.share.toFixed(1)}%<br>平均回复 ${item.intensity.toFixed(1)}`
      },
    },
  }
  chart.setOption(compact ? {
    ...sharedOption,
    grid: { top: 12, right: 50, bottom: 38, left: 4, containLabel: true },
    xAxis: {
      type: "value", name: "帖子数", min: 0,
      nameTextStyle: { color: chartTheme.axis, fontSize: 11 },
      axisLabel: { color: chartTheme.axis, fontSize: 10 },
      splitLine: { lineStyle: { color: chartTheme.gridLine } },
    },
    yAxis: {
      type: "category", inverse: true, data: rows.map((item) => String(item.label).split(" · ")[0]),
      axisLabel: { width: 82, overflow: "truncate", color: chartTheme.axis, fontSize: 10 },
      axisLine: { show: false }, axisTick: { show: false },
    },
    series: [{
      type: "bar", data: rows.map((item) => item.count), barMaxWidth: 14,
      itemStyle: { color: "#4e79a7" },
      label: { show: true, position: "right", color: "#475467", fontSize: 10, formatter: (params: any) => `${rows[params.dataIndex].share.toFixed(1)}%` },
      labelLayout: { hideOverlap: true },
    }],
  } : {
    ...sharedOption,
    grid: { top: 24, right: 24, bottom: 120, left: 72 },
    xAxis: { type: "category", data: rows.map((item) => item.label), axisLabel: { rotate: 35, color: chartTheme.axis, fontSize: 11 }, axisLine: { lineStyle: { color: chartTheme.axisLine } } },
    yAxis: { type: "value", name: "帖子数", min: 0, axisLabel: { color: chartTheme.axis, fontSize: 11 }, splitLine: { lineStyle: { color: chartTheme.gridLine } } },
    series: [{
      type: "bar", data: rows.map((item) => item.count), barMaxWidth: 38,
      itemStyle: { color: "#4e79a7" },
      label: { show: true, position: "top", color: "#475467", fontSize: 11, formatter: (params: any) => `${rows[params.dataIndex].share.toFixed(1)}%` },
      labelLayout: { hideOverlap: true },
    }],
  } as any, true)
  chart.off("click")
  chart.on("click", (params: any) => {
    const node = rows[params.dataIndex]?.node
    if (node) void openNodeDetail(node)
  })
}

function renderNodeTrend() {
  const values = aggregateSeriesRows(nodes.value.rows, 1, 2, 3)
  const totals = periodsByBucket()
  const buckets = [...values.keys()].sort()
  const names = nodeInsights.value.top.slice(0, nodeTrendLimit.value).map((item) => item.node)
  renderLineChart("node-trend", buckets, names.map((node, index) => ({
    name: nodeLabel(node),
    data: buckets.map((bucket) => values.get(bucket)?.get(node)?.count || 0),
    secondaryData: buckets.map((bucket) => (values.get(bucket)?.get(node)?.count || 0) / Math.max(1, totals.get(bucket) || 0) * 100),
    secondarySuffix: "%",
    color: categoricalColors[index],
  })), [{ name: "帖子数" }])
}

function aggregateNumericRows(rows: any[][], valueIndexes: number[]) {
  const values = new Map<string, number[]>()
  for (const row of rows) {
    if (!inRange(row[0])) continue
    const period = bucketFor(row[0])
    const current = values.get(period) || valueIndexes.map(() => 0)
    valueIndexes.forEach((valueIndex, index) => { current[index] += row[valueIndex] })
    values.set(period, current)
  }
  return values
}

function renderMemberTrend() {
  const values = aggregateNumericRows(community.value.rows, [1, 2, 3])
  const periods = [...values.keys()].sort()
  renderLineChart("member-trend", periods, [
    { name: "新增成员", data: periods.map((period) => values.get(period)![0]), color: categoricalColors[0] },
    { name: "发帖用户", data: periods.map((period) => values.get(period)![1]), color: categoricalColors[1] },
    { name: "评论用户", data: periods.map((period) => values.get(period)![2]), color: categoricalColors[2] },
  ], [{ name: grain.value === "month" ? "每月人数" : "年度月份人数之和" }])
}

function renderMemberProfileTrend() {
  if (!selectedMemberProfile.value) return
  const values = new Map<string, number[]>()
  for (const row of memberProfileRowsInRange.value) {
    const period = bucketFor(row[0])
    const current = values.get(period) || [0, 0]
    current[0] += row[1]
    current[1] += row[2]
    values.set(period, current)
  }
  const periods = [...new Set(
    periodOptions.value.filter(inRange).map(bucketFor),
  )].sort()
  renderLineChart("member-profile-trend", periods, [
    { name: "发帖", data: periods.map((period) => values.get(period)?.[0] || 0), color: "#2563eb" },
    { name: "评论", data: periods.map((period) => values.get(period)?.[1] || 0), color: "#d94841", yAxisIndex: 1 },
  ], [{ name: "帖子数" }, { name: "评论数" }])
}

function renderMemberEvolution() {
  const chart = managedChart("member-evolution")
  if (!chart) return
  const periods = memberEvolutionPeriods.value
  const periodIndexes = new Map(periods.map((period, index) => [period, index]))
  const metricLabels: Record<MemberRankingMetric, string> = {
    topics: "发帖",
    comments: "评论",
    thanks: "收到感谢",
  }
  const rawData = memberEvolutionRows.value.map((row: any[]) => [
    periodIndexes.get(row[1]), row[3] - 1, row[5], row[4], row[1], row[3],
  ])
  const maxValue = Math.max(1, ...rawData.map((item: any[]) => Number(item[2])))
  const data = rawData.map((item: any[]) => ({
    value: item,
    label: { color: item[2] > maxValue * 0.55 ? "#ffffff" : "#1d2939" },
  }))
  const usernameIndices = new Map<string, number[]>()
  rawData.forEach((item: any[], index: number) => {
    const indices = usernameIndices.get(item[3]) || []
    indices.push(index)
    usernameIndices.set(item[3], indices)
  })
  const element = chart.getDom()
  chart.resize()
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter(params: any) {
        const item = params.data?.value || []
        const action = hasMemberProfile(item[3]) ? "点击查看成员详情" : "点击查看成员范围说明"
        return `${escapeHtml(item[4])} · 第 ${item[5]} 名<br><strong>${escapeHtml(item[3])}</strong><br>${metricLabels[memberRankingMetric.value]} ${formatNumber(item[2])}<br><span style="color:#667085">${action}</span>`
      },
    },
    grid: { top: 18, right: 24, bottom: 92, left: 24 },
    dataZoom: heatmapDataZoom(periods, element),
    xAxis: {
      type: "category",
      data: periods,
      axisTick: { alignWithLabel: true },
      axisLabel: { interval: 0, rotate: 45, color: chartTheme.axis, fontSize: 11 },
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "category",
      data: Array.from({ length: memberRankingLimit.value }, (_, index) => `第 ${index + 1} 名`),
      inverse: true,
      axisLabel: { show: false },
      axisTick: { show: false },
      axisLine: { show: false },
    },
    visualMap: {
      show: false,
      min: 0,
      max: maxValue,
      dimension: 2,
      inRange: { color: heatmapColors },
    },
    series: [{
      type: "heatmap",
      data,
      progressive: 1000,
      label: {
        show: true,
        fontSize: 11,
        width: 78,
        overflow: "truncate",
        formatter: (params: any) => params.data?.value?.[3] || "",
      },
      itemStyle: { borderColor: "#ffffff", borderWidth: 1 },
      emphasis: {
        itemStyle: { color: "#d94841", borderColor: "#ffffff", borderWidth: 1 },
        label: { color: "#ffffff", fontWeight: 700 },
      },
    }],
  } as any, true)

  let hoveredUsername = ""
  const clearHighlight = () => {
    if (!hoveredUsername) return
    chart.dispatchAction({ type: "downplay", seriesIndex: 0, dataIndex: usernameIndices.get(hoveredUsername) || [] })
    hoveredUsername = ""
  }
  chart.off("mouseover")
  chart.off("globalout")
  chart.off("click")
  chart.on("mouseover", (params: any) => {
    const username = params.data?.value?.[3]
    if (!username || username === hoveredUsername) return
    clearHighlight()
    hoveredUsername = username
    chart.dispatchAction({ type: "highlight", seriesIndex: 0, dataIndex: usernameIndices.get(username) || [] })
  })
  chart.on("globalout", clearHighlight)
  chart.on("click", (params: any) => {
    const username = params.data?.value?.[3]
    if (username) openMemberProfile(username)
  })
}

function renderMemberRoles() {
  const aggregated = aggregateNumericRows(community.value.rows, [2, 3])
  const values = [...aggregated.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([period, row]) => ({
    period,
    ratio: row[0] ? row[1] / row[0] : 0,
  }))
  renderLineChart("member-roles", values.map((item: any) => item.period), [
    { name: "评论用户/发帖用户", data: values.map((item: any) => item.ratio), color: "#0f766e", areaColor: "rgba(15,118,110,0.12)" },
  ], [{ name: "人数比" }])
}

function renderEngagementVolume() {
  const values = aggregateNumericRows(engagement.value.rows, [3, 4, 5, 8])
  const periods = [...values.keys()].sort()
  const labels = ["收藏", "感谢", "投票", "评论感谢"]
  renderLineChart("engagement-volume", periods, labels.map((label, index) => ({
    name: label, data: periods.map((period) => values.get(period)![index]), color: categoricalColors[index],
  })), [{ name: "累计互动量" }])
}

function renderEngagementEfficiency() {
  const values = aggregateNumericRows(engagement.value.rows, [1, 2, 3, 4, 5, 6])
  const periods = [...values.keys()].sort()
  renderLineChart("engagement-efficiency", periods, [
    { name: "每千次点击收藏", data: periods.map((period) => { const row = values.get(period)!; return row[1] ? row[2] / row[1] * 1000 : 0 }), color: categoricalColors[0] },
    { name: "每千次回复感谢", data: periods.map((period) => { const row = values.get(period)!; return row[5] ? row[3] / row[5] * 1000 : 0 }), color: categoricalColors[1] },
    { name: "每千个帖子投票", data: periods.map((period) => { const row = values.get(period)!; return row[0] ? row[4] / row[0] * 1000 : 0 }), color: categoricalColors[2] },
  ], [{ name: "每千单位" }])
}

const firstReplyOrder = ["10m", "1h", "6h", "24h", "3d", "7d", "none"]
const lifecycleLabels: Record<string, string> = {
  "10m": "10分钟内", "1h": "10分钟-1小时", "6h": "1-6小时",
  "24h": "6-24小时", "3d": "1-3天", "7d": "3-7天", "none": "7日内无已存回复",
}

function aggregateLifecycleRows(rows: any[][]) {
  const values = new Map<string, Map<string, number>>()
  for (const row of rows) {
    if (!lifecycleInRange(row[0], "first")) continue
    const bucket = bucketFor(row[0])
    if (!values.has(bucket)) values.set(bucket, new Map())
    const periods = values.get(bucket)!
    periods.set(row[1], (periods.get(row[1]) || 0) + row[2])
  }
  return values
}

function renderFirstReplyTrend() {
  const values = aggregateLifecycleRows(lifecycle.value.first_reply_rows)
  const periods = [...values.keys()].sort()
  const colors = ["#0f766e", "#2a9d8f", "#74a57f", "#d6a84b", "#c77732", "#a44a3f", "#98a2b3"]
  const series = firstReplyOrder.map((replyBucket, index) => ({
    name: lifecycleLabels[replyBucket],
    type: "bar",
    stack: "first-reply",
    data: periods.map((period) => {
      const counts = values.get(period)!
      const total = [...counts.values()].reduce((sum, value) => sum + value, 0)
      return total ? ((counts.get(replyBucket) || 0) / total) * 100 : 0
    }),
    itemStyle: { color: colors[index] },
    emphasis: { focus: "series" },
  }))
  const chart = managedChart("first-reply-trend")
  if (!chart) return
  const element = chart.getDom()
  const legendLayout = wrappedLegendLayout(element, series.map((item) => item.name))
  const chartSides = responsiveChartSides(element)
  chart.resize()
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: { trigger: "axis", confine: true, valueFormatter: (value: any) => `${Number(value).toFixed(1)}%` },
    legend: { ...legendLayout.option, itemWidth: 16, itemHeight: 8 },
    grid: { top: 24, ...chartSides, bottom: legendLayout.gridBottom },
    xAxis: { type: "category", data: periods, axisLabel: timeAxisLabel(), axisLine: { lineStyle: { color: "#d9dee7" } } },
    yAxis: { type: "value", name: "帖子占比 (%)", min: 0, max: 100, axisLabel: { color: chartTheme.axis, fontSize: 11 }, splitLine: { lineStyle: { color: chartTheme.gridLine } } },
    series,
  } as any, true)
  clearLegendHoverAfterSelection(chart)
}

function renderDiscussionStructureTrend() {
  const values = new Map<string, number[]>()
  for (const row of lifecycle.value.discussion_structure_rows as any[][]) {
    if (!lifecycleInRange(row[0], "first")) continue
    const bucket = bucketFor(row[0])
    const current = values.get(bucket) || [0, 0, 0, 0, 0]
    for (let index = 0; index < 5; index += 1) current[index] += Number(row[index + 1] || 0)
    values.set(bucket, current)
  }
  const periods = [...values.keys()].sort()
  renderLineChart("discussion-structure-trend", periods, [
    {
      name: "平均参与用户",
      data: periods.map((period) => { const row = values.get(period)!; return row[0] ? row[2] / row[0] : 0 }),
      color: categoricalColors[0],
    },
    {
      name: "人均评论",
      data: periods.map((period) => { const row = values.get(period)!; return row[2] ? row[1] / row[2] : 0 }),
      color: categoricalColors[3],
    },
    {
      name: "楼主参与率",
      data: periods.map((period) => { const row = values.get(period)!; return row[0] ? row[3] / row[0] * 100 : 0 }),
      color: categoricalColors[2],
      role: "secondary",
      yAxisIndex: 1,
      suffix: "%",
    },
    {
      name: "@提及评论",
      data: periods.map((period) => { const row = values.get(period)!; return row[1] ? row[4] / row[1] * 100 : 0 }),
      color: categoricalColors[5],
      role: "secondary",
      yAxisIndex: 1,
      suffix: "%",
    },
  ], [{ name: "人次" }, { name: "占比 (%)", max: 100 }])
}

async function renderActiveTab() {
  await nextTick()
  if (loading.value) return
  const usesCharts = (
    (activeTab.value === "overview" && overviewView.value === "trend")
    || (activeTab.value === "content" && !["content-evolution", "content-detail"].includes(contentView.value))
    || activeTab.value === "community"
    || activeTab.value === "engagement"
  )
  if (!usesCharts) return
  await ensureChartRuntime()
  await nextTick()
  if (activeTab.value === "overview" && overviewView.value === "trend") {
    renderOverviewTrend()
    renderOverviewParticipation()
    renderHeatmap()
  }
  if (activeTab.value === "content" && contentView.value === "topics") {
    renderTopicEvolution()
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    if (activeTab.value !== "content" || contentView.value !== "topics") return
    renderTopicTrend()
  }
  if (activeTab.value === "content" && contentView.value === "topic-detail") renderSelectedTopicTrend()
  if (activeTab.value === "content" && contentView.value === "nodes") {
    renderNodeStructure()
    renderNodeTrend()
  }
  if (activeTab.value === "content" && contentView.value === "node-detail") renderSelectedNodeTrend()
  if (activeTab.value === "community" && communityView.value === "trends") {
    renderMemberEvolution()
    renderMemberTrend()
    renderMemberRoles()
  }
  if (activeTab.value === "community" && communityView.value === "member-detail") renderMemberProfileTrend()
  if (activeTab.value === "content" && contentView.value === "lifecycle") {
    renderPostResponseIntensity()
    renderFirstReplyTrend()
    renderDiscussionStructureTrend()
  }
  if (activeTab.value === "engagement") {
    renderEngagementVolume()
    renderEngagementEfficiency()
  }
}

function reloadPage() {
  window.location.reload()
}

function reportLoadError(error: unknown) {
  loadError.value = error instanceof Error ? error.message : "当前数据加载失败"
}

async function retryActiveData() {
  loadError.value = ""
  clearJsonCache()
  await loadActiveData()
  await renderActiveTab()
}

function normalizeKnownSelection(key: string) {
  if ((key === "topics" || key === "topic-detail") && selectedTag.value) {
    const tagNames = topics.value.tags.map((item: any) => String(item.tag))
    const canonicalTag = tagNames.find((tag: string) => tag === selectedTag.value)
      || tagNames.find((tag: string) => tag.toLocaleLowerCase("en-US") === selectedTag.value.toLocaleLowerCase("en-US"))
    selectedTag.value = canonicalTag || ""
    const normalizedComparisons = comparedTags.value
      .map((value) => tagNames.find((tag: string) => tag === value)
        || tagNames.find((tag: string) => tag.toLocaleLowerCase("en-US") === value.toLocaleLowerCase("en-US")))
      .filter((tag): tag is string => Boolean(tag) && tag !== selectedTag.value)
    comparedTags.value = [...new Set(normalizedComparisons)].slice(0, 4)
  }
  if (key === "node-details" && selectedNode.value && !nodeDetailIndex.value.nodes?.[selectedNode.value]) {
    selectedNode.value = ""
  }
}

async function ensureTopicRows() {
  const shards = topics.value.row_shards || {}
  const momentumStart = shiftMonth(toPeriod.value, -23)
  const loadFrom = fromPeriod.value < momentumStart ? fromPeriod.value : momentumStart
  const startYear = Number(loadFrom.slice(0, 4))
  const endYear = Number(toPeriod.value.slice(0, 4))
  if (!startYear || !endYear) return
  const years = Array.from({ length: endYear - startYear + 1 }, (_, index) => String(startYear + index))
  const missing = years.filter((year) => shards[year] && !loadedTopicRowYears.has(year))
  if (!missing.length) return
  const payloads = await Promise.all(missing.map((year) => getJson(shards[year])))
  topics.value = {
    ...topics.value,
    rows: [
      ...topics.value.rows,
      ...payloads.flatMap((payload) => payload.rows || []),
    ].sort((a: any[], b: any[]) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1], "zh-CN")),
    group_topic_rows: [
      ...(topics.value.group_topic_rows || []),
      ...payloads.flatMap((payload) => payload.group_topic_rows || []),
    ].sort((a: any[], b: any[]) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]) || a[2].localeCompare(b[2], "zh-CN")),
  }
  missing.forEach((year) => loadedTopicRowYears.add(year))
}

function ensureDefaultTopicDetail() {
  if (contentView.value !== "topic-detail") return
  if (!topicDetailTagOptions.value.some(([tag]: [string, number]) => tag === selectedTag.value)) {
    selectedTag.value = topicDetailTagOptions.value[0]?.[0] || ""
  }
}

function ensureDefaultMemberDetail() {
  if (communityView.value !== "member-detail" || selectedMember.value) return
  selectedMember.value = memberProfileIndex.value.criteria?.default_member
    || community.value.top_topic_authors[0]?.username
    || memberSearchOptions.value[0]?.value
    || ""
}

function ensureDefaultNodeDetail() {
  if (contentView.value !== "node-detail") return
  if (!nodeDetailIndex.value.nodes?.[selectedNode.value]) {
    selectedNode.value = nodeSearchOptions.value[0]?.value || ""
  }
}

async function loadActiveData() {
  let key: string = activeTab.value
  if (activeTab.value === "overview") {
    if (overviewView.value === "trend") key = "overview-activity"
    else if (overviewView.value === "distribution") key = "overview-distribution"
    else key = "overview-period"
  }
  if (activeTab.value === "content") {
    if (contentView.value === "lifecycle") key = "lifecycle"
    else if (contentView.value === "nodes") key = "nodes"
    else if (contentView.value === "node-detail") key = "node-details"
    else if (contentView.value === "content-evolution" || contentView.value === "content-detail") key = contentView.value
    else if (contentView.value === "topic-detail") key = "topic-detail"
    else key = "topics"
  }
  if (activeTab.value === "community") {
    key = communityView.value === "member-detail" ? "member-details" : "members"
  }
  if (loadedData.has(key)) {
    loadError.value = ""
    try {
      if (key === "topics") await ensureTopicRows()
      if (key === "nodes") await ensureNodesData()
      if (key === "overview-activity") await ensureOverviewActivityData()
      normalizeKnownSelection(key)
      if (key === "topic-detail") ensureDefaultTopicDetail()
      if (key === "member-details") ensureDefaultMemberDetail()
      if (key === "node-details") {
        ensureDefaultNodeDetail()
        if (selectedNode.value) {
          await loadNodeDetail(selectedNode.value)
          await loadNodePeriodPosts()
        }
      }
      if (key === "topic-detail" && selectedTag.value) {
        await Promise.all([loadTagDetail(selectedTag.value), loadTagComparisonDetails()])
        await loadTopicPeriodPosts()
      }
      if (key === "member-details" && selectedMember.value) await loadMemberProfile(selectedMember.value)
    } catch (error) {
      reportLoadError(error)
    }
    return
  }
  tabLoading.value = true
  loadError.value = ""
  try {
    if (key === "overview-activity") {
      await ensureOverviewActivityData()
    } else if (key === "topics" || key === "topic-detail") {
      if (!loadedData.has("topics-base")) {
        topics.value = { ...topics.value, ...(await getJson("dynamic-topics.json")) }
        loadedData.add("topics-base")
      }
      if (key === "topics") await ensureTopicRows()
    } else if (key === "content-evolution" || key === "content-detail") {
      // The async view owns its year and term-detail requests.
    } else if (key === "nodes") {
      await ensureNodesData()
    } else if (key === "node-details") {
      await ensureNodeDetailIndex()
    } else if (key === "members") {
      await ensureMemberData()
    } else if (key === "member-details") {
      await ensureMemberIndex()
    } else if (key === "lifecycle") {
      lifecycle.value = await getJson("dynamic-lifecycle.json")
    } else if (key === "engagement") {
      engagement.value = await getJson("dynamic-engagement.json")
    } else if (key === "observations") {
      observations.value = await getJson("dynamic-observations.json")
    }
    normalizeKnownSelection(key)
    if (key === "topic-detail") ensureDefaultTopicDetail()
    if (key === "topic-detail" && selectedTag.value) {
      await Promise.all([loadTagDetail(selectedTag.value), loadTagComparisonDetails()])
      await loadTopicPeriodPosts()
    }
    if (key === "member-details") ensureDefaultMemberDetail()
    if (key === "node-details") ensureDefaultNodeDetail()
    if (key === "member-details" && selectedMember.value) await loadMemberProfile(selectedMember.value)
    if (key === "node-details" && selectedNode.value) {
      await loadNodeDetail(selectedNode.value)
      await loadNodePeriodPosts()
    }
    loadedData.add(key)
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "当前页面加载失败"
  } finally {
    tabLoading.value = false
  }
}

watch([fromPeriod, toPeriod, grain], () => {
  if (applyingUrlState || loading.value) return
  selectedTopicDetailPeriod.value = ""
  topicPeriodPosts.value = []
  topicPeriodComments.value = []
  topicPeriodCommentSummary.value = {}
  selectedContentDetailPeriod.value = ""
  selectedNodeDetailPeriod.value = ""
  nodePeriodPosts.value = []
  nodePeriodComments.value = []
  nodePeriodCommentSummary.value = {}
}, { flush: "sync" })
watch([fromPeriod, toPeriod, grain, topLimit, trendLimit, nodeTrendLimit, memberRankingMetric, memberRankingLimit], async () => {
  if (applyingUrlState || loading.value) return
  try {
    if (activeTab.value === "content" && contentView.value === "topics") {
      await ensureTopicRows()
    }
    if (activeTab.value === "content" && contentView.value === "nodes") {
      await ensureNodesData()
    }
    if (activeTab.value === "content" && contentView.value === "topic-detail" && selectedTag.value) {
      await loadTopicPeriodPosts()
    }
    if (activeTab.value === "content" && contentView.value === "node-detail" && selectedNode.value) {
      await loadNodePeriodPosts()
    }
    if (activeTab.value === "overview" && overviewView.value === "trend") {
      await ensureOverviewActivityData()
    }
    await renderActiveTab()
    syncDashboardUrl("replace")
  } catch (error) {
    reportLoadError(error)
  }
})
watch([fromPeriod, toPeriod], () => {
  if (applyingUrlState) return
  topicDetailPostPage.value = 1
})
watch(interactionRanking, () => {
  if (applyingUrlState) return
  postRankingPage.value = 1
})
watch(selectedTag, async () => {
  if (applyingUrlState || loading.value) return
  topicDetailPostPage.value = 1
  comparedTags.value = []
  selectedTopicDetailPeriod.value = ""
  topicPeriodPosts.value = []
  topicPeriodComments.value = []
  topicPeriodCommentSummary.value = {}
  try {
    if (activeTab.value === "content" && contentView.value === "topic-detail") {
      await Promise.all([loadTagDetail(selectedTag.value), loadTagComparisonDetails()])
      await loadTopicPeriodPosts()
    }
    await nextTick()
    if (activeTab.value === "content" && contentView.value === "topic-detail") renderSelectedTopicTrend()
  } catch (error) {
    reportLoadError(error)
  }
})
watch(selectedContentTerm, () => {
  if (applyingUrlState || loading.value) return
  comparedContentTerms.value = []
  selectedContentDetailPeriod.value = ""
})
watch(comparedTags, async () => {
  if (applyingUrlState || loading.value) return
  try {
    if (activeTab.value === "content" && contentView.value === "topic-detail") {
      await loadTagComparisonDetails()
      await nextTick()
      renderSelectedTopicTrend()
    }
  } catch (error) {
    reportLoadError(error)
  }
})
watch(selectedTopicDetailPeriod, async () => {
  if (applyingUrlState || loading.value) return
  topicDetailPostPage.value = 1
  await loadTopicPeriodPosts()
  await nextTick()
  if (activeTab.value === "content" && contentView.value === "topic-detail") {
    renderSelectedTopicTrend()
  }
  if (scrollToTopicPostsAfterPeriodChange) {
    scrollToTopicPostsAfterPeriodChange = false
    await nextTick()
    scrollToSection("topic-representative-posts")
  }
  syncDashboardUrl("replace")
})
watch(selectedMember, async () => {
  if (applyingUrlState || loading.value) return
  try {
    if (activeTab.value === "community") await loadMemberProfile(selectedMember.value)
    await nextTick()
    if (activeTab.value === "community") renderMemberProfileTrend()
  } catch (error) {
    reportLoadError(error)
  }
})
watch(selectedNode, async () => {
  if (applyingUrlState || loading.value) return
  selectedNodeDetailPeriod.value = ""
  nodePeriodPosts.value = []
  nodePeriodComments.value = []
  nodePeriodCommentSummary.value = {}
  try {
    if (activeTab.value === "content" && contentView.value === "node-detail") {
      await loadNodeDetail(selectedNode.value)
      await loadNodePeriodPosts()
      await nextTick()
      renderSelectedNodeTrend()
    }
  } catch (error) {
    reportLoadError(error)
  }
})
watch(selectedNodeDetailPeriod, async () => {
  if (applyingUrlState || loading.value) return
  await loadNodePeriodPosts()
  await nextTick()
  if (activeTab.value === "content" && contentView.value === "node-detail") {
    renderSelectedNodeTrend()
  }
  if (scrollToNodePostsAfterPeriodChange) {
    scrollToNodePostsAfterPeriodChange = false
    await nextTick()
    scrollToSection("node-representative-posts")
  }
  syncDashboardUrl("replace")
})
watch(topicDetailPosts, () => {
  topicDetailPostPage.value = Math.min(topicDetailPostPage.value, topicDetailPostPageCount.value)
})
watch([activeTab, contentView, overviewView, communityView], async () => {
  if (applyingUrlState || loading.value) return
  await loadActiveData()
  if (activeTab.value === "overview" && overviewView.value === "month") await ensureMonthlyData()
  if (activeTab.value === "overview" && overviewView.value === "year") await ensureAnnualData()
  await renderActiveTab()
})
watch([activeTab, contentView, overviewView, communityView, aboutView, catalogType, selectedTag, selectedContentTerm, selectedNode, selectedMember], () => syncDashboardUrl("push"), { flush: "post" })
watch([comparedTags, comparedContentTerms, selectedContentDetailPeriod, selectedNodeDetailPeriod], () => syncDashboardUrl("replace"), { flush: "post" })
watch([catalogSort, catalogGroup], () => syncDashboardUrl("replace"), { flush: "post" })
watch(selectedPeriod, () => syncDashboardUrl("replace"), { flush: "post" })
watch(selectedYear, () => syncDashboardUrl("replace"), { flush: "post" })
watch([interactionRanking, contentHotspotLimit, contentTrendLimit, topicDetailPostPage, postRankingPage, commentRankingPage], () => syncDashboardUrl("replace"), { flush: "post" })

function resizeDashboardCharts() {
  if (topicEvolutionChart?.getDom().isConnected) topicEvolutionChart.resize()
  if (topicTrendChart?.getDom().isConnected) topicTrendChart.resize()
  for (const chart of managedCharts.values()) {
    if (chart.getDom().isConnected) chart.resize()
  }
}

onMounted(async () => {
  window.addEventListener("popstate", restoreDashboardUrl)
  window.addEventListener("resize", resizeDashboardCharts)
  try {
    const [overviewPayload, eventPayload, nodeMetadataPayload] = await Promise.all([
      getJson("dynamic-overview.json"),
      getJson("dynamic-events.json"),
      getJson("dynamic-node-metadata.json"),
    ])
    overview.value = overviewPayload
    communityEvents.value = eventPayload.events || []
    nodeLabels.value = nodeMetadataPayload.labels || {}
    analyzedNodeNames.value = new Set(nodeMetadataPayload.analyzed_nodes || [])
    applyingUrlState = true
    applyUrlState()
    await nextTick()
    applyingUrlState = false
    loading.value = false
    await loadActiveData()
    if (activeTab.value === "overview" && overviewView.value === "month") await ensureMonthlyData()
    if (activeTab.value === "overview" && overviewView.value === "year") await ensureAnnualData()
    await renderActiveTab()
    await scrollToUrlAnchor()
    urlStateReady = true
    syncDashboardUrl("replace")
  } catch (error) {
    applyingUrlState = false
    loading.value = false
    loadError.value = error instanceof Error ? error.message : "基础数据加载失败"
  }
})

onBeforeUnmount(() => {
  window.removeEventListener("popstate", restoreDashboardUrl)
  window.removeEventListener("resize", resizeDashboardCharts)
})
</script>

<template>
  <a class="skip-link" href="#dashboard-main">跳到主要内容</a>
  <main id="dashboard-main" class="dashboard-shell" tabindex="-1">
    <DashboardHeader
      :active-tab="activeTab"
      :tabs="loading ? [] : tabs"
      :data-scope="headerDataScope"
      :compact-data-scope="compactHeaderDataScope"
      :narrow-data-scope="narrowHeaderDataScope"
      @select="selectTab"
    >
      <template #tools><GlobalEntitySearch :node-label="nodeLabel" @select="openGlobalEntity" @browse="openCatalog" /></template>
    </DashboardHeader>

    <SubtabNav v-if="activeTab === 'overview'" :active="overviewView" :items="overviewSubtabs" label="概览页面" @select="selectOverviewView" />
    <GroupedSubtabNav v-if="activeTab === 'content'" :active="contentView" :groups="contentSubtabGroups" label="帖子页面" @select="selectContentView" />
    <SubtabNav v-if="activeTab === 'community'" :active="communityView" :items="communitySubtabs" label="成员页面" @select="selectCommunityView" />
    <section
      v-if="!loading && !['observations', 'about'].includes(activeTab) && !(activeTab === 'overview' && overviewView !== 'trend')"
      class="filter-band"
      :class="{ expanded: filterExpanded }"
      aria-label="全局时间筛选"
    >
      <button class="mobile-filter-summary" type="button" :aria-expanded="filterExpanded" @click="filterExpanded = !filterExpanded">
        <CalendarRange :size="17" aria-hidden="true" />
        <strong>{{ filterSummary }}</strong>
        <SlidersHorizontal :size="16" aria-hidden="true" />
        <ChevronDown class="mobile-filter-chevron" :class="{ expanded: filterExpanded }" :size="16" aria-hidden="true" />
      </button>
      <PeriodSelect v-model="fromPeriod" label="开始月份" :periods="fromPeriodOptions" :latest-first="false" />
      <PeriodSelect v-model="toPeriod" label="结束月份" :periods="toPeriodOptions" />
      <div class="control-group">
        <span>时间粒度</span>
        <div class="segmented">
          <button :class="{ active: grain === 'month' }" @click="grain = 'month'">月</button>
          <button :class="{ active: grain === 'year' }" @click="grain = 'year'">年</button>
        </div>
      </div>
      <div class="quick-ranges">
        <span>快捷范围</span>
        <div class="quick-range-buttons">
          <button
            v-for="preset in quickRanges"
            :key="preset.id"
            :class="{ active: isQuickRangeActive(preset) }"
            :aria-pressed="isQuickRangeActive(preset)"
            @click="applyQuickRange(preset)"
          >{{ preset.label }}</button>
        </div>
      </div>
    </section>

    <LoadingState v-if="loading" label="正在加载看板数据" retry @retry="reloadPage" />
    <LoadingState v-else-if="loadError" :label="loadError" retry @retry="overview.periods.length ? retryActiveData() : reloadPage()" />
    <LoadingState v-else-if="tabLoading" label="正在加载当前页面" />

    <ScaleDistributionView
      v-else-if="activeTab === 'overview' && overviewView === 'distribution'"
    />

    <MonthlyDataView
      v-else-if="activeTab === 'overview' && overviewView === 'month'"
      :profile="monthlyData"
      :loading="monthlyDataLoading"
      :periods="monthlyPeriodOptions"
      :selected-period="selectedPeriod"
      :can-select-node="hasNodeDetail"
      @select-period="selectMonthlyPeriod"
      @select-tag="selectPeriodTag"
      @select-content="openContentDetail"
      @select-node="openNodeDetail"
    />

    <MonthlyDataView
      v-else-if="activeTab === 'overview' && overviewView === 'year'"
      period-type="year"
      :profile="annualData"
      :loading="annualDataLoading"
      :periods="annualPeriodOptions"
      :selected-period="selectedYear"
      :can-select-node="hasNodeDetail"
      @select-period="selectAnnualPeriod"
      @select-tag="selectPeriodTag"
      @select-content="openContentDetail"
      @select-node="openNodeDetail"
    />

    <OverviewTrendView
      v-else-if="activeTab === 'overview'"
      :summary="currentSummary"
      :previous="previousSummary"
      :activity-metric="overviewActivityMetric"
      @select-activity-metric="selectOverviewActivityMetric"
      @ready="renderActiveTab"
    />

    <section v-else-if="activeTab === 'content' && (contentView === 'topics' || contentView === 'topic-detail')" class="view-section">
      <PageHeader v-if="contentView === 'topics'" title="话题演变" description="默认展示所选时间范围内帖子数最多的话题；点击话题即可查看详情。" />

      <div v-if="contentView === 'topics'" class="metric-grid six">
        <article class="metric">
          <span>帖子</span><strong>{{ formatNumber(currentSummary.topics) }}</strong>
          <em :class="{ down: change(currentSummary.topics, previousSummary.topics) < 0 }">较上期 {{ formatPercent(change(currentSummary.topics, previousSummary.topics), true) }}</em>
        </article>
        <article class="metric">
          <span>评论</span><strong>{{ formatNumber(currentSummary.comments) }}</strong>
          <em :class="{ down: change(currentSummary.comments, previousSummary.comments) < 0 }">较上期 {{ formatPercent(change(currentSummary.comments, previousSummary.comments), true) }}</em>
        </article>
        <article class="metric"><span>月均帖子</span><strong>{{ formatNumber(postSummary.monthlyTopics) }}</strong><em>所选时间范围</em></article>
        <article class="metric"><span>平均回复</span><strong>{{ formatNumber(currentSummary.commentsPerTopic, 1) }}</strong><em>每个帖子</em></article>
        <article class="metric"><span>零回复率</span><strong>{{ formatPercent(currentSummary.zeroReplyRate) }}</strong><em>{{ formatNumber(currentSummary.zeroReplies) }} 个帖子</em></article>
        <article class="metric"><span>活跃话题</span><strong>{{ formatNumber(postSummary.activeTags) }}</strong><em>所选时间范围内有发帖</em></article>
      </div>
      <ViewSectionNav v-if="contentView === 'topics'" :items="[
        { id: 'topic-evolution-panel', label: '话题演变' },
        { id: 'topic-trend-panel', label: '话题趋势' },
        { id: 'group-trend-panel', label: '话题板块' },
      ]" />

      <article v-if="contentView === 'topics'" id="topic-evolution-panel" class="analysis-block full section-anchor">
        <header class="block-header-with-control">
        <div><h2>各期话题排名</h2><p>每列展示该月或该年帖子数最多的话题，行表示当期排名；颜色越深，帖子数越多，拖动底部时间条可浏览历史。</p></div>
          <div class="segmented compact-segmented" aria-label="话题数量">
            <button :class="{ active: topLimit === 10 }" @click="topLimit = 10">Top 10</button>
            <button :class="{ active: topLimit === 20 }" @click="topLimit = 20">Top 20</button>
            <button :class="{ active: topLimit === 30 }" @click="topLimit = 30">Top 30</button>
          </div>
        </header>
        <div id="topic-evolution" class="chart evolution-heatmap" :style="topicEvolutionChartStyle"></div>
        <p class="method-note">说明：本看板将 V2EX 帖子携带的原始标签统一称为“话题”；同一帖子可包含多个话题。由标题分词得到的“标题关键词”单独统计，不等同于话题。</p>
        <RankedColumns :columns="topicEvolutionRankingColumns" @select="selectRankedItem" />
      </article>

      <article v-if="contentView === 'topic-detail' && selectedTag" id="topic-detail" class="analysis-block full topic-detail-block">
        <header class="block-header-with-control">
          <div><h2>话题详情：{{ selectedTag }}</h2><p>规模、趋势和代表帖子按所选时间范围统计；关联话题、关联标题关键词、主要节点与活跃用户按全部历史数据统计。</p></div>
          <div class="detail-actions topic-detail-actions">
            <SearchSelect v-model="selectedTag" class="topic-detail-select" label="选择话题" icon="tag" hide-label :options="topicSearchOptions" />
            <a :href="topicTagUrl(selectedTag)" target="_blank" rel="noreferrer">查看 V2EX 话题</a>
          </div>
        </header>
        <div v-if="tagDetailLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="selectedTagDetail && selectedTagStats">
          <div class="metric-grid four topic-detail-metrics">
            <article class="metric"><span>帖子</span><strong>{{ formatNumber(selectedTagStats.count) }}</strong><em>所选时间范围</em></article>
            <article class="metric"><span>帖子占比</span><strong>{{ selectedTagStats.share.toFixed(2) }}%</strong><em>占所选范围有效帖子</em></article>
            <article class="metric"><span>平均回复</span><strong>{{ formatNumber(selectedTagStats.repliesPerTopic, 1) }}</strong><em>每个帖子</em></article>
            <article class="metric"><span>活跃峰值</span><strong>{{ selectedTagStats.peak }}</strong><em>帖子数最高的{{ grain === 'month' ? '月份' : '年份' }}</em></article>
          </div>
          <section class="topic-detail-trend">
            <header class="detail-trend-header">
              <div><h3>{{ selectedTag }} 趋势</h3><p>按{{ grain === 'month' ? '月' : '年' }}展示所选时间范围内的帖子数；点击主话题的空心圆点可查看该期代表帖子，实心圆点表示已选中。</p></div>
              <ComparisonSelect v-model="comparedTags" label="对比话题" :options="topicComparisonOptions" :exclude="[selectedTag]" :suggested-values="topicComparisonSuggestedValues" :loading="tagComparisonLoading" />
            </header>
            <p v-if="tagComparisonError" class="comparison-error">{{ tagComparisonError }}</p>
            <div id="topic-detail-trend" class="chart compact-chart"></div>
          </section>
          <p class="topic-detail-scope-note">以下数据按全部历史记录统计，每栏最多显示 20 项。“{{ selectedTag }}”共涉及 {{ formatNumber(selectedTagDetail.total) }} 个帖子；关联话题来自帖子原始标签，关联标题关键词来自相关帖子标题；节点和用户数量均按包含当前话题的帖子数计算。</p>
          <div class="content-relation-toolbar">
            <span>关联数据</span>
            <div class="segmented compact-segmented" aria-label="话题关联维度">
              <button :class="{ active: topicRelationMode === 'topics' }" @click="topicRelationMode = 'topics'">关联话题</button>
              <button :class="{ active: topicRelationMode === 'content' }" @click="topicRelationMode = 'content'">关联标题关键词</button>
            </div>
          </div>
          <RankedColumns :columns="topicDetailRankingColumns" @select="selectRankedItem" />
          <section id="topic-representative-posts" class="topic-detail-posts representative-posts-anchor">
            <header class="content-section-header">
              <div><h3>{{ topicDetailPostsTitle }}</h3><p>{{ topicDetailPostsDescription }}</p></div>
              <PeriodSelect
                v-model="selectedTopicDetailPeriod"
                class="topic-post-period-select"
                label="代表帖子时间"
                hide-label
                :periods="topicDetailPeriodOptions"
                :option-labels="topicDetailPeriodLabels"
              />
            </header>
            <div v-if="topicPeriodPostsLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
            <p v-else-if="topicPeriodPostsError" class="empty-state compact-empty">{{ topicPeriodPostsError }}</p>
            <div v-else class="post-list topic-representative-list">
              <article v-for="post in displayedTopicDetailPosts" :key="post.id" class="post-row">
                <div class="post-main">
                  <div class="post-meta"><span>{{ formatDateTime(post.create_at) }}</span><button v-if="hasNodeDetail(post.node)" class="text-action" @click="openNodeDetail(post.node)">{{ nodeLabel(post.node) }}</button><span v-else>{{ nodeLabel(post.node) }}</span><span>#{{ post.id }}</span></div>
                  <a :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">{{ post.title }}</a>
                  <div class="post-tags"><button v-for="tag in post.tags.slice(0, 6)" :key="tag" @click="openTopicDetail(tag)">{{ tag }}</button></div>
                </div>
                <dl>
                  <div><dt>点击</dt><dd>{{ formatNumber(post.clicks) }}</dd></div>
                  <div><dt>回复</dt><dd>{{ formatNumber(post.reply_count) }}</dd></div>
                  <div><dt>收藏</dt><dd>{{ formatNumber(post.favorite_count) }}</dd></div>
                  <div><dt>感谢</dt><dd>{{ formatNumber(post.thank_count) }}</dd></div>
                </dl>
              </article>
              <div v-if="!topicDetailPosts.length" class="empty-state compact-empty">所选时间范围内没有该话题的代表帖子。</div>
              <footer v-else-if="topicDetailPosts.length > rankingPageSize" class="ranking-pagination detail-pagination">
                <span>共 {{ formatNumber(topicDetailPosts.length) }} 帖 · 第 {{ topicDetailPostPage }} / {{ topicDetailPostPageCount }} 页</span>
                <nav aria-label="话题代表帖子分页">
                  <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="topicDetailPostPage <= 1" @click="topicDetailPostPage--">‹</button>
                  <template v-for="item in topicDetailPostPaginationItems" :key="item">
                    <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === topicDetailPostPage }" :aria-current="item === topicDetailPostPage ? 'page' : undefined" @click="topicDetailPostPage = item">{{ item }}</button>
                    <span v-else class="pagination-gap" aria-hidden="true">…</span>
                  </template>
                  <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="topicDetailPostPage >= topicDetailPostPageCount" @click="topicDetailPostPage++">›</button>
                </nav>
              </footer>
            </div>
            <p class="method-note representative-note">代表帖子已排除“推广”（promotions）节点；该过滤不影响全站帖子、节点和互动统计。</p>
          </section>
          <RepresentativeComments
            :comments="topicPeriodComments"
            :summary="topicPeriodCommentSummary"
            :title="selectedTopicDetailPeriod ? `${selectedTopicDetailPeriod} 代表评论` : '代表评论'"
            :period="selectedTopicDetailPeriod"
            :description="topicDetailCommentsDescription"
            :loading="topicPeriodCommentsLoading"
            :error="topicPeriodCommentsError"
            empty-text="该话题相关帖子暂无获得感谢的代表评论。"
          />
        </template>
      </article>

      <section v-if="contentView === 'topics'" id="topic-trend-panel" class="topic-trend-view section-anchor" aria-label="话题趋势分析">
        <article class="analysis-block full">
          <header class="block-header-with-control">
            <div><h2>话题趋势</h2><p>展示所选时间范围内主要话题的连续变化。一个帖子可以包含多个话题，因此使用折线图；点击折线可查看话题详情。</p></div>
            <div class="segmented compact-segmented" aria-label="趋势话题数量">
              <button :class="{ active: trendLimit === 10 }" @click="trendLimit = 10">Top 10</button>
              <button :class="{ active: trendLimit === 20 }" @click="trendLimit = 20">Top 20</button>
              <button :class="{ active: trendLimit === 30 }" @click="trendLimit = 30">Top 30</button>
            </div>
          </header>
          <div id="topic-trend" class="chart tall"></div>
        </article>
      </section>

      <section v-if="contentView === 'topics'" id="group-trend-panel" class="topic-group-section section-anchor">
        <article class="analysis-block full">
          <header><h2>话题板块趋势</h2><p>按各期帖子占比观察板块结构变化。一个帖子可以属于多个板块，因此使用折线图。</p></header>
          <AggregateGroupTrend
            :groups="topics.groups"
            :rows="topics.group_rows"
            :period-totals="topicPeriodTotals"
            :from-period="fromPeriod"
            :to-period="toPeriod"
            :grain="grain"
          />
        </article>
        <article class="analysis-block full aggregate-group-panel">
          <header>
            <h2>话题板块</h2>
            <p>根据 V2EX 原始话题和节点汇总社区分类结构，与标题关键词板块分开统计。</p>
          </header>
          <AggregateGroupCards
            embedded
            :cards="topicGroupCards"
            count-label="相关帖子"
            item-label="主要话题"
            empty-text="暂无符合展示条件的话题"
            @select="openTopicGroupTopic"
          />
          <p class="method-note topic-group-note">板块只使用帖子所在节点和 V2EX 原始话题，不读取标题关键词。同一帖子在单个板块内只计一次，但可以进入多个板块，因此各板块数量不能相加。话题至少涉及 3 个帖子且达到板块帖子数的 1%，或累计达到 100 个帖子时显示。推广、拼车、免费和优惠节点不计入；标题中的讨论线索可在“标题关键词演变”中查看。</p>
        </article>
      </section>
    </section>

    <section v-else-if="activeTab === 'content' && contentView === 'nodes'" class="view-section">
      <PageHeader title="节点分布" description="从帖子分区观察主要节点的规模、占比和长期变化，并通过最低帖子数限制减少小样本干扰。" />
      <ViewSectionNav :items="[
        { id: 'node-structure-panel', label: '主要结构' },
        { id: 'node-trend-panel', label: '趋势变化' },
        { id: 'node-insights-panel', label: '节点观察' },
      ]" />
      <article id="node-structure-panel" class="analysis-block full section-anchor">
        <header><h2>主要节点结构</h2><p>展示所选时间范围内帖子数最多的 24 个节点，柱形标注节点帖子占比。</p></header>
        <div id="node-structure" class="chart tall"></div>
      </article>
      <article id="node-trend-panel" class="analysis-block full section-anchor">
        <header class="block-header-with-control">
          <div><h2>主要节点趋势</h2><p>展示当前帖子数最多的节点，观察主要讨论分区随时间的变化。</p></div>
          <div class="segmented compact-segmented" aria-label="趋势节点数量">
            <button :class="{ active: nodeTrendLimit === 5 }" @click="nodeTrendLimit = 5">Top 5</button>
            <button :class="{ active: nodeTrendLimit === 10 }" @click="nodeTrendLimit = 10">Top 10</button>
            <button :class="{ active: nodeTrendLimit === 20 }" @click="nodeTrendLimit = 20">Top 20</button>
          </div>
        </header>
        <div id="node-trend" class="chart tall"></div>
      </article>
      <div id="node-insights-panel" class="node-insights section-anchor">
        <article class="rank-panel">
          <h3>活跃上升节点</h3>
          <div v-for="(item, index) in nodeInsights.rising" :key="item.node" class="insight-row">
            <span>{{ index + 1 }}</span><button class="insight-action" @click="openNodeDetail(item.node)">{{ item.label }}</button>
            <strong>+{{ formatNumber(item.delta) }}</strong><em>{{ formatPercent(item.growth || 0, true) }}</em>
          </div>
          <p class="rank-note">仅统计当前不少于 500 个帖子且上一周期不少于 200 个帖子的节点，并按新增帖子数排序。</p>
        </article>
        <article class="rank-panel">
          <h3>高回复节点</h3>
          <div v-for="(item, index) in nodeInsights.coreDiscussed" :key="item.node" class="insight-row">
            <span>{{ index + 1 }}</span><button class="insight-action" @click="openNodeDetail(item.node)">{{ item.label }}</button>
            <strong>{{ item.intensity.toFixed(1) }} 回复/帖子</strong><em>{{ formatNumber(item.count) }} 帖子</em>
          </div>
          <p class="rank-note">仅统计当前不少于 1,000 个帖子的节点，减少小节点偶发热门帖的影响。</p>
        </article>
      </div>
    </section>

    <NodeDetailView
      v-else-if="activeTab === 'content' && contentView === 'node-detail' && selectedNode"
      :node="selectedNode"
      :loading="nodeDetailLoading"
      :detail="selectedNodeDetail"
      :summary="selectedNodeSummary"
      :options="nodeSearchOptions"
      :columns="nodeDetailRankingColumns"
      :label="nodeLabel(selectedNode)"
      :grain="grain"
      :selected-period="selectedNodeDetailPeriod"
      :period-options="nodeDetailPeriodOptions"
      :period-labels="nodeDetailPeriodLabels"
      :period-posts="nodePeriodPosts"
      :period-posts-loading="nodePeriodPostsLoading"
      :period-posts-error="nodePeriodPostsError"
      :period-comments="nodePeriodComments"
      :period-comment-summary="nodePeriodCommentSummary"
      :period-comments-loading="nodePeriodCommentsLoading"
      :period-comments-error="nodePeriodCommentsError"
      @update:node="selectedNode = $event"
      @update:selected-period="selectedNodeDetailPeriod = $event"
      @select="selectRankedItem"
      @topic="openTopicDetail"
      @member="openMemberProfile"
      @ready="renderSelectedNodeTrend"
    />

    <ContentHotspotsView
      v-else-if="activeTab === 'content' && (contentView === 'content-evolution' || contentView === 'content-detail')"
      :key="contentView"
      :mode="contentView === 'content-evolution' ? 'evolution' : 'detail'"
      :from-period="fromPeriod"
      :to-period="toPeriod"
      :grain="grain"
      :selected-term="selectedContentTerm"
      :compared-terms="comparedContentTerms"
      :selected-period="selectedContentDetailPeriod"
      :top-limit="contentHotspotLimit"
      :trend-limit="contentTrendLimit"
      :node-label="nodeLabel"
      :can-open-node="hasNodeDetail"
      @update:selected-term="selectedContentTerm = $event"
      @update:compared-terms="comparedContentTerms = $event"
      @update:selected-period="selectedContentDetailPeriod = $event"
      @update:top-limit="contentHotspotLimit = $event"
      @update:trend-limit="contentTrendLimit = $event"
      @open-detail="openContentDetail"
      @topic="openTopicDetail"
      @node="openNodeDetail"
      @member="openMemberProfile"
    />

    <section v-else-if="activeTab === 'community'" class="view-section">
      <PageHeader v-if="communityView === 'trends'" title="成员趋势" description="按月统计新注册成员，以及实际参与发帖和评论的去重用户数。" />
      <div v-if="communityView === 'trends'" class="metric-grid five">
        <article class="metric"><span>新增成员</span><strong>{{ formatNumber(memberSummary.newMembers) }}</strong><em>所选时间范围内注册</em></article>
        <article class="metric"><span>月均发帖用户</span><strong>{{ formatNumber(memberSummary.averageAuthors) }}</strong><em>按用户名去重</em></article>
        <article class="metric"><span>月均评论用户</span><strong>{{ formatNumber(memberSummary.averageCommenters) }}</strong><em>按用户名去重</em></article>
        <article class="metric"><span>发帖用户峰值</span><strong>{{ formatNumber(memberSummary.peakAuthors[2]) }}</strong><em>{{ memberSummary.peakAuthors[0] || '-' }}</em></article>
        <article class="metric"><span>评论用户峰值</span><strong>{{ formatNumber(memberSummary.peakCommenters[3]) }}</strong><em>{{ memberSummary.peakCommenters[0] || '-' }}</em></article>
      </div>
      <ViewSectionNav v-if="communityView === 'trends'" :items="[
        { id: 'member-evolution-panel', label: '成员演变' },
        { id: 'member-growth-panel', label: '增长参与' },
        { id: 'member-roles-panel', label: '角色结构' },
      ]" />
      <article v-if="communityView === 'trends'" id="member-evolution-panel" class="analysis-block full member-evolution-block section-anchor">
        <header class="block-header-with-control">
          <div><h2>成员演变</h2><p>展示每月或每年发帖、评论或获得感谢最多的成员；当前年度只统计完整月份。拖动底部时间条可浏览历史，悬停可追踪同一成员，点击可查看详情。感谢数按内容发布时间统计，为当前累计快照。</p></div>
          <div class="member-evolution-controls">
            <div class="segmented compact-segmented" aria-label="成员排名指标">
              <button :class="{ active: memberRankingMetric === 'topics' }" @click="memberRankingMetric = 'topics'">发帖</button>
              <button :class="{ active: memberRankingMetric === 'comments' }" @click="memberRankingMetric = 'comments'">评论</button>
              <button :class="{ active: memberRankingMetric === 'thanks' }" @click="memberRankingMetric = 'thanks'">感谢</button>
            </div>
            <div class="segmented compact-segmented" aria-label="成员排名数量">
              <button :class="{ active: memberRankingLimit === 10 }" @click="memberRankingLimit = 10">Top 10</button>
              <button :class="{ active: memberRankingLimit === 20 }" @click="memberRankingLimit = 20">Top 20</button>
              <button :class="{ active: memberRankingLimit === 30 }" @click="memberRankingLimit = 30">Top 30</button>
            </div>
          </div>
        </header>
        <div id="member-evolution" class="chart evolution-heatmap" :style="memberEvolutionChartStyle"></div>
        <RankedColumns :columns="memberEvolutionRankingColumns" @select="selectRankedItem" />
      </article>
      <p v-if="communityView === 'trends'" class="method-note member-ranking-note">三组榜单使用全站累计数据，不受时间筛选影响；成员演变热力图使用所选时间范围。账号 usdc 的评论感谢值明显异常，已从感谢榜单和感谢演变中排除，汇总指标仍保留数据库原始值。</p>
      <article v-if="communityView === 'member-detail' && selectedMember" id="member-profile" class="analysis-block full member-profile-block">
        <header class="block-header-with-control">
          <div><h2>成员详情：{{ selectedMember }}</h2><p>仅显示部分活跃成员；基于公开发帖、评论和感谢记录描述社区参与，不推断个人属性、职业或立场。</p></div>
          <div class="detail-actions topic-detail-actions">
            <SearchSelect v-model="selectedMember" class="member-detail-select" label="选择成员" icon="user" hide-label :options="memberSearchOptions" />
            <a :href="memberUrl(selectedMember)" target="_blank" rel="noreferrer">V2EX 主页</a>
          </div>
        </header>
        <div v-if="memberProfileLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="selectedMemberProfile">
          <div class="metric-grid six member-profile-metrics">
            <article class="metric"><span>发帖</span><strong>{{ formatNumber(memberProfileSummary.topics) }}</strong><em>所选时间范围</em></article>
            <article class="metric"><span>评论</span><strong>{{ formatNumber(memberProfileSummary.comments) }}</strong><em>所选时间范围</em></article>
            <article class="metric"><span>收到感谢</span><strong>{{ formatNumber(memberProfileSummary.totalThanks) }}</strong><em>帖子 {{ formatNumber(memberProfileSummary.topicThanks) }} / 评论 {{ formatNumber(memberProfileSummary.commentThanks) }}</em></article>
            <article class="metric"><span>活跃月份</span><strong>{{ formatNumber(memberProfileSummary.activePeriods) }}</strong><em>所选时间范围</em></article>
            <article class="metric"><span>累计发帖</span><strong>{{ formatNumber(selectedMemberProfile.totals.topics) }}</strong><em>累计 {{ formatNumber(selectedMemberProfile.totals.comments) }} 条评论</em></article>
            <article class="metric"><span>加入时间</span><strong class="metric-date">{{ selectedMemberProfile.registered_at ? formatDateTime(selectedMemberProfile.registered_at).slice(0, 10) : '未知' }}</strong><em>成员公开档案</em></article>
          </div>
          <section class="member-profile-trend">
            <header><h3>发帖与评论变化</h3><p>随全局日期范围和月/年粒度变化，评论使用右轴。</p></header>
            <div id="member-profile-trend" class="chart compact-chart"></div>
          </section>
          <p class="member-profile-scope-note">以下节点、发帖话题、标题关键词、代表帖子和代表评论按全部历史数据统计，不受上方时间范围影响。标题关键词按包含该词的帖子数计算；代表评论只收录至少获得 1 次感谢的内容。</p>
          <RankedColumns :columns="memberProfileRankingColumns" @select="selectRankedItem" />
          <section class="topic-detail-posts member-profile-posts">
            <header class="content-section-header">
              <h3>代表帖子</h3>
              <button v-if="selectedMemberProfile.posts.length > 10" class="subtle-command list-toggle" @click="memberPostsExpanded = !memberPostsExpanded">{{ memberPostsExpanded ? '收起' : `显示全部 ${selectedMemberProfile.posts.length} 条` }}</button>
            </header>
            <a v-for="post in displayedMemberPosts" :key="post.id" :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">
              <span><strong>{{ post.title }}</strong><small>{{ formatDateTime(post.create_at) }} · {{ nodeLabel(post.node) }} · #{{ post.id }}</small></span>
              <em>{{ formatNumber(post.reply_count) }} 回复</em>
            </a>
            <p v-if="!selectedMemberProfile.posts.length" class="empty-state compact-empty">该成员暂无代表帖子。</p>
          </section>
          <section class="member-profile-comments">
            <header class="content-section-header">
              <h3>代表评论</h3>
              <button v-if="selectedMemberComments.length > 10" class="subtle-command list-toggle" @click="memberCommentsExpanded = !memberCommentsExpanded">{{ memberCommentsExpanded ? '收起' : `显示全部 ${selectedMemberComments.length} 条` }}</button>
            </header>
            <div v-if="memberCommentsLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
            <div v-else class="comment-ranking-list member-comment-list">
              <a v-for="comment in displayedMemberComments" :key="comment.id" class="comment-ranking-row" :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`" target="_blank" rel="noreferrer">
                <span class="comment-ranking-main">
                  <strong>{{ comment.content || '评论原文未收录' }}</strong>
                  <small>{{ formatDateTime(comment.create_at) }} · {{ comment.topic_title }} · #{{ comment.no }}</small>
                </span>
                <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
              </a>
              <p v-if="!selectedMemberComments.length" class="empty-state compact-empty">该成员暂无收到感谢的代表评论。</p>
            </div>
          </section>
        </template>
        <p v-else class="empty-state compact-empty">看板暂未收录该成员的详细数据，可前往 V2EX 主页查看公开资料。</p>
      </article>
      <article v-if="communityView === 'trends'" id="member-growth-panel" class="analysis-block full section-anchor">
        <header><h2>成员增长与参与</h2><p>新增成员按公开档案中的注册时间统计，发帖用户和评论用户按当月实际内容去重。</p></header>
        <div id="member-trend" class="chart tall"></div>
      </article>
      <article v-if="communityView === 'trends'" id="member-roles-panel" class="analysis-block full section-anchor">
        <header><h2>参与角色结构</h2><p>评论用户与发帖用户人数比越高，表示更多用户通过回复参与讨论。</p></header>
        <div id="member-roles" class="chart"></div>
      </article>
    </section>

    <LifecycleView
      v-else-if="activeTab === 'content' && contentView === 'lifecycle'"
      :summary="lifecycleSummary"
      :complete-through="lifecycle.metadata?.long_tail_complete_through"
      @ready="renderActiveTab"
    />

    <EngagementView
      v-else-if="activeTab === 'engagement'"
      :summary="engagementSummary"
      :engagement="engagement"
      :interaction-ranking="interactionRanking"
      :displayed-posts="displayedInteractionPosts"
      :displayed-comments="displayedTopComments"
      :post-page="postRankingPage"
      :comment-page="commentRankingPage"
      :post-page-count="postPageCount"
      :comment-page-count="commentPageCount"
      :post-pagination-items="postPaginationItems"
      :comment-pagination-items="commentPaginationItems"
      :ranking-page-size="rankingPageSize"
      :top-posts-length="topInteractionPosts.length"
      @update:interaction-ranking="interactionRanking = $event"
      @update:post-page="postRankingPage = $event"
      @update:comment-page="commentRankingPage = $event"
      @ready="renderActiveTab"
    />

    <ObservationsView v-else-if="activeTab === 'observations'" :observations="observations" />

    <AnalysisCatalogView
      v-else-if="activeTab === 'about' && aboutView === 'catalog'"
      v-model:type="catalogType"
      v-model:sort="catalogSort"
      v-model:group="catalogGroup"
      :counts="catalogCounts"
      :node-label="nodeLabel"
      @select="openGlobalEntity"
    />

    <AboutView v-else-if="activeTab === 'about'" :summary="aboutSummary" @catalog="openCatalog" />

  </main>
  <DashboardFooter :year="footerYear" @about="openAbout" />
</template>
