<script setup lang="ts">
import { computed, nextTick, onMounted, ref, shallowRef, watch } from "vue"
import DashboardFooter from "./components/DashboardFooter.vue"
import DashboardHeader from "./components/DashboardHeader.vue"
import LoadingState from "./components/LoadingState.vue"
import MonthlyDataView from "./components/MonthlyDataView.vue"
import PeriodSelect from "./components/PeriodSelect.vue"
import RankedColumns from "./components/RankedColumns.vue"
import type { DashboardChart } from "./chartRuntime"

type TabId = "overview" | "content" | "community" | "engagement" | "observations"
type ContentView = "topics" | "topic-detail" | "nodes" | "lifecycle"
type OverviewView = "trend" | "month" | "year"
type CommunityView = "trends" | "member-detail"
type Grain = "month" | "year"
type ValueMode = "count" | "share"
type MemberRankingMetric = "topics" | "comments" | "thanks"
type PaginationItem = number | "gap-start" | "gap-end"

type PeriodMetric = {
  period: string
  topic_count: number
  comment_count: number
  member_count: number
  reply_count: number
  zero_reply_count: number
  click_sum: number
  favorite_sum: number
  thank_sum: number
}

type RepresentativePost = {
  id: number
  period: string
  title: string
  node: string
  tags: string[]
  create_at: number
  clicks: number
  reply_count: number
  favorite_count: number
  thank_count: number
  score: number
}

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
const topics = shallowRef<any>({ tags: [], rows: [], groups: [], group_rows: [], representative_posts: [] })
const tagDetailIndex = shallowRef<any>({ tags: {} })
const selectedTagDetail = shallowRef<any>(null)
const tagDetailLoading = ref(false)
const nodes = shallowRef<any>({ rows: [] })
const lifecycle = shallowRef<any>({ first_reply_rows: [], comment_age_rows: [], long_tail_rows: [] })
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
const communityView = ref<CommunityView>("trends")
const fromPeriod = ref("")
const toPeriod = ref("")
const grain = ref<Grain>("month")
const valueMode = ref<ValueMode>("count")
const topLimit = ref(20)
const trendLimit = ref(10)
const nodeTrendLimit = ref(10)
const memberRankingMetric = ref<MemberRankingMetric>("topics")
const memberRankingLimit = ref(10)
const selectedTag = ref("")
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

let chartRuntime: typeof import("./chartRuntime") | null = null
let chartRuntimeRequest: Promise<typeof import("./chartRuntime")> | null = null
let topicEvolutionChart: DashboardChart | null = null
let topicTrendChart: DashboardChart | null = null
let groupTrendChart: DashboardChart | null = null
const managedCharts = new Map<string, DashboardChart>()
const topicEvolutionTagIndices = new Map<string, number[]>()
const tagDetailBuckets = new Map<string, any>()
const memberProfileBuckets = new Map<string, any>()
const memberCommentBuckets = new Map<string, any>()
const loadedMonthlyRankingPeriods = new Set<string>()
const loadedAnnualRankingYears = new Set<string>()
const loadedTopicRowYears = new Set<string>()
let monthlyRankingIndex: any = null
let annualRankingIndex: any = null
let tagDetailRequestId = 0
let memberProfileRequestId = 0
let memberCommentRequestId = 0
let hoveredEvolutionTag = ""
let representativePostsRequest: Promise<void> | null = null
let tagDetailIndexRequest: Promise<void> | null = null
let applyingUrlState = false
let urlStateReady = false
const categoricalColors = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
  "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
  "#9c755f", "#6b7280", "#2563eb", "#c2410c",
  "#7c3aed", "#0f766e", "#be123c", "#4d7c0f",
  "#0891b2", "#a16207", "#4338ca", "#15803d",
  "#0369a1", "#b91c1c", "#6d28d9", "#047857", "#a21caf",
  "#ca8a04", "#1d4ed8", "#ea580c", "#0e7490", "#65a30d",
]
const nodeLabels: Record<string, string> = {
  qna: "问与答", all4all: "二手交易", programmer: "程序员", jobs: "酷工作",
  share: "分享发现", create: "分享创造", career: "职场话题", life: "生活",
  internet: "互联网", ideas: "奇思妙想", invest: "投资", travel: "旅行",
  bb: "宽带症候群", pointless: "无要点", flamewar: "水深火热",
  flood: "水", random: "随想", in: "邀请码", promotions: "推广", fit: "健康",
  outsourcing: "外包", cv: "求职", free: "免费赠送", deals: "优惠信息",
  exchange: "物物交换", cosub: "拼车", feedback: "反馈", newbie: "新手求助", survey: "调查",
  gts: "全球工单系统", chamber: "爱意满满", autistic: "自言自语",
  dn: "域名", wechat: "微信", fe: "前端开发", tuan: "团购", libido: "情欲",
  monthly: "每月主题", webmaster: "站长",
  ime: "输入法", afterdark: "天黑以后", music: "音乐", movie: "电影",
  tv: "剧集", book: "阅读", games: "游戏", photography: "摄影",
  business: "商业", money: "财富", remote: "远程工作", workplace: "职场",
  beijing: "北京", shanghai: "上海", shenzhen: "深圳", guangzhou: "广州",
  hangzhou: "杭州", chengdu: "成都",
  home: "家居", car: "汽车", hardware: "硬件", cloud: "云计算",
  apple: "Apple", macos: "macOS", iphone: "iPhone", mbp: "MacBook Pro",
  appletv: "Apple TV", ipad: "iPad", airpods: "AirPods",
  android: "Android", linux: "Linux", python: "Python", java: "Java",
  javascript: "JavaScript", golang: "Go", ai: "人工智能",
}

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}

function displayIndex(index: string | number) {
  return Number(index) + 1
}

function formatPercent(value: number | undefined, signed = false) {
  const number = Number(value || 0)
  return `${signed && number > 0 ? "+" : ""}${number.toFixed(1)}%`
}

function formatDateTime(timestamp: number | undefined) {
  if (!timestamp) return "时间未知"
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(timestamp * 1000))
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value || ""
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}`
}

function escapeHtml(value: unknown) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character] || character)
}

function timeAxisLabel(overrides: Record<string, unknown> = {}) {
  return { color: "#667085", fontSize: 10, showMaxLabel: true, ...overrides }
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
  yAxisIndex?: number
  suffix?: string
  areaColor?: string
}

function wrappedLegendLayout(element: HTMLElement, names: string[], itemHeight = 3) {
  const availableWidth = Math.max(240, element.clientWidth - 24)
  let rowWidth = 0
  let rows = 1
  for (const name of names) {
    const textWidth = Array.from(name).reduce(
      (width, character) => width + (character.charCodeAt(0) <= 0xff ? 6.5 : 11),
      0,
    )
    const itemWidth = Math.min(availableWidth, 52 + textWidth)
    if (rowWidth > 0 && rowWidth + itemWidth > availableWidth) {
      rows += 1
      rowWidth = itemWidth
    } else {
      rowWidth += itemWidth
    }
  }
  const legendHeight = rows * 20
  const baseHeight = element.classList.contains("compact-chart")
    ? 300
    : window.innerWidth <= 680
      ? 430
      : element.classList.contains("tall") ? 520 : 400
  element.style.height = `${Math.max(baseHeight, 300 + legendHeight)}px`
  return {
    option: {
      type: "plain",
      bottom: 4,
      left: 12,
      width: availableWidth,
      itemWidth: 18,
      itemHeight,
      itemGap: 14,
      textStyle: { color: "#475467", fontSize: 11, lineHeight: 20 },
    },
    gridBottom: legendHeight + 50,
  }
}

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
      axisPointer: { type: "line", lineStyle: { color: "#98a2b3", width: 1 } },
      formatter(params: any[]) {
        const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
        const rows = items.map((item) => {
          const definition = definitions.find((candidate) => candidate.name === item.seriesName)
          const value = `${formatNumber(Number(item.value), 2)}${definition?.suffix || ""}`
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:145px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${value}</strong></span>`
        }).join("")
        return `<div style="min-width:320px"><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 18px;margin-top:8px">${rows}</div></div>`
      },
    },
    legend: legendLayout?.option || { show: false },
    grid: { top: 28, right: yAxes.length > 1 ? 72 : 24, bottom: legendLayout?.gridBottom || 48, left: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: periods,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: yAxes.map((axis, index) => ({
      type: "value",
      name: axis.name,
      min: 0,
      max: axis.max,
      position: index === 1 ? "right" : "left",
      nameTextStyle: { color: "#667085", fontSize: 11 },
      axisLabel: { color: "#667085", fontSize: 10 },
      splitLine: { show: index === 0, lineStyle: { color: "#edf0f3" } },
    })),
    series: definitions.map((definition, index) => ({
      name: definition.name,
      type: "line",
      data: definition.data,
      yAxisIndex: definition.yAxisIndex || 0,
      showSymbol: periods.length <= 1,
      symbolSize: 7,
      lineStyle: { color: definition.color, width: 2.2 },
      itemStyle: { color: definition.color },
      areaStyle: definition.areaColor ? { color: definition.areaColor } : undefined,
      emphasis: { focus: "series", lineStyle: { width: 4 } },
      markLine: index === 0 && eventMarkers.length ? {
        silent: true,
        symbol: ["none", "none"],
        lineStyle: { color: "#98a2b3", type: "dashed", width: 1 },
        label: { color: "#667085", fontSize: 10, formatter: "{b}", position: "insideEndTop" },
        data: eventMarkers.map((event: any) => ({ name: event.short_label, xAxis: event.axisPeriod })),
      } : undefined,
    })),
  } as any, true)
}

function inRange(period: string) {
  return period >= fromPeriod.value && period <= toPeriod.value
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
}

function isQuickRangeActive(preset: (typeof quickRanges)[number]) {
  const range = quickRangeBounds(preset)
  if (!range) return false
  return fromPeriod.value === range.start && toPeriod.value === range.end
}

const dashboardQueryKeys = [
  "tab", "view", "overview", "community", "from", "to", "grain", "mode", "tag", "member", "period",
  "topicTop", "trendTop", "nodeTop", "memberMetric", "memberTop",
  "topicList", "postSort", "topicPage", "repPage", "postPage", "commentPage",
]

function integerParam(params: URLSearchParams, key: string, allowed?: number[]) {
  const raw = params.get(key) || ""
  if (!/^\d+$/.test(raw)) return null
  const value = Number.parseInt(raw, 10)
  if (!Number.isInteger(value) || value < 1 || (allowed && !allowed.includes(value))) return null
  return value
}

function safeTagParam(value: string | null) {
  const tag = (value || "").trim()
  return tag.length <= 64 && !/[\u0000-\u001f\u007f<>\\/#?&]/.test(tag) ? tag : ""
}

function safeMemberParam(value: string | null) {
  const member = (value || "").trim()
  return /^[A-Za-z0-9_-]{1,64}$/.test(member) ? member : ""
}

function applyUrlState() {
  const params = new URLSearchParams(window.location.search)
  const defaultRange = quickRanges.find((preset) => preset.id === "5y")
  if (defaultRange) applyQuickRange(defaultRange)
  activeTab.value = ["overview", "content", "community", "engagement", "observations"].includes(params.get("tab") || "")
    ? params.get("tab") as TabId
    : "overview"
  const requestedContentView = params.get("view") || ""
  contentView.value = requestedContentView === "posts"
    ? "topic-detail"
    : ["topics", "topic-detail", "nodes", "lifecycle"].includes(requestedContentView)
      ? requestedContentView as ContentView
      : "topics"
  overviewView.value = ["month", "year"].includes(params.get("overview") || "")
    ? params.get("overview") as OverviewView
    : "trend"
  grain.value = params.get("grain") === "year" ? "year" : "month"
  valueMode.value = params.get("mode") === "share" ? "share" : "count"
  topLimit.value = integerParam(params, "topicTop", [10, 20, 30]) || 20
  trendLimit.value = integerParam(params, "trendTop", [10, 20, 30]) || 10
  nodeTrendLimit.value = integerParam(params, "nodeTop", [5, 10, 20]) || 10
  memberRankingMetric.value = ["topics", "comments", "thanks"].includes(params.get("memberMetric") || "")
    ? params.get("memberMetric") as MemberRankingMetric
    : "topics"
  memberRankingLimit.value = integerParam(params, "memberTop", [10, 20, 30]) || 10
  interactionRanking.value = ["favorite_count", "thank_count", "votes", "clicks"].includes(params.get("postSort") || "")
    ? params.get("postSort") as typeof interactionRanking.value
    : "favorite_count"
  selectedTag.value = safeTagParam(params.get("tag"))
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
}

function dashboardUrl() {
  const url = new URL(window.location.href)
  for (const key of dashboardQueryKeys) url.searchParams.delete(key)
  const defaultRange = quickRanges.find((preset) => preset.id === "5y")
  const bounds = defaultRange ? quickRangeBounds(defaultRange) : null
  if (activeTab.value !== "overview") url.searchParams.set("tab", activeTab.value)
  if (activeTab.value === "overview" && overviewView.value !== "trend") {
    url.searchParams.set("overview", overviewView.value)
    url.searchParams.set("period", overviewView.value === "month" ? selectedPeriod.value : selectedYear.value)
  }
  if (activeTab.value === "content" && contentView.value !== "topics") url.searchParams.set("view", contentView.value)
  if (!bounds || fromPeriod.value !== bounds.start || toPeriod.value !== bounds.end) {
    url.searchParams.set("from", fromPeriod.value)
    url.searchParams.set("to", toPeriod.value)
  }
  if (grain.value !== "month") url.searchParams.set("grain", grain.value)
  if (valueMode.value !== "count") url.searchParams.set("mode", valueMode.value)
  if (activeTab.value === "content") {
    if (selectedTag.value) url.searchParams.set("tag", selectedTag.value)
    if (topLimit.value !== 20) url.searchParams.set("topicTop", String(topLimit.value))
    if (trendLimit.value !== 10) url.searchParams.set("trendTop", String(trendLimit.value))
    if (nodeTrendLimit.value !== 10) url.searchParams.set("nodeTop", String(nodeTrendLimit.value))
    if (contentView.value === "topic-detail" && topicDetailPostPage.value > 1) url.searchParams.set("topicPage", String(topicDetailPostPage.value))
  }
  if (activeTab.value === "community") {
    if (communityView.value === "member-detail") url.searchParams.set("community", communityView.value)
    if (communityView.value === "member-detail" && selectedMember.value) url.searchParams.set("member", selectedMember.value)
    if (memberRankingMetric.value !== "topics") url.searchParams.set("memberMetric", memberRankingMetric.value)
    if (memberRankingLimit.value !== 10) url.searchParams.set("memberTop", String(memberRankingLimit.value))
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
const headerDataScope = computed(() => overview.value.metadata.start_period
  ? `数据范围：${overview.value.metadata.start_period} 至 ${overview.value.metadata.default_end_period} · ${formatNumber(defaultScopeSummary.value.members)} 位成员 · ${formatNumber(defaultScopeSummary.value.topics)} 个帖子 · ${formatNumber(defaultScopeSummary.value.comments)} 条评论`
  : "正在读取数据范围")

function selectTab(id: string) {
  activeTab.value = id as TabId
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
  const summary = ranking.summary || { tags: [], nodes: [], members: [], activity: {} }
  const activityMetric = (values: Array<number | null> | undefined) => monthlyMetric(
    Number(values?.[0] || 0),
    values?.[1] == null ? undefined : Number(values[1]),
    values?.[2] == null ? undefined : Number(values[2]),
  )
  const posts = ranking.posts.map((post: RepresentativePost) => ({ ...post, nodeLabel: nodeLabel(post.node) }))
  return {
    period: selectedPeriod.value,
    metrics: {
      topics: metric("topic_count"),
      comments: metric("comment_count"),
      members: metric("member_count"),
      favorites: metric("favorite_sum"),
      thanks: metric("thank_sum"),
      authors: activityMetric(summary.activity?.authors),
      commenters: activityMetric(summary.activity?.commenters),
      commentsPerTopic: monthlyMetric(ratioMetric(current), ratioMetric(previous), ratioMetric(yearAgo)),
    },
    tags: summary.tags || [],
    nodes: (summary.nodes || []).map((item: any) => ({ ...item, label: nodeLabels[item.name] || item.name })),
    members: summary.members || [],
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
  const summary = ranking.summary || { tags: [], nodes: [], members: [], activity: {} }
  const activityMetric = (values: Array<number | null> | undefined) => annualMetric(
    Number(values?.[0] || 0), Number(values?.[2] || 0),
  )
  const posts = (ranking.posts || []).map((post: RepresentativePost) => ({ ...post, nodeLabel: nodeLabel(post.node) }))
  return {
    period: selectedYear.value,
    periodNote: monthCount < 12 ? `截至 ${monthCount} 月` : "",
    metrics: {
      topics: annualMetric(current.topics, previous.topics),
      comments: annualMetric(current.comments, previous.comments),
      members: annualMetric(current.members, previous.members),
      favorites: annualMetric(current.favorites, previous.favorites),
      thanks: annualMetric(current.thanks, previous.thanks),
      authors: activityMetric(summary.activity?.authors),
      commenters: activityMetric(summary.activity?.commenters),
      commentsPerTopic: annualMetric(current.commentsPerTopic, previous.commentsPerTopic),
    },
    tags: summary.tags || [],
    nodes: (summary.nodes || []).map((item: any) => ({ ...item, label: nodeLabels[item.name] || item.name })),
    members: summary.members || [],
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
    await ensureMonthlyRankingData(selectedPeriod.value)
  } finally {
    monthlyDataLoading.value = false
  }
}

async function ensureAnnualData() {
  annualDataLoading.value = true
  try {
    const year = selectedYear.value
    if (loadedAnnualRankingYears.has(year)) return
    if (!annualRankingIndex) annualRankingIndex = await getJson("dynamic-annual-rankings-index.json")
    const shard = annualRankingIndex.years?.[year]
    if (!shard) return
    const payload = await getJson(shard)
    annualRankings.value = { ...annualRankings.value, [year]: payload.ranking }
    loadedAnnualRankingYears.add(year)
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

async function selectPeriodMember(username: string) {
  activeTab.value = "community"
  communityView.value = "member-detail"
  selectedMember.value = username
  await loadActiveData()
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
))
const displayedTopComments = computed(() => engagement.value.top_comments.slice(
  (commentRankingPage.value - 1) * rankingPageSize,
  commentRankingPage.value * rankingPageSize,
))

function paginationItems(current: number, total: number): PaginationItem[] {
  if (total <= 9) return Array.from({ length: total }, (_, index) => index + 1)
  let start = Math.max(2, current - 2)
  let end = Math.min(total - 1, current + 2)
  if (current <= 4) end = 6
  if (current >= total - 3) start = total - 5
  const items: PaginationItem[] = [1]
  if (start > 2) items.push("gap-start")
  for (let page = start; page <= end; page += 1) items.push(page)
  if (end < total - 1) items.push("gap-end")
  items.push(total)
  return items
}

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
const memberEvolutionChartStyle = computed(() => ({
  height: `${Math.max(390, memberRankingLimit.value * 24 + 110)}px`,
}))

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
    key: "topic-nodes", title: "主要发帖节点", items: selectedMemberProfile.value.topic_nodes.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: nodeLabel(item[0]), value: `${formatNumber(item[1])} 主题`, href: `https://www.v2ex.com/go/${item[0]}`,
    })),
  },
  {
    key: "comment-nodes", title: "主要评论节点", items: selectedMemberProfile.value.comment_nodes.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: nodeLabel(item[0]), value: `${formatNumber(item[1])} 评论`, href: `https://www.v2ex.com/go/${item[0]}`,
    })),
  },
  {
    key: "tags", title: "主要发帖标签", items: selectedMemberProfile.value.tags.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 主题`, action: `topic:${item[0]}`,
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
  return {
    eligibleTopics,
    responseRate: eligibleTopics ? ((eligibleTopics - (firstCounts.get("none") || 0)) / eligibleTopics) * 100 : 0,
    within1hRate: eligibleTopics ? (within1h / eligibleTopics) * 100 : 0,
    within24hRate: eligibleTopics ? (within24h / eligibleTopics) * 100 : 0,
    firstHourShare: first7dComments ? (firstHourComments / first7dComments) * 100 : 0,
    after7dShare: comments30d ? (after7d / comments30d) * 100 : 0,
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
const topicEvolutionChartStyle = computed(() => {
  const height = Math.max(360, 112 + topLimit.value * 30)
  return { height: `${height}px` }
})

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

function tagStats(tag: string) {
  const rows = topics.value.rows.filter((row: any[]) => row[1] === tag && inRange(row[0]))
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

const hotTopics = computed(() => selectTopNames(tagValues.value, 20).map(tagStats))
const topicDetailTagOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const row of topics.value.rows) {
    if (inRange(row[0]) && row[2] > 0) counts.set(row[1], (counts.get(row[1]) || 0) + row[2])
  }
  return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "zh-CN"))
})
const topicDetailTagValues = computed(() => topicDetailTagOptions.value.map(([tag]) => tag))
const topicDetailTagLabels = computed(() => Object.fromEntries(
  topicDetailTagOptions.value.map(([tag, count]) => [tag, `${tag} · ${formatNumber(count)}`]),
))
const selectedTagStats = computed(() => selectedTag.value ? tagStats(selectedTag.value) : null)
const memberProfileOptions = computed(() => Object.entries(memberProfileIndex.value.members || {})
  .sort(([left], [right]) => left.localeCompare(right, "en", { sensitivity: "base", numeric: true }))
  .map(([username]) => username))
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
const topicDetailRankingColumns = computed(() => selectedTagDetail.value ? [
  {
    key: "related", title: "关联标签", items: selectedTagDetail.value.related.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 次`, action: `topic:${item[0]}`,
    })),
  },
  {
    key: "nodes", title: "主要节点", items: selectedTagDetail.value.nodes.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: nodeLabel(item[0]), value: `${formatNumber(item[1])} 主题`, href: `https://www.v2ex.com/go/${item[0]}`,
    })),
  },
  {
    key: "authors", title: "活跃用户", items: selectedTagDetail.value.authors.slice(0, 20).map((item: any[]) => ({
      key: item[0], label: item[0], value: `${formatNumber(item[1])} 主题`, href: `https://www.v2ex.com/member/${item[0]}`,
    })),
  },
] : [])

const representativePostsInRange = computed<RepresentativePost[]>(() => (
  topics.value.representative_posts.filter((post: RepresentativePost) => inRange(post.period))
))
const topicDetailPosts = computed<RepresentativePost[]>(() => {
  if (!selectedTag.value) return []
  return representativePostsInRange.value
    .filter((post: RepresentativePost) => post.tags.includes(selectedTag.value))
    .sort((a: RepresentativePost, b: RepresentativePost) => b.score - a.score)
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

async function selectRankedItem(item: any) {
  if (item.action?.startsWith("topic:")) await openTopicDetail(item.action.slice(6))
  if (item.action?.startsWith("member:")) await openMemberProfile(item.action.slice(7))
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
  activeTab.value = "community"
  communityView.value = "member-detail"
  selectedMember.value = username
}

async function ensureRepresentativePosts() {
  if (loadedData.has("representative-posts")) return
  if (!representativePostsRequest) {
    representativePostsRequest = getJson("dynamic-representative-posts.json")
      .then((postData) => {
        topics.value = { ...topics.value, ...postData }
        loadedData.add("representative-posts")
      })
      .finally(() => {
        representativePostsRequest = null
      })
  }
  await representativePostsRequest
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

async function loadTagDetail(tag: string) {
  const requestId = ++tagDetailRequestId
  if (!tag) {
    selectedTagDetail.value = null
    tagDetailLoading.value = false
    return
  }
  await ensureTagDetailIndex()
  if (requestId !== tagDetailRequestId) return
  const entry = tagDetailIndex.value.tags?.[tag]
  if (!entry) {
    selectedTagDetail.value = null
    tagDetailLoading.value = false
    return
  }
  tagDetailLoading.value = true
  try {
    const representativePosts = ensureRepresentativePosts()
    let payload = tagDetailBuckets.get(entry.bucket)
    if (!payload) {
      payload = await getJson(`dynamic-tag-details-${entry.bucket}.json`)
      tagDetailBuckets.set(entry.bucket, payload)
    }
    await representativePosts
    if (requestId === tagDetailRequestId) selectedTagDetail.value = payload.details?.[tag] || null
  } finally {
    if (requestId === tagDetailRequestId) tagDetailLoading.value = false
  }
}

function renderOverviewTrend() {
  const periods = selectedMetrics.value.map((item) => item.period)
  renderLineChart("overview-trend", periods, [
    { name: "主题", data: selectedMetrics.value.map((item) => item.topic_count), color: "#2563eb" },
    { name: "评论", data: selectedMetrics.value.map((item) => item.comment_count), color: "#d94841", yAxisIndex: 1 },
  ], [{ name: "主题数" }, { name: "评论数" }])
}

function renderOverviewParticipation() {
  const periods = selectedMetrics.value.map((item) => item.period)
  renderLineChart("overview-participation", periods, [
    { name: "新增成员", data: selectedMetrics.value.map((item) => item.member_count), color: "#0f766e" },
    { name: "收藏", data: selectedMetrics.value.map((item) => item.favorite_sum), color: "#b45309", yAxisIndex: 1 },
    { name: "感谢", data: selectedMetrics.value.map((item) => item.thank_sum), color: "#7c3aed", yAxisIndex: 1 },
  ], [{ name: "新增成员" }, { name: "互动量" }])
}

function renderPostResponseIntensity() {
  const periods = selectedMetrics.value.map((item) => item.period)
  renderLineChart("post-response-intensity", periods, [
    { name: "评论/主题", data: selectedMetrics.value.map((item) => item.topic_count ? item.comment_count / item.topic_count : 0), color: "#0f766e" },
    { name: "零回复率", data: selectedMetrics.value.map((item) => item.topic_count ? item.zero_reply_count / item.topic_count * 100 : 0), color: "#b45309", yAxisIndex: 1, suffix: "%" },
  ], [{ name: "评论/主题" }, { name: "零回复率 (%)" }])
}

function renderHeatmap() {
  const metric = new Map<string, number>()
  for (const row of overview.value.activity) {
    if (!inRange(row[0])) continue
    const key = `${row[1]}-${row[2]}`
    metric.set(key, (metric.get(key) || 0) + row[4])
  }
  const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
  const chart = managedChart("activity-heatmap")
  if (!chart) return
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
    tooltip: { trigger: "item", confine: true, formatter: (params: any) => `${days[params.value[1]]} ${hours[params.value[0]]}<br>评论 ${formatNumber(params.value[2])}` },
    grid: { top: 18, right: 24, bottom: 42, left: 58 },
    xAxis: { type: "category", data: hours, axisLabel: { color: "#667085", fontSize: 10 }, axisLine: { lineStyle: { color: "#d9dee7" } } },
    yAxis: { type: "category", data: days, axisLabel: { color: "#667085", fontSize: 11 }, axisLine: { lineStyle: { color: "#d9dee7" } } },
    visualMap: { show: false, min: 0, max: maxValue || 1, dimension: 2, inRange: { color: ["#f7f8fa", "#b9d8d0", "#2f8f83", "#0b4f4a"] } },
    series: [{ type: "heatmap", data, itemStyle: { borderColor: "#fff", borderWidth: 1 }, emphasis: { itemStyle: { borderColor: "#111827", borderWidth: 2 } } }],
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
      const value = valueMode.value === "share" ? share : count
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
        return `${escapeHtml(item[7])} · ${escapeHtml(item[3])}<br>主题 ${formatNumber(item[4])}<br>同期占比 ${formatPercent(item[5])}<br>平均回复 ${formatNumber(item[6], 1)}`
      },
    },
    grid: { top: 18, right: 24, bottom: 92, left: 24 },
    dataZoom: heatmapDataZoom(topicBuckets.value, element),
    xAxis: {
      type: "category",
      data: topicBuckets.value,
      axisTick: { alignWithLabel: true },
      axisLabel: { interval: 0, rotate: 45, fontSize: 10, color: "#667085" },
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
      text: [valueMode.value === "share" ? "占比" : "主题", ""],
      textGap: 6,
      textStyle: { color: "#667085", fontSize: 11 },
      inRange: { color: ["#f7f8fa", "#b9d8d0", "#2f8f83", "#0b4f4a"] },
    },
    series: [{
      type: "heatmap",
      data,
      progressive: 1000,
      label: {
        show: true,
        fontSize: 10,
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
  topicTrendChart.resize()
  const totals = periodsByBucket()
  const series = trendTags.value.map((tag, index) => ({
    name: tag,
    type: "line",
    data: topicBuckets.value.map((bucket) => {
      const count = tagValues.value.get(bucket)?.get(tag)?.count || 0
      return valueMode.value === "share" ? count / Math.max(1, totals.get(bucket) || 0) * 100 : count
    }),
    showSymbol: false,
    symbolSize: 7,
    lineStyle: { color: selectedTag.value === tag ? "#111827" : categoricalColors[index], width: selectedTag.value === tag ? 3.5 : 2 },
    itemStyle: { color: selectedTag.value === tag ? "#111827" : categoricalColors[index] },
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
          const value = valueMode.value === "share" ? `${Number(item.value).toFixed(2)}%` : formatNumber(item.value)
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:150px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${value}</strong></span>`
        }).join("")
        return `<div style="min-width:330px"><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 18px;margin-top:8px">${values}</div></div>`
      },
    },
    legend: legendLayout.option,
    grid: { top: 24, right: 24, bottom: legendLayout.gridBottom, left: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: topicBuckets.value,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "value",
      name: valueMode.value === "share" ? "同期占比 (%)" : "主题数",
      min: 0,
      nameTextStyle: { color: "#667085", fontSize: 11 },
      axisLabel: { color: "#667085", fontSize: 10 },
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
  const tag = selectedTag.value
  const values = topicBuckets.value.map((period) => tagValues.value.get(period)?.get(tag)?.count || 0)
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "axis",
      confine: true,
      formatter(params: any[]) {
        const item = params[0]
        return `<strong>${escapeHtml(item?.axisValueLabel || "")}</strong><br>${escapeHtml(tag)}：${formatNumber(item?.value)} 个主题`
      },
    },
    grid: { top: 24, right: 24, bottom: 48, left: 68 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: topicBuckets.value,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "value",
      name: "主题数",
      min: 0,
      nameTextStyle: { color: "#667085", fontSize: 11 },
      axisLabel: { color: "#667085", fontSize: 10 },
      splitLine: { lineStyle: { color: "#edf0f3" } },
    },
    series: [{
      name: tag,
      type: "line",
      data: values,
      showSymbol: values.length <= 24,
      symbolSize: 6,
      smooth: 0.2,
      lineStyle: { color: "#2563eb", width: 2.5 },
      itemStyle: { color: "#2563eb" },
      areaStyle: { color: "rgba(37, 99, 235, 0.10)" },
      emphasis: { focus: "series" },
    }],
  } as any, true)
}

function renderGroupTrend() {
  const element = document.getElementById("group-trend")
  if (!element) return
  if (!groupTrendChart || groupTrendChart.getDom() !== element) {
    groupTrendChart?.dispose()
    groupTrendChart = chartRuntime?.initChart(element) || null
  }
  if (!groupTrendChart) return
  const legendLayout = wrappedLegendLayout(
    element,
    topics.value.groups.map((group: any) => group.label),
  )
  groupTrendChart.resize()
  const values = aggregateSeriesRows(topics.value.group_rows, 1, 2, 3)
  const totals = periodsByBucket()
  const buckets = [...values.keys()].sort()
  const series = topics.value.groups.map((group: any, index: number) => ({
    name: group.label,
    type: "line",
    data: buckets.map((bucket) => {
      const count = values.get(bucket)?.get(group.name)?.count || 0
      return valueMode.value === "share" ? (count / Math.max(1, totals.get(bucket) || 0)) * 100 : count
    }),
    showSymbol: false,
    lineStyle: { color: group.color || categoricalColors[index], width: 2 },
    itemStyle: { color: group.color || categoricalColors[index] },
    emphasis: { focus: "series", lineStyle: { width: 4 } },
  }))
  groupTrendChart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { color: "#98a2b3", width: 1 } },
      formatter(params: any[]) {
        const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
        const rows = items.map((item) => {
          const value = valueMode.value === "share" ? `${Number(item.value).toFixed(2)}%` : formatNumber(item.value)
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;min-width:150px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${value}</strong></span>`
        }).join("")
        return `<div style="min-width:330px"><strong>${escapeHtml(items[0]?.axisValueLabel || "")}</strong><div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 18px;margin-top:8px">${rows}</div></div>`
      },
    },
    legend: legendLayout.option,
    grid: { top: 24, right: 24, bottom: legendLayout.gridBottom, left: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: buckets,
      axisLabel: timeAxisLabel(),
      axisLine: { lineStyle: { color: "#d9dee7" } },
    },
    yAxis: {
      type: "value",
      name: valueMode.value === "share" ? "同期占比 (%)" : "主题数",
      min: 0,
      nameTextStyle: { color: "#667085", fontSize: 11 },
      axisLabel: { color: "#667085", fontSize: 10 },
      splitLine: { lineStyle: { color: "#edf0f3" } },
    },
    series,
  } as any, true)
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
  return nodeLabels[node] ? `${nodeLabels[node]} · ${node}` : node
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
  })
  const coreRows = rows.filter((item) => item.count >= 1000)
  return {
    top: [...rows].sort((a, b) => b.count - a.count).slice(0, 24),
    topShare: [...rows].sort((a, b) => b.count - a.count).slice(0, 5)
      .reduce((sum, item) => sum + item.share, 0),
    rising: [...rows].filter((item) => item.count >= 500 && item.previousCount >= 200 && item.delta >= 100)
      .sort((a, b) => b.delta - a.delta).slice(0, 10),
    coreDiscussed: coreRows
      .sort((a, b) => b.intensity - a.intensity).slice(0, 10),
  }
})

function renderNodeStructure() {
  const rows = nodeInsights.value.top
  const chart = managedChart("node-structure")
  if (!chart) return
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter(params: any) {
        const item = rows[params.dataIndex]
        return `${escapeHtml(item.label)}<br>主题 ${formatNumber(item.count)}<br>份额 ${item.share.toFixed(1)}%<br>平均回复 ${item.intensity.toFixed(1)}`
      },
    },
    grid: { top: 24, right: 24, bottom: 120, left: 72 },
    xAxis: { type: "category", data: rows.map((item) => item.label), axisLabel: { rotate: 35, color: "#667085", fontSize: 10 }, axisLine: { lineStyle: { color: "#d9dee7" } } },
    yAxis: { type: "value", name: "主题数", min: 0, axisLabel: { color: "#667085", fontSize: 10 }, splitLine: { lineStyle: { color: "#edf0f3" } } },
    series: [{ type: "bar", data: rows.map((item) => item.count), barMaxWidth: 38, itemStyle: { color: "#4e79a7" }, label: { show: true, position: "top", color: "#475467", fontSize: 10, formatter: (params: any) => `${rows[params.dataIndex].share.toFixed(1)}%` } }],
  } as any, true)
}

function renderNodeTrend() {
  const values = aggregateSeriesRows(nodes.value.rows, 1, 2, 3)
  const totals = periodsByBucket()
  const buckets = [...values.keys()].sort()
  const names = nodeInsights.value.top.slice(0, nodeTrendLimit.value).map((item) => item.node)
  renderLineChart("node-trend", buckets, names.map((node, index) => ({
    name: nodeLabel(node),
    data: buckets.map((bucket) => {
      const count = values.get(bucket)?.get(node)?.count || 0
      return valueMode.value === "share" ? (count / Math.max(1, totals.get(bucket) || 0)) * 100 : count
    }),
    color: categoricalColors[index],
    suffix: valueMode.value === "share" ? "%" : "",
  })), [{ name: valueMode.value === "share" ? "节点份额 (%)" : "主题数" }])
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
    { name: "发帖者", data: periods.map((period) => values.get(period)![1]), color: categoricalColors[1] },
    { name: "评论者", data: periods.map((period) => values.get(period)![2]), color: categoricalColors[2] },
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
  ], [{ name: "主题数" }, { name: "评论数" }])
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
    label: { color: item[2] > maxValue * 0.4 ? "#ffffff" : "#1d2939" },
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
        const action = hasMemberProfile(item[3]) ? "点击查看成员详情" : "该成员未纳入详情范围"
        return `${escapeHtml(item[4])} · 第 ${item[5]} 名<br><strong>${escapeHtml(item[3])}</strong><br>${metricLabels[memberRankingMetric.value]} ${formatNumber(item[2])}<br><span style="color:#667085">${action}</span>`
      },
    },
    grid: { top: 18, right: 24, bottom: 92, left: 24 },
    dataZoom: heatmapDataZoom(periods, element),
    xAxis: {
      type: "category",
      data: periods,
      axisTick: { alignWithLabel: true },
      axisLabel: { interval: 0, rotate: grain.value === "month" ? 45 : 0, color: "#667085", fontSize: 10 },
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
      inRange: { color: ["#f4f7f7", "#b9d8d0", "#2f8f83", "#0b4f4a"] },
    },
    series: [{
      type: "heatmap",
      data,
      progressive: 1000,
      label: {
        show: true,
        fontSize: 10,
        width: 76,
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
    { name: "评论者/发帖者", data: values.map((item: any) => item.ratio), color: "#0f766e", areaColor: "rgba(15,118,110,0.12)" },
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
    { name: "每千个主题投票", data: periods.map((period) => { const row = values.get(period)!; return row[0] ? row[4] / row[0] * 1000 : 0 }), color: categoricalColors[2] },
  ], [{ name: "标准化互动率" }])
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
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: { trigger: "axis", confine: true, valueFormatter: (value: any) => `${Number(value).toFixed(1)}%` },
    legend: { type: "scroll", bottom: 4, left: 12, right: 12, itemWidth: 16, itemHeight: 8, textStyle: { color: "#475467", fontSize: 11 } },
    grid: { top: 24, right: 24, bottom: 88, left: 72 },
    xAxis: { type: "category", data: periods, axisLabel: timeAxisLabel(), axisLine: { lineStyle: { color: "#d9dee7" } } },
    yAxis: { type: "value", name: "主题占比 (%)", min: 0, max: 100, axisLabel: { color: "#667085", fontSize: 10 }, splitLine: { lineStyle: { color: "#edf0f3" } } },
    series,
  } as any, true)
}

async function renderActiveTab() {
  await nextTick()
  if (loading.value) return
  const usesCharts = (
    (activeTab.value === "overview" && overviewView.value === "trend")
    || activeTab.value === "content"
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
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    if (activeTab.value !== "content" || contentView.value !== "topics") return
    renderGroupTrend()
  }
  if (activeTab.value === "content" && contentView.value === "topic-detail") renderSelectedTopicTrend()
  if (activeTab.value === "content" && contentView.value === "nodes") {
    renderNodeStructure()
    renderNodeTrend()
  }
  if (activeTab.value === "community" && communityView.value === "trends") {
    renderMemberEvolution()
    renderMemberTrend()
    renderMemberRoles()
  }
  if (activeTab.value === "community" && communityView.value === "member-detail") renderMemberProfileTrend()
  if (activeTab.value === "content" && contentView.value === "lifecycle") {
    renderPostResponseIntensity()
    renderFirstReplyTrend()
  }
  if (activeTab.value === "engagement") {
    renderEngagementVolume()
    renderEngagementEfficiency()
  }
}

const getJson = async (path: string) => {
  const response = await fetch(path)
  if (!response.ok) throw new Error(`加载 ${path} 失败：${response.status}`)
  return response.json()
}

function reloadPage() {
  window.location.reload()
}

function normalizeKnownSelection(key: string) {
  if (key === "topics" && selectedTag.value) {
    const knownTag = topics.value.tags.some((item: any) => item.tag === selectedTag.value)
    if (!knownTag) selectedTag.value = ""
  }
  if (key === "members" && selectedMember.value) {
    const knownMember = Boolean(memberProfileIndex.value.members?.[selectedMember.value])
      || community.value.rank_rows.some((row: any[]) => row[4] === selectedMember.value)
    if (!knownMember) selectedMember.value = ""
  }
}

async function ensureTopicRows() {
  const shards = topics.value.row_shards || {}
  const startYear = Number(fromPeriod.value.slice(0, 4))
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
  }
  missing.forEach((year) => loadedTopicRowYears.add(year))
}

function ensureDefaultTopicDetail() {
  if (contentView.value !== "topic-detail") return
  if (!topicDetailTagOptions.value.some(([tag]) => tag === selectedTag.value)) {
    selectedTag.value = topicDetailTagOptions.value[0]?.[0] || ""
  }
}

function ensureDefaultMemberDetail() {
  if (communityView.value !== "member-detail" || selectedMember.value) return
  selectedMember.value = community.value.top_topic_authors[0]?.username || ""
}

async function loadActiveData() {
  let key: string = activeTab.value
  if (activeTab.value === "overview") {
    key = overviewView.value === "trend" ? "overview-activity" : "overview-period"
  }
  if (activeTab.value === "content") {
    if (contentView.value === "lifecycle") key = "lifecycle"
    else if (contentView.value === "nodes") key = "nodes"
    else key = "topics"
  }
  if (activeTab.value === "community") key = "members"
  if (loadedData.has(key)) {
    if (key === "topics") await ensureTopicRows()
    if (key === "topics") ensureDefaultTopicDetail()
    normalizeKnownSelection(key)
    if (key === "members") ensureDefaultMemberDetail()
    if (key === "topics" && contentView.value === "topic-detail" && selectedTag.value) await loadTagDetail(selectedTag.value)
    if (key === "members" && selectedMember.value) await loadMemberProfile(selectedMember.value)
    return
  }
  tabLoading.value = true
  try {
    if (key === "overview-activity") {
      const payload = await getJson("dynamic-overview-activity.json")
      overview.value = { ...overview.value, activity: payload.rows || [] }
    } else if (key === "topics") {
      if (!loadedData.has("topics-base")) {
        topics.value = { ...topics.value, ...(await getJson("dynamic-topics.json")) }
        loadedData.add("topics-base")
      }
      await ensureTopicRows()
    } else if (key === "nodes") {
      nodes.value = await getJson("dynamic-nodes.json")
    } else if (key === "members") {
      const [communityData, profileIndex] = await Promise.all([
        getJson("dynamic-community.json"),
        getJson("dynamic-member-profile-index.json"),
      ])
      community.value = communityData
      memberProfileIndex.value = profileIndex
    } else if (key === "lifecycle") {
      lifecycle.value = await getJson("dynamic-lifecycle.json")
    } else if (key === "engagement") {
      engagement.value = await getJson("dynamic-engagement.json")
    } else if (key === "observations") {
      observations.value = await getJson("dynamic-observations.json")
    }
    normalizeKnownSelection(key)
    if (key === "topics") ensureDefaultTopicDetail()
    if (key === "topics" && contentView.value === "topic-detail" && selectedTag.value) await loadTagDetail(selectedTag.value)
    if (key === "members") ensureDefaultMemberDetail()
    if (key === "members" && selectedMember.value) await loadMemberProfile(selectedMember.value)
    loadedData.add(key)
  } finally {
    tabLoading.value = false
  }
}

watch([fromPeriod, toPeriod, grain, valueMode, topLimit, trendLimit, nodeTrendLimit, memberRankingMetric, memberRankingLimit], async () => {
  if (applyingUrlState || loading.value) return
  if (activeTab.value === "content" && (contentView.value === "topics" || contentView.value === "topic-detail")) {
    await ensureTopicRows()
  }
  await renderActiveTab()
  syncDashboardUrl("replace")
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
  if (activeTab.value === "content" && contentView.value === "topic-detail") {
    await loadTagDetail(selectedTag.value)
  }
  await nextTick()
  if (activeTab.value === "content" && contentView.value === "topic-detail") renderSelectedTopicTrend()
})
watch(selectedMember, async () => {
  if (applyingUrlState || loading.value) return
  if (activeTab.value === "community") await loadMemberProfile(selectedMember.value)
  await nextTick()
  if (activeTab.value === "community") renderMemberProfileTrend()
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
watch([activeTab, contentView, overviewView, communityView, selectedTag, selectedMember], () => syncDashboardUrl("push"), { flush: "post" })
watch(selectedPeriod, () => syncDashboardUrl("replace"), { flush: "post" })
watch(selectedYear, () => syncDashboardUrl("replace"), { flush: "post" })
watch([interactionRanking, topicDetailPostPage, postRankingPage, commentRankingPage], () => syncDashboardUrl("replace"), { flush: "post" })

onMounted(async () => {
  window.addEventListener("popstate", restoreDashboardUrl)
  window.addEventListener("resize", () => {
    if (topicEvolutionChart?.getDom().isConnected) topicEvolutionChart.resize()
    if (topicTrendChart?.getDom().isConnected) topicTrendChart.resize()
    if (groupTrendChart?.getDom().isConnected) groupTrendChart.resize()
    for (const chart of managedCharts.values()) {
      if (chart.getDom().isConnected) chart.resize()
    }
  })
  const [overviewPayload, eventPayload] = await Promise.all([
    getJson("dynamic-overview.json"),
    getJson("dynamic-events.json"),
  ])
  overview.value = overviewPayload
  communityEvents.value = eventPayload.events || []
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
})
</script>

<template>
  <main class="dashboard-shell">
    <DashboardHeader :active-tab="activeTab" :tabs="loading ? [] : tabs" :data-scope="headerDataScope" @select="selectTab" />

    <nav v-if="activeTab === 'overview'" class="subtab-list" aria-label="概览视图">
      <button :class="{ active: overviewView === 'trend' }" @click="overviewView = 'trend'">数据概览</button>
      <button :class="{ active: overviewView === 'month' }" @click="overviewView = 'month'">月度</button>
      <button :class="{ active: overviewView === 'year' }" @click="overviewView = 'year'">年度</button>
    </nav>
    <nav v-if="activeTab === 'content'" class="subtab-list" aria-label="帖子视图">
      <button :class="{ active: contentView === 'topics' }" @click="contentView = 'topics'">话题演变</button>
      <button :class="{ active: contentView === 'topic-detail' }" @click="contentView = 'topic-detail'">话题详情</button>
      <button :class="{ active: contentView === 'nodes' }" @click="contentView = 'nodes'">节点分布</button>
      <button :class="{ active: contentView === 'lifecycle' }" @click="contentView = 'lifecycle'">生命周期</button>
    </nav>
    <nav v-if="activeTab === 'community'" class="subtab-list" aria-label="成员分析视图">
      <button :class="{ active: communityView === 'trends' }" @click="communityView = 'trends'">成员演变</button>
      <button :class="{ active: communityView === 'member-detail' }" @click="communityView = 'member-detail'">成员详情</button>
    </nav>
    <section v-if="!loading && activeTab !== 'observations' && !(activeTab === 'overview' && overviewView !== 'trend')" class="filter-band" aria-label="全局数据筛选">
      <PeriodSelect v-model="fromPeriod" label="开始月份" :periods="fromPeriodOptions" :latest-first="false" />
      <PeriodSelect v-model="toPeriod" label="结束月份" :periods="toPeriodOptions" />
      <div class="control-group">
        <span>时间粒度</span>
        <div class="segmented">
          <button :class="{ active: grain === 'month' }" @click="grain = 'month'">月</button>
          <button :class="{ active: grain === 'year' }" @click="grain = 'year'">年</button>
        </div>
      </div>
      <div v-if="activeTab === 'content' && (contentView === 'topics' || contentView === 'nodes')" class="control-group">
        <span>指标口径</span>
        <div class="segmented">
          <button :class="{ active: valueMode === 'count' }" @click="valueMode = 'count'">数量</button>
          <button :class="{ active: valueMode === 'share' }" @click="valueMode = 'share'">占比</button>
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

    <LoadingState v-if="loading" label="正在加载聚合数据" retry @retry="reloadPage" />
    <LoadingState v-else-if="tabLoading" label="正在加载当前分析视图" />

    <MonthlyDataView
      v-else-if="activeTab === 'overview' && overviewView === 'month'"
      :profile="monthlyData"
      :loading="monthlyDataLoading"
      :periods="monthlyPeriodOptions"
      :selected-period="selectedPeriod"
      @select-period="selectMonthlyPeriod"
      @select-tag="selectPeriodTag"
      @select-member="selectPeriodMember"
    />

    <MonthlyDataView
      v-else-if="activeTab === 'overview' && overviewView === 'year'"
      period-type="year"
      :profile="annualData"
      :loading="annualDataLoading"
      :periods="annualPeriodOptions"
      :selected-period="selectedYear"
      @select-period="selectAnnualPeriod"
      @select-tag="selectPeriodTag"
      @select-member="selectPeriodMember"
    />

    <section v-else-if="activeTab === 'overview'" class="view-section">
      <div class="metric-grid six">
        <article class="metric">
          <span>主题</span><strong>{{ formatNumber(currentSummary.topics) }}</strong>
          <em :class="{ down: change(currentSummary.topics, previousSummary.topics) < 0 }">较上期 {{ formatPercent(change(currentSummary.topics, previousSummary.topics), true) }}</em>
        </article>
        <article class="metric">
          <span>评论</span><strong>{{ formatNumber(currentSummary.comments) }}</strong>
          <em :class="{ down: change(currentSummary.comments, previousSummary.comments) < 0 }">较上期 {{ formatPercent(change(currentSummary.comments, previousSummary.comments), true) }}</em>
        </article>
        <article class="metric">
          <span>新增成员</span><strong>{{ formatNumber(currentSummary.members) }}</strong>
          <em :class="{ down: change(currentSummary.members, previousSummary.members) < 0 }">较上期 {{ formatPercent(change(currentSummary.members, previousSummary.members), true) }}</em>
        </article>
        <article class="metric">
          <span>点击</span><strong>{{ formatNumber(currentSummary.clicks) }}</strong>
          <em>主题累计快照</em>
        </article>
        <article class="metric">
          <span>收藏</span><strong>{{ formatNumber(currentSummary.favorites) }}</strong>
          <em :class="{ down: change(currentSummary.favorites, previousSummary.favorites) < 0 }">较上期 {{ formatPercent(change(currentSummary.favorites, previousSummary.favorites), true) }}</em>
        </article>
        <article class="metric">
          <span>主题感谢</span><strong>{{ formatNumber(currentSummary.thanks) }}</strong>
          <em :class="{ down: change(currentSummary.thanks, previousSummary.thanks) < 0 }">较上期 {{ formatPercent(change(currentSummary.thanks, previousSummary.thanks), true) }}</em>
        </article>
      </div>
      <div class="chart-grid two">
        <article class="analysis-block">
          <header><h2>帖子与评论变化</h2><p>评论使用右轴，观察发帖规模与讨论量是否同步。</p></header>
          <div id="overview-trend" class="chart"></div>
        </article>
        <article class="analysis-block">
          <header><h2>成员与互动变化</h2><p>新增成员使用左轴，收藏与主题感谢使用右轴。</p></header>
          <div id="overview-participation" class="chart"></div>
        </article>
      </div>
      <article class="analysis-block full">
        <header><h2>评论活跃时段</h2><p>筛选周期内，星期与小时的累计评论分布。</p></header>
        <div id="activity-heatmap" class="chart heatmap"></div>
      </article>
    </section>

    <section v-else-if="activeTab === 'content' && (contentView === 'topics' || contentView === 'topic-detail')" class="view-section">
      <div v-if="contentView === 'topics'" class="section-toolbar">
        <div><h2>话题演变</h2><p>默认展示筛选区间内总量最高的标签；点击话题可进入话题详情。</p></div>
      </div>

      <div v-if="contentView === 'topics'" class="metric-grid six">
        <article class="metric">
          <span>主题</span><strong>{{ formatNumber(currentSummary.topics) }}</strong>
          <em :class="{ down: change(currentSummary.topics, previousSummary.topics) < 0 }">较上期 {{ formatPercent(change(currentSummary.topics, previousSummary.topics), true) }}</em>
        </article>
        <article class="metric">
          <span>评论</span><strong>{{ formatNumber(currentSummary.comments) }}</strong>
          <em :class="{ down: change(currentSummary.comments, previousSummary.comments) < 0 }">较上期 {{ formatPercent(change(currentSummary.comments, previousSummary.comments), true) }}</em>
        </article>
        <article class="metric"><span>月均主题</span><strong>{{ formatNumber(postSummary.monthlyTopics) }}</strong><em>筛选周期内</em></article>
        <article class="metric"><span>平均回复</span><strong>{{ formatNumber(currentSummary.commentsPerTopic, 1) }}</strong><em>每个主题</em></article>
        <article class="metric"><span>零回复率</span><strong>{{ formatPercent(currentSummary.zeroReplyRate) }}</strong><em>{{ formatNumber(currentSummary.zeroReplies) }} 个主题</em></article>
        <article class="metric"><span>活跃标签</span><strong>{{ formatNumber(postSummary.activeTags) }}</strong><em>筛选周期内有发帖</em></article>
      </div>

      <article v-if="contentView === 'topics'" class="analysis-block full">
        <header class="block-header-with-control">
        <div><h2>话题演变</h2><p>每列展示该月或该年讨论最多的标签，行表示当期排名；颜色越深，主题数或同期占比越高，拖动底部范围条可浏览历史。</p></div>
          <div class="segmented compact-segmented" aria-label="标签数量">
            <button :class="{ active: topLimit === 10 }" @click="topLimit = 10">Top 10</button>
            <button :class="{ active: topLimit === 20 }" @click="topLimit = 20">Top 20</button>
            <button :class="{ active: topLimit === 30 }" @click="topLimit = 30">Top 30</button>
          </div>
        </header>
        <div id="topic-evolution" class="chart evolution-heatmap" :style="topicEvolutionChartStyle"></div>
        <RankedColumns :columns="topicEvolutionRankingColumns" @select="selectRankedItem" />
      </article>

      <article v-if="contentView === 'topic-detail' && selectedTag" id="topic-detail" class="analysis-block full topic-detail-block">
        <header class="block-header-with-control">
          <div><h2>话题详情：{{ selectedTag }}</h2><p>当前筛选范围展示话题规模、趋势和代表帖子；关联标签、主要节点与活跃用户使用全历史累计结构。</p></div>
          <div class="detail-actions topic-detail-actions">
            <PeriodSelect v-model="selectedTag" class="topic-detail-select" label="选择话题" icon="tag" hide-label :periods="topicDetailTagValues" :option-labels="topicDetailTagLabels" :latest-first="false" />
            <a :href="topicTagUrl(selectedTag)" target="_blank" rel="noreferrer">话题链接</a>
          </div>
        </header>
        <div v-if="tagDetailLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="selectedTagDetail && selectedTagStats">
          <div class="metric-grid four topic-detail-metrics">
            <article class="metric"><span>主题</span><strong>{{ formatNumber(selectedTagStats.count) }}</strong><em>当前筛选范围</em></article>
            <article class="metric"><span>同期份额</span><strong>{{ selectedTagStats.share.toFixed(2) }}%</strong><em>占有效主题</em></article>
            <article class="metric"><span>平均回复</span><strong>{{ formatNumber(selectedTagStats.repliesPerTopic, 1) }}</strong><em>每个主题</em></article>
            <article class="metric"><span>活跃峰值</span><strong>{{ selectedTagStats.peak }}</strong><em>主题量最高的{{ grain === 'month' ? '月份' : '年份' }}</em></article>
          </div>
          <section class="topic-detail-trend">
            <header><h3>{{ selectedTag }} 话题趋势</h3><p>按当前日期范围和{{ grain === 'month' ? '月份' : '年份' }}展示该话题的主题数量变化。</p></header>
            <div id="topic-detail-trend" class="chart compact-chart"></div>
          </section>
          <p class="topic-detail-scope-note">以下关联结构按全历史统计：{{ selectedTag }} 共 {{ formatNumber(selectedTagDetail.total) }} 个主题。节点和用户数量均为包含该标签的主题数；关联标签可在同一主题中同时出现。</p>
          <RankedColumns :columns="topicDetailRankingColumns" @select="selectRankedItem" />
          <section class="topic-detail-posts">
            <header class="content-section-header">
              <div><h3>代表帖子</h3><p>从每月全站综合互动 Top 30 候选中筛选包含该话题的帖子，并按综合得分排序。</p></div>
            </header>
            <div class="post-list topic-representative-list">
              <article v-for="post in displayedTopicDetailPosts" :key="post.id" class="post-row">
                <div class="post-main">
                  <div class="post-meta"><span>{{ formatDateTime(post.create_at) }}</span><span>{{ nodeLabel(post.node) }}</span><span>#{{ post.id }}</span></div>
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
              <div v-if="!topicDetailPosts.length" class="empty-state compact-empty">当前筛选范围内没有该话题的代表帖子。</div>
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
            <p class="method-note representative-note">代表帖子候选已排除“推广”（promotions）节点；该过滤不影响全站主题、节点和互动统计。</p>
          </section>
        </template>
      </article>

      <section v-if="contentView === 'topics'" class="topic-trend-view" aria-label="话题趋势分析">
        <article class="analysis-block full">
          <header class="block-header-with-control">
            <div><h2>话题趋势</h2><p>展示筛选区间内主要标签的连续变化。标签存在交叉，因此使用折线而非堆叠；点击折线可查看话题详情。</p></div>
            <div class="segmented compact-segmented" aria-label="趋势标签数量">
              <button :class="{ active: trendLimit === 10 }" @click="trendLimit = 10">Top 10</button>
              <button :class="{ active: trendLimit === 20 }" @click="trendLimit = 20">Top 20</button>
              <button :class="{ active: trendLimit === 30 }" @click="trendLimit = 30">Top 30</button>
            </div>
          </header>
          <div id="topic-trend" class="chart tall"></div>
        </article>
      </section>

      <article v-if="contentView === 'topics'" class="analysis-block full">
        <header><h2>聚合话题趋势</h2><p>同一主题可属于多个类别，因此类别之间不做堆叠求和。</p></header>
        <div id="group-trend" class="chart"></div>
      </article>
    </section>

    <section v-else-if="activeTab === 'content' && contentView === 'nodes'" class="view-section">
      <div class="section-toolbar">
        <div><h2>节点分布</h2><p>把节点作为内容分区来观察：重点看主阵地、头部集中度和通过样本过滤后的活跃变化。</p></div>
      </div>
      <article class="analysis-block full">
        <header><h2>主要节点结构</h2><p>筛选周期内主题最多的24个节点，柱顶为其主题份额。</p></header>
        <div id="node-structure" class="chart tall"></div>
      </article>
      <article class="analysis-block full">
        <header class="block-header-with-control">
          <div><h2>主要节点趋势</h2><p>展示当前规模最大的节点，观察主阵地随时间的迁移。</p></div>
          <div class="segmented compact-segmented" aria-label="趋势节点数量">
            <button :class="{ active: nodeTrendLimit === 5 }" @click="nodeTrendLimit = 5">Top 5</button>
            <button :class="{ active: nodeTrendLimit === 10 }" @click="nodeTrendLimit = 10">Top 10</button>
            <button :class="{ active: nodeTrendLimit === 20 }" @click="nodeTrendLimit = 20">Top 20</button>
          </div>
        </header>
        <div id="node-trend" class="chart tall"></div>
      </article>
      <div class="node-insights">
        <article class="rank-panel">
          <h3>活跃上升节点</h3>
          <div v-for="(item, index) in nodeInsights.rising" :key="item.node" class="insight-row">
            <span>{{ index + 1 }}</span><a :href="`https://www.v2ex.com/go/${item.node}`" target="_blank" rel="noreferrer">{{ item.label }}</a>
            <strong>+{{ formatNumber(item.delta) }}</strong><em>{{ formatPercent(item.growth || 0, true) }}</em>
          </div>
          <p class="rank-note">仅纳入当前不少于 500 主题、上一周期不少于 200 主题，按净增主题数排序。</p>
        </article>
        <article class="rank-panel">
          <h3>高回复核心节点</h3>
          <div v-for="(item, index) in nodeInsights.coreDiscussed" :key="item.node" class="insight-row">
            <span>{{ index + 1 }}</span><a :href="`https://www.v2ex.com/go/${item.node}`" target="_blank" rel="noreferrer">{{ item.label }}</a>
            <strong>{{ item.intensity.toFixed(1) }} 回复/主题</strong><em>{{ formatNumber(item.count) }} 主题</em>
          </div>
          <p class="rank-note">仅纳入当前不少于 1000 主题的核心节点，降低小节点偶发热帖影响。</p>
        </article>
      </div>
    </section>

    <section v-else-if="activeTab === 'community'" class="view-section">
      <div v-if="communityView === 'trends'" class="section-toolbar">
        <div><h2>成员趋势</h2><p>按月统计新注册成员，以及实际参与发帖和评论的唯一成员数。</p></div>
      </div>
      <div v-if="communityView === 'trends'" class="metric-grid five">
        <article class="metric"><span>新增成员</span><strong>{{ formatNumber(memberSummary.newMembers) }}</strong><em>筛选周期内注册</em></article>
        <article class="metric"><span>月均发帖者</span><strong>{{ formatNumber(memberSummary.averageAuthors) }}</strong><em>唯一用户名</em></article>
        <article class="metric"><span>月均评论者</span><strong>{{ formatNumber(memberSummary.averageCommenters) }}</strong><em>唯一用户名</em></article>
        <article class="metric"><span>发帖者峰值</span><strong>{{ formatNumber(memberSummary.peakAuthors[2]) }}</strong><em>{{ memberSummary.peakAuthors[0] || '-' }}</em></article>
        <article class="metric"><span>评论者峰值</span><strong>{{ formatNumber(memberSummary.peakCommenters[3]) }}</strong><em>{{ memberSummary.peakCommenters[0] || '-' }}</em></article>
      </div>
      <article v-if="communityView === 'trends'" class="analysis-block full member-evolution-block">
        <header class="block-header-with-control">
          <div><h2>成员演变</h2><p>展示每月或每个自然年贡献最高的成员，当前年度仅累计完整月份；拖动底部范围条可浏览历史，悬停可追踪同一成员，点击可查看成员详情。感谢按内容发布时间归期，为当前累计快照。</p></div>
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
      <p v-if="communityView === 'trends'" class="method-note member-ranking-note">三组榜单为全站当前累计快照，不受时间筛选影响；成员演变热力图使用当前筛选范围。账号 usdc 的评论感谢值明显异常，已从感谢榜单和成员演变感谢视图排除，汇总指标仍保留数据库原始值。</p>
      <article v-if="communityView === 'member-detail' && selectedMember" id="member-profile" class="analysis-block full member-profile-block">
        <header class="block-header-with-control">
          <div><h2>成员详情：{{ selectedMember }}</h2><p>仅显示部分活跃成员；基于公开发帖、评论和感谢记录描述社区参与，不推断个人属性、职业或立场。</p></div>
          <div class="detail-actions topic-detail-actions">
            <PeriodSelect v-model="selectedMember" class="member-detail-select" label="选择成员" icon="user" hide-label :periods="memberProfileOptions" :latest-first="false" />
            <a :href="memberUrl(selectedMember)" target="_blank" rel="noreferrer">V2EX 主页</a>
          </div>
        </header>
        <div v-if="memberProfileLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
        <template v-else-if="selectedMemberProfile">
          <div class="metric-grid six member-profile-metrics">
            <article class="metric"><span>发帖</span><strong>{{ formatNumber(memberProfileSummary.topics) }}</strong><em>当前筛选范围</em></article>
            <article class="metric"><span>评论</span><strong>{{ formatNumber(memberProfileSummary.comments) }}</strong><em>当前筛选范围</em></article>
            <article class="metric"><span>收到感谢</span><strong>{{ formatNumber(memberProfileSummary.totalThanks) }}</strong><em>主题 {{ formatNumber(memberProfileSummary.topicThanks) }} / 评论 {{ formatNumber(memberProfileSummary.commentThanks) }}</em></article>
            <article class="metric"><span>活跃月份</span><strong>{{ formatNumber(memberProfileSummary.activePeriods) }}</strong><em>当前筛选范围</em></article>
            <article class="metric"><span>全历史发帖</span><strong>{{ formatNumber(selectedMemberProfile.totals.topics) }}</strong><em>{{ formatNumber(selectedMemberProfile.totals.comments) }} 条评论</em></article>
            <article class="metric"><span>加入时间</span><strong class="metric-date">{{ selectedMemberProfile.registered_at ? formatDateTime(selectedMemberProfile.registered_at).slice(0, 10) : '未知' }}</strong><em>成员公开档案</em></article>
          </div>
          <section class="member-profile-trend">
            <header><h3>发帖与评论变化</h3><p>随全局日期范围和月/年粒度变化，评论使用右轴。</p></header>
            <div id="member-profile-trend" class="chart compact-chart"></div>
          </section>
          <p class="member-profile-scope-note">以下节点、标签、代表帖子和代表评论为全历史累计结构，不受上方日期范围影响。代表评论仅收录至少获得 1 次感谢的内容。</p>
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
        <p v-else class="empty-state compact-empty">该成员暂未纳入有限画像范围，可通过 V2EX 主页查看公开资料。</p>
      </article>
      <article v-if="communityView === 'trends'" class="analysis-block full">
        <header><h2>成员增长与参与</h2><p>新增成员来自档案注册时间，发帖者和评论者来自当月实际内容。</p></header>
        <div id="member-trend" class="chart tall"></div>
      </article>
      <article v-if="communityView === 'trends'" class="analysis-block full">
        <header><h2>参与角色结构</h2><p>评论者与发帖者人数比越高，表示社区参与更偏向回复讨论。</p></header>
        <div id="member-roles" class="chart"></div>
      </article>
    </section>

    <section v-else-if="activeTab === 'content' && contentView === 'lifecycle'" class="view-section">
      <div class="section-toolbar">
        <div><h2>帖子生命周期</h2><p>衡量帖子获得首条回复的速度，以及讨论从发布后数小时延续到数天的过程。完整观察截至 {{ lifecycle.metadata?.long_tail_complete_through }}。</p></div>
      </div>
      <div class="metric-grid five">
        <article class="metric"><span>7日内获得回复</span><strong>{{ formatPercent(lifecycleSummary.responseRate) }}</strong><em>已观察满7天的主题</em></article>
        <article class="metric"><span>1小时内首回</span><strong>{{ formatPercent(lifecycleSummary.within1hRate) }}</strong><em>占符合条件主题</em></article>
        <article class="metric"><span>24小时内首回</span><strong>{{ formatPercent(lifecycleSummary.within24hRate) }}</strong><em>占符合条件主题</em></article>
        <article class="metric"><span>首小时评论</span><strong>{{ formatPercent(lifecycleSummary.firstHourShare) }}</strong><em>占前7日评论</em></article>
        <article class="metric"><span>7天后评论</span><strong>{{ formatPercent(lifecycleSummary.after7dShare) }}</strong><em>占前30日评论</em></article>
      </div>
      <article class="analysis-block full">
        <header><h2>讨论强度</h2><p>以平均回复数衡量讨论深度，并结合零回复率观察帖子获得回应的覆盖面。</p></header>
        <div id="post-response-intensity" class="chart"></div>
      </article>
      <article class="analysis-block full">
        <header><h2>回复速度</h2><p>展示帖子发布后获得首条回复所需时间的分布；只纳入已观察满7天的帖子，灰色部分表示7日内没有已存回复。</p></header>
        <div id="first-reply-trend" class="chart tall"></div>
      </article>
      <p class="method-note">生命周期按帖子发布时间归入月份，仅统计数据库中实际保存的评论。删除、不可见及尚未补齐的评论会使响应率偏低。</p>
    </section>

    <section v-else-if="activeTab === 'engagement'" class="view-section">
      <div class="section-toolbar">
        <div><h2>互动</h2><p>比较不同发布时期内容最终积累的点击、收藏、感谢与投票。</p></div>
      </div>
      <div class="metric-grid five">
        <article class="metric"><span>点击</span><strong>{{ formatNumber(engagementSummary.clicks) }}</strong><em>主题累计快照</em></article>
        <article class="metric"><span>收藏</span><strong>{{ formatNumber(engagementSummary.favorites) }}</strong><em>{{ formatNumber(engagementSummary.favoriteRate, 2) }}/千次点击</em></article>
        <article class="metric"><span>主题感谢</span><strong>{{ formatNumber(engagementSummary.topicThanks) }}</strong><em>{{ formatNumber(engagementSummary.topicThankRate, 2) }}/千次回复</em></article>
        <article class="metric"><span>投票</span><strong>{{ formatNumber(engagementSummary.votes) }}</strong><em>{{ formatNumber(engagementSummary.voteRate, 1) }}/千主题</em></article>
        <article class="metric"><span>评论感谢</span><strong>{{ formatNumber(engagementSummary.commentThanks) }}</strong><em>按评论发布期归入</em></article>
      </div>
      <div class="chart-grid two">
        <article class="analysis-block">
          <header><h2>互动规模变化</h2><p>主题互动按主题发布期归入，评论感谢按评论发布期归入。</p></header>
          <div id="engagement-volume" class="chart"></div>
        </article>
        <article class="analysis-block">
          <header><h2>互动效率变化</h2><p>使用点击、回复和主题数标准化，降低社区规模变化的影响。</p></header>
          <div id="engagement-efficiency" class="chart"></div>
        </article>
      </div>
      <article class="leader-board interaction-ranking">
        <header class="ranking-header">
          <div><h2>热门帖子</h2><p>按当前累计互动指标展示 Top 200，不受上方时间筛选影响。</p></div>
          <div class="control-group interaction-metric-control">
            <span>排序指标</span>
            <div class="segmented compact-segmented" aria-label="热门帖子排序指标">
              <button :class="{ active: interactionRanking === 'favorite_count' }" @click="interactionRanking = 'favorite_count'">收藏</button>
              <button :class="{ active: interactionRanking === 'thank_count' }" @click="interactionRanking = 'thank_count'">感谢</button>
              <button :class="{ active: interactionRanking === 'votes' }" @click="interactionRanking = 'votes'">投票</button>
              <button :class="{ active: interactionRanking === 'clicks' }" @click="interactionRanking = 'clicks'">点击</button>
            </div>
          </div>
        </header>
        <div class="content-list interaction-post-list">
          <a v-for="(post, index) in displayedInteractionPosts" :key="post.id" class="content-list-row" :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">
            <span class="content-list-rank">{{ (postRankingPage - 1) * rankingPageSize + displayIndex(index) }}</span>
            <span class="content-list-main">
              <strong>{{ post.title }}</strong>
              <small>{{ formatDateTime(post.create_at) }} · {{ nodeLabel(post.node) }} · #{{ post.id }}</small>
            </span>
            <em class="content-list-value">{{ formatNumber(post.value) }}</em>
          </a>
        </div>
        <footer class="ranking-pagination">
          <span>Top {{ formatNumber(topInteractionPosts.length) }} · 第 {{ postRankingPage }} / {{ postPageCount }} 页</span>
          <nav aria-label="热门帖子分页">
            <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="postRankingPage <= 1" @click="postRankingPage--">‹</button>
            <template v-for="item in postPaginationItems" :key="item">
              <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === postRankingPage }" :aria-current="item === postRankingPage ? 'page' : undefined" @click="postRankingPage = item">{{ item }}</button>
              <span v-else class="pagination-gap" aria-hidden="true">…</span>
            </template>
            <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="postRankingPage >= postPageCount" @click="postRankingPage++">›</button>
          </nav>
        </footer>
      </article>
      <article class="leader-board interaction-ranking">
        <header><h2>热门评论</h2><p>按累计感谢数展示 Top 500，点击可跳转至原主题评论位置。</p></header>
        <div class="comment-ranking-list">
          <a v-for="(comment, index) in displayedTopComments" :key="comment.id" class="comment-ranking-row" :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`" target="_blank" rel="noreferrer">
            <span class="comment-rank">{{ (commentRankingPage - 1) * rankingPageSize + displayIndex(index) }}</span>
            <span class="comment-ranking-main">
              <strong>{{ comment.content || '评论原文未收录' }}</strong>
              <small>{{ formatDateTime(comment.create_at) }} · {{ comment.commenter }} · {{ comment.topic_title }} · #{{ comment.no }}</small>
            </span>
            <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
          </a>
        </div>
        <footer class="ranking-pagination">
          <span>Top {{ formatNumber(engagement.top_comments.length) }} · 第 {{ commentRankingPage }} / {{ commentPageCount }} 页</span>
          <nav aria-label="热门评论分页">
            <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="commentRankingPage <= 1" @click="commentRankingPage--">‹</button>
            <template v-for="item in commentPaginationItems" :key="item">
              <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === commentRankingPage }" :aria-current="item === commentRankingPage ? 'page' : undefined" @click="commentRankingPage = item">{{ item }}</button>
              <span v-else class="pagination-gap" aria-hidden="true">…</span>
            </template>
            <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="commentRankingPage >= commentPageCount" @click="commentRankingPage++">›</button>
          </nav>
        </footer>
      </article>
      <p class="method-note">账号 usdc 的评论感谢值明显异常，已从“热门评论”榜单排除；全站汇总与趋势仍保留数据库原始值。</p>
      <p class="method-note">V2EX 未提供收藏、感谢和投票的发生时间。这里展示的是按内容发布时间分组的当前累计值，不能解释为对应月份实际发生的互动；原始值为 -1 的未知互动按 0 处理。</p>
    </section>

    <section v-else-if="activeTab === 'observations'" class="view-section observations-view">
      <div class="observation-brief">
        <div class="observation-kicker">离线数据解读 · {{ observations.metadata.analysis_start }} 至 {{ observations.metadata.analysis_end }}</div>
        <h2>{{ observations.headline.title }}</h2>
        <p>{{ observations.headline.summary }}</p>
        <div class="observation-headline-metrics">
          <div v-for="metric in observations.headline.metrics" :key="metric.label">
            <strong>{{ metric.value }}</strong><span>{{ metric.label }}</span>
          </div>
        </div>
      </div>

      <div class="observation-grid">
        <article v-for="(item, index) in observations.observations" :key="item.id" class="observation-item">
          <header>
            <div class="observation-index">{{ String(displayIndex(index)).padStart(2, '0') }}</div>
            <div>
              <div class="observation-meta"><span>{{ item.category }}</span><span>{{ item.evidence }}</span><span>可信度 {{ item.confidence }}</span></div>
              <h3>{{ item.title }}</h3>
            </div>
          </header>
          <p class="observation-summary">{{ item.summary }}</p>
          <p class="observation-interpretation">{{ item.interpretation }}</p>
          <div class="observation-stats">
            <div v-for="stat in item.stats" :key="stat.label"><strong>{{ stat.value }}</strong><span>{{ stat.label }}</span></div>
          </div>
          <footer>
            <div class="observation-links">
              <a v-for="link in item.links" :key="link.href" :href="link.href">{{ link.label }}</a>
              <a v-if="item.source" :href="item.source.url" target="_blank" rel="noreferrer">{{ item.source.action || "查看来源" }}</a>
            </div>
            <span v-if="item.source" class="observation-source">{{ item.source.date }} · {{ item.source.label }}</span>
          </footer>
        </article>
      </div>

      <section class="observation-method">
        <header>
          <div><span>方法与边界</span><h3>解读口径</h3></div>
          <p>离线生成 · 固定窗口 · 可追溯证据</p>
        </header>
        <div class="observation-method-grid">
          <div v-for="(note, index) in observations.notes" :key="note">
            <span>{{ String(displayIndex(index)).padStart(2, "0") }}</span><p>{{ note }}</p>
          </div>
        </div>
        <footer>生成方式：{{ observations.metadata.generated_by }} · 核心窗口 {{ observations.metadata.analysis_start }} 至 {{ observations.metadata.analysis_end }} · 前后五年比较</footer>
      </section>
    </section>

  </main>
  <DashboardFooter :year="footerYear" />
</template>
