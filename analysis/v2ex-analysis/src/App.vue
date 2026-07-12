<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue"
import * as echarts from "echarts/core"
import { BarChart, HeatmapChart, LineChart } from "echarts/charts"
import { GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from "echarts/components"
import { CanvasRenderer } from "echarts/renderers"

echarts.use([BarChart, HeatmapChart, LineChart, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

type TabId = "overview" | "content" | "community" | "engagement"
type ContentView = "topics" | "nodes" | "lifecycle" | "posts"
type Grain = "month" | "year"
type ValueMode = "count" | "share"
type MemberRankingMetric = "topics" | "comments" | "thanks"

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
]

const activeTab = ref<TabId>("overview")
const loading = ref(true)
const tabLoading = ref(false)
const overview = ref<any>({ periods: [], activity: [], metadata: {} })
const topics = ref<any>({ tags: [], rows: [], groups: [], group_rows: [], representative_posts: [] })
const nodes = ref<any>({ rows: [] })
const lifecycle = ref<any>({ first_reply_rows: [], comment_age_rows: [], long_tail_rows: [] })
const community = ref<any>({ rows: [], rank_rows: [], top_topic_authors: [], top_commenters: [], top_thanked: [] })
const engagement = ref<any>({ rows: [], top_posts: {}, top_comments: [] })
const loadedData = new Set<string>(["overview"])
const contentView = ref<ContentView>("topics")
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
const interactionRanking = ref<"favorite_count" | "thank_count" | "votes" | "clicks">("favorite_count")
const interactionPostDisplayLimit = ref(30)
const interactionCommentDisplayLimit = ref(30)
const representativePostPage = ref(1)
const postRankingPage = ref(1)
const commentRankingPage = ref(1)
const rankingPageSize = 10
const quickRanges = [
  { id: "ytd", label: "今年来" },
  { id: "1y", label: "近1年", months: 12 },
  { id: "3y", label: "近3年", months: 36 },
  { id: "5y", label: "近5年", months: 60 },
  { id: "10y", label: "近10年", months: 120 },
  { id: "all", label: "全部" },
] as const

let topicEvolutionChart: echarts.ECharts | null = null
let topicTrendChart: echarts.ECharts | null = null
let groupTrendChart: echarts.ECharts | null = null
const managedCharts = new Map<string, echarts.ECharts>()
const topicEvolutionTagIndices = new Map<string, number[]>()
let hoveredEvolutionTag = ""
const categoricalColors = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
  "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
  "#9c755f", "#6b7280", "#2563eb", "#c2410c",
  "#7c3aed", "#0f766e", "#be123c", "#4d7c0f",
  "#0891b2", "#a16207", "#4338ca", "#15803d",
]
const nodeLabels: Record<string, string> = {
  qna: "问与答", all4all: "二手交易", programmer: "程序员", jobs: "酷工作",
  share: "分享发现", create: "分享创造", career: "职场话题", life: "生活",
  internet: "互联网", ideas: "奇思妙想", invest: "投资", travel: "旅行",
  bb: "宽带症候群", pointless: "无要点", flamewar: "水深火热",
  random: "随想", in: "邀请码", promotions: "推广", fit: "健康",
  ime: "输入法", afterdark: "天黑以后", music: "音乐", movie: "电影",
  tv: "剧集", book: "阅读", games: "游戏", photography: "摄影",
  business: "商业", money: "财富", remote: "远程工作", workplace: "职场",
  beijing: "北京", shanghai: "上海", shenzhen: "深圳", guangzhou: "广州",
  home: "家居", car: "汽车", hardware: "硬件", cloud: "云计算",
  apple: "Apple", macos: "macOS", iphone: "iPhone", mbp: "MacBook Pro",
  appletv: "Apple TV", ipad: "iPad", airpods: "AirPods",
  android: "Android", linux: "Linux", python: "Python", java: "Java",
  javascript: "JavaScript", golang: "Go", ai: "人工智能",
}

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
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

function managedChart(id: string) {
  const element = document.getElementById(id)
  if (!element) return null
  const current = managedCharts.get(id)
  if (current?.getDom() === element) return current
  current?.dispose()
  const chart = echarts.init(element, undefined, { renderer: "canvas" })
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

function renderLineChart(
  id: string,
  periods: string[],
  definitions: LineDefinition[],
  yAxes: Array<{ name: string; max?: number }> = [{ name: "数量" }],
) {
  const chart = managedChart(id)
  if (!chart) return
  chart.setOption({
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
    legend: definitions.length > 1 ? {
      type: "scroll",
      bottom: 4,
      left: 12,
      right: 12,
      itemWidth: 18,
      itemHeight: 3,
      textStyle: { color: "#475467", fontSize: 11 },
    } : { show: false },
    grid: { top: 28, right: yAxes.length > 1 ? 72 : 24, bottom: definitions.length > 1 ? 84 : 48, left: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: periods,
      axisLabel: { color: "#667085", fontSize: 10 },
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
    series: definitions.map((definition) => ({
      name: definition.name,
      type: "line",
      data: definition.data,
      yAxisIndex: definition.yAxisIndex || 0,
      showSymbol: false,
      lineStyle: { color: definition.color, width: 2.2 },
      itemStyle: { color: definition.color },
      areaStyle: definition.areaColor ? { color: definition.areaColor } : undefined,
      emphasis: { focus: "series", lineStyle: { width: 4 } },
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
const selectedRawPeriods = computed<PeriodMetric[]>(() =>
  overview.value.periods.filter((item: PeriodMetric) => inRange(item.period)),
)
const selectedMetrics = computed(() => aggregateMetrics(selectedRawPeriods.value))
const incompletePeriods = computed<string[]>(() => overview.value.metadata.incomplete_periods || [])
const periodNotice = computed(() => {
  if (incompletePeriods.value.some((period) => inRange(period))) {
    return "包含进行中月份，末期仅展示已采集数据"
  }
  const currentYear = overview.value.metadata.end_period?.slice(0, 4)
  if (grain.value === "year" && toPeriod.value.slice(0, 4) === currentYear) {
    return `${currentYear} 为年度累计`
  }
  return ""
})

function quickRangeBounds(preset: (typeof quickRanges)[number]) {
  const periods = periodOptions.value
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
const allTimeSummary = computed(() => summarize(overview.value.periods))

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
const limitedInteractionPosts = computed(() => topInteractionPosts.value.slice(0, interactionPostDisplayLimit.value))
const limitedTopComments = computed(() => engagement.value.top_comments.slice(0, interactionCommentDisplayLimit.value))
const postPageCount = computed(() => Math.max(1, Math.ceil(limitedInteractionPosts.value.length / rankingPageSize)))
const commentPageCount = computed(() => Math.max(1, Math.ceil(limitedTopComments.value.length / rankingPageSize)))
const displayedInteractionPosts = computed(() => limitedInteractionPosts.value.slice(
  (postRankingPage.value - 1) * rankingPageSize,
  postRankingPage.value * rankingPageSize,
))
const displayedTopComments = computed(() => limitedTopComments.value.slice(
  (commentRankingPage.value - 1) * rankingPageSize,
  commentRankingPage.value * rankingPageSize,
))

const memberEvolutionRows = computed(() => community.value.rank_rows.filter((row: any[]) => {
  if (row[0] !== grain.value || row[2] !== memberRankingMetric.value || row[3] > memberRankingLimit.value) return false
  if (grain.value === "month") return inRange(row[1])
  return row[1] >= fromPeriod.value.slice(0, 4) && row[1] <= toPeriod.value.slice(0, 4)
}))
const memberEvolutionPeriods = computed(() => [...new Set<string>(
  memberEvolutionRows.value.map((row: any[]) => row[1] as string),
)].sort())
const memberEvolutionChartStyle = computed(() => ({
  width: `${Math.max(960, memberEvolutionPeriods.value.length * (grain.value === "month" ? 88 : 110))}px`,
  height: `${Math.max(390, memberRankingLimit.value * 24 + 110)}px`,
}))

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
const topicEvolutionChartDimensions = computed(() => {
  const columnWidth = grain.value === "year" ? 96 : 88
  const width = Math.max(960, topicBuckets.value.length * columnWidth + 150)
  const height = Math.max(360, 94 + topLimit.value * 30)
  return { width, height }
})
const topicEvolutionChartStyle = computed(() => {
  const { width, height } = topicEvolutionChartDimensions.value
  return { width: `${width}px`, height: `${height}px` }
})

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
    rising: [...rows].sort((a, b) => b.delta - a.delta).slice(0, 10),
    falling: [...rows].sort((a, b) => a.delta - b.delta).slice(0, 10),
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

const hotTopics = computed(() => selectTopNames(tagValues.value, 10).map(tagStats))

const representativePostsInRange = computed<RepresentativePost[]>(() => {
  return topics.value.representative_posts.filter((post: RepresentativePost) => inRange(post.period))
})
const representativeTagOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const post of representativePostsInRange.value) {
    for (const tag of post.tags) counts.set(tag, (counts.get(tag) || 0) + 1)
  }
  const ranked = [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag, "zh-CN"))
  const options = ranked.slice(0, 500)
  if (selectedTag.value && counts.has(selectedTag.value) && !options.some((item) => item.tag === selectedTag.value)) {
    options.push({ tag: selectedTag.value, count: counts.get(selectedTag.value) || 0 })
  }
  return options
})
const filteredPosts = computed<RepresentativePost[]>(() => {
  return representativePostsInRange.value
    .filter((post: RepresentativePost) => !selectedTag.value || post.tags.includes(selectedTag.value))
    .sort((a: RepresentativePost, b: RepresentativePost) => b.score - a.score)
})
const representativePostPageCount = computed(() => Math.max(1, Math.ceil(filteredPosts.value.length / rankingPageSize)))
const displayedRepresentativePosts = computed(() => filteredPosts.value.slice(
  (representativePostPage.value - 1) * rankingPageSize,
  representativePostPage.value * rankingPageSize,
))

function chooseTag(tag: string, openPosts = false) {
  selectedTag.value = tag
  if (openPosts) {
    activeTab.value = "content"
    contentView.value = "posts"
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
  const dimensions = topicEvolutionChartDimensions.value
  const element = document.getElementById("topic-evolution")
  if (!element) return
  if (!topicEvolutionChart || topicEvolutionChart.getDom() !== element) {
    topicEvolutionChart?.dispose()
    topicEvolutionChart = echarts.init(element, undefined, { renderer: "canvas" })
  }
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
  topicEvolutionChart.resize({ width: dimensions.width, height: dimensions.height })
  topicEvolutionChart.setOption({
    animation: false,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter(params: any) {
        const item = params.data?.value || []
        return `${item[7]} · ${item[3]}<br>主题 ${formatNumber(item[4])}<br>同期占比 ${formatPercent(item[5])}<br>平均回复 ${formatNumber(item[6], 1)}`
      },
    },
    grid: { top: 18, right: 24, bottom: 76, left: 24 },
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
  const scrollToLatest = () => {
    const scroll = element.parentElement
    if (scroll) scroll.scrollLeft = Number.MAX_SAFE_INTEGER
  }
  requestAnimationFrame(() => requestAnimationFrame(scrollToLatest))
  window.setTimeout(scrollToLatest, 120)
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
      chooseTag(tag)
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
    topicTrendChart = echarts.init(element, undefined, { renderer: "canvas" })
  }
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
    legend: {
      type: "scroll",
      bottom: 4,
      left: 12,
      right: 12,
      itemWidth: 18,
      itemHeight: 3,
      textStyle: { color: "#475467", fontSize: 11 },
    },
    grid: { top: 24, right: 24, bottom: 88, left: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: topicBuckets.value,
      axisLabel: { color: "#667085", fontSize: 10 },
      axisLine: { lineStyle: { color: "#d9dee7" } },
      triggerEvent: true,
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
    if (params.seriesName) chooseTag(params.seriesName, true)
  })
}

function renderGroupTrend() {
  const element = document.getElementById("group-trend")
  if (!element) return
  if (!groupTrendChart || groupTrendChart.getDom() !== element) {
    groupTrendChart?.dispose()
    groupTrendChart = echarts.init(element, undefined, { renderer: "canvas" })
  }
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
    legend: {
      type: "scroll",
      bottom: 4,
      left: 12,
      right: 12,
      itemWidth: 18,
      itemHeight: 3,
      textStyle: { color: "#475467", fontSize: 11 },
    },
    grid: { top: 24, right: 24, bottom: 88, left: 72 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: buckets,
      axisLabel: { color: "#667085", fontSize: 10 },
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
  const dimensions = memberEvolutionChartStyle.value
  chart.resize({ width: Number.parseInt(dimensions.width), height: Number.parseInt(dimensions.height) })
  chart.setOption({
    animation: false,
    tooltip: {
      trigger: "item",
      confine: true,
      formatter(params: any) {
        const item = params.data?.value || []
        return `${escapeHtml(item[4])} · 第 ${item[5]} 名<br><strong>${escapeHtml(item[3])}</strong><br>${metricLabels[memberRankingMetric.value]} ${formatNumber(item[2])}`
      },
    },
    grid: { top: 18, right: 24, bottom: 68, left: 24 },
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
    if (username) window.open(`https://www.v2ex.com/member/${encodeURIComponent(username)}`, "_blank", "noopener,noreferrer")
  })
  const scrollToLatest = () => {
    const scroll = chart.getDom().parentElement
    if (scroll) scroll.scrollLeft = Number.MAX_SAFE_INTEGER
  }
  requestAnimationFrame(() => requestAnimationFrame(scrollToLatest))
  window.setTimeout(scrollToLatest, 120)
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
    animation: false,
    tooltip: { trigger: "axis", confine: true, valueFormatter: (value: any) => `${Number(value).toFixed(1)}%` },
    legend: { type: "scroll", bottom: 4, left: 12, right: 12, itemWidth: 16, itemHeight: 8, textStyle: { color: "#475467", fontSize: 11 } },
    grid: { top: 24, right: 24, bottom: 88, left: 72 },
    xAxis: { type: "category", data: periods, axisLabel: { color: "#667085", fontSize: 10 }, axisLine: { lineStyle: { color: "#d9dee7" } } },
    yAxis: { type: "value", name: "主题占比 (%)", min: 0, max: 100, axisLabel: { color: "#667085", fontSize: 10 }, splitLine: { lineStyle: { color: "#edf0f3" } } },
    series,
  } as any, true)
}

async function renderActiveTab() {
  await nextTick()
  if (loading.value) return
  if (activeTab.value === "overview") {
    renderOverviewTrend()
    renderOverviewParticipation()
    renderHeatmap()
  }
  if (activeTab.value === "content" && contentView.value === "topics") {
    renderTopicEvolution()
    renderTopicTrend()
    renderGroupTrend()
  }
  if (activeTab.value === "content" && contentView.value === "nodes") {
    renderNodeStructure()
    renderNodeTrend()
  }
  if (activeTab.value === "community") {
    renderMemberEvolution()
    renderMemberTrend()
    renderMemberRoles()
  }
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

async function loadActiveData() {
  let key: string = activeTab.value
  if (activeTab.value === "content") {
    if (contentView.value === "lifecycle") key = "lifecycle"
    else if (contentView.value === "nodes") key = "nodes"
    else if (contentView.value === "posts") key = "posts"
    else key = "topics"
  }
  if (activeTab.value === "community") key = "members"
  if (loadedData.has(key)) return
  tabLoading.value = true
  try {
    if (key === "topics") {
      if (!loadedData.has("topics-base")) {
        topics.value = { ...topics.value, ...(await getJson("dynamic-topics.json")) }
        loadedData.add("topics-base")
      }
    } else if (key === "posts") {
      if (!loadedData.has("topics-base")) {
        topics.value = { ...topics.value, ...(await getJson("dynamic-topics.json")) }
        loadedData.add("topics-base")
      }
      const postData = await getJson("dynamic-representative-posts.json")
      topics.value = { ...topics.value, ...postData }
    } else if (key === "nodes") {
      nodes.value = await getJson("dynamic-nodes.json")
    } else if (key === "members") {
      community.value = await getJson("dynamic-community.json")
    } else if (key === "lifecycle") {
      lifecycle.value = await getJson("dynamic-lifecycle.json")
    } else if (key === "engagement") {
      engagement.value = await getJson("dynamic-engagement.json")
    }
    loadedData.add(key)
  } finally {
    tabLoading.value = false
  }
}

watch([fromPeriod, toPeriod, grain, valueMode, topLimit, trendLimit, nodeTrendLimit, memberRankingMetric, memberRankingLimit], renderActiveTab)
watch([fromPeriod, toPeriod], () => {
  representativePostPage.value = 1
})
watch([interactionPostDisplayLimit, interactionRanking], () => {
  postRankingPage.value = 1
})
watch(interactionCommentDisplayLimit, () => {
  commentRankingPage.value = 1
})
watch(representativeTagOptions, (options) => {
  if (
    activeTab.value === "content"
    && contentView.value === "posts"
    && selectedTag.value
    && !options.some((item) => item.tag === selectedTag.value)
  ) selectedTag.value = ""
})
watch(selectedTag, async () => {
  representativePostPage.value = 1
  await nextTick()
  if (activeTab.value === "content" && contentView.value === "topics") {
    renderTopicTrend()
  }
})
watch([activeTab, contentView], async () => {
  await loadActiveData()
  renderActiveTab()
})

onMounted(async () => {
  window.addEventListener("resize", () => {
    if (topicTrendChart?.getDom().isConnected) topicTrendChart.resize()
    if (groupTrendChart?.getDom().isConnected) groupTrendChart.resize()
    for (const chart of managedCharts.values()) {
      if (chart.getDom().isConnected) chart.resize()
    }
  })
  overview.value = await getJson("dynamic-overview.json")
  const defaultRange = quickRanges.find((preset) => preset.id === "5y")
  if (defaultRange) applyQuickRange(defaultRange)
  loading.value = false
  await loadActiveData()
  renderActiveTab()
})
</script>

<template>
  <main class="dashboard-shell">
    <header class="dashboard-header">
      <div class="dashboard-header-inner">
        <div class="dashboard-brand">
          <a class="brand-link" href="./" aria-label="刷新 V2EX 社区看板首页"><h1>V2EX 社区看板</h1></a>
          <p class="data-scope" v-if="overview.metadata.start_period">
            数据分析范围 {{ overview.metadata.start_period }} 至 {{ overview.metadata.end_period }} ·
            {{ formatNumber(allTimeSummary.topics) }} 个有效主题 ·
            {{ formatNumber(allTimeSummary.comments) }} 条评论 ·
            {{ formatNumber(allTimeSummary.members) }} 位成员
          </p>
        </div>
        <nav v-if="!loading" class="tab-list" aria-label="分析视图">
          <button v-for="tab in tabs" :key="tab.id" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">
            {{ tab.label }}
          </button>
        </nav>
      </div>
    </header>

    <nav v-if="activeTab === 'content'" class="subtab-list" aria-label="帖子分析视图">
      <button :class="{ active: contentView === 'topics' }" @click="contentView = 'topics'">话题演变</button>
      <button :class="{ active: contentView === 'nodes' }" @click="contentView = 'nodes'">节点分布</button>
      <button :class="{ active: contentView === 'lifecycle' }" @click="contentView = 'lifecycle'">生命周期</button>
      <button :class="{ active: contentView === 'posts' }" @click="contentView = 'posts'">代表帖子</button>
    </nav>
    <section v-if="!loading" class="filter-band" aria-label="全局数据筛选">
      <label>
        <span>开始月份</span>
        <select v-model="fromPeriod">
          <option v-for="period in periodOptions" :key="period" :value="period">{{ period }}{{ incompletePeriods.includes(period) ? "（进行中）" : "" }}</option>
        </select>
      </label>
      <label>
        <span>结束月份</span>
        <select v-model="toPeriod">
          <option v-for="period in periodOptions" :key="period" :value="period">{{ period }}{{ incompletePeriods.includes(period) ? "（进行中）" : "" }}</option>
        </select>
      </label>
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
      <div class="partial-note" v-if="periodNotice">{{ periodNotice }}</div>
    </section>

    <div v-if="loading" class="loading">
      <div class="loading-card">
        <span class="loading-spinner" aria-hidden="true"></span>
        <strong>正在加载聚合数据</strong>
        <button class="command" type="button" @click="reloadPage">刷新</button>
      </div>
    </div>
    <div v-else-if="tabLoading" class="loading">
      <div class="loading-card">
        <span class="loading-spinner" aria-hidden="true"></span>
        <strong>正在加载当前分析视图</strong>
      </div>
    </div>

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

    <section v-else-if="activeTab === 'content' && contentView === 'topics'" class="view-section">
      <div class="section-toolbar">
        <div><h2>话题演变</h2><p>默认展示筛选区间内总量最高的标签；点击升温、降温或热力图标签后可固定高亮。</p></div>
        <div class="toolbar-controls">
          <button v-if="selectedTag" class="subtle-command" @click="contentView = 'posts'">查看高亮帖子</button>
          <button v-if="selectedTag" class="subtle-command" @click="selectedTag = ''">取消高亮</button>
        </div>
      </div>

      <div class="metric-grid six">
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

      <article class="analysis-block full">
        <header class="block-header-with-control">
          <div><h2>话题演变</h2><p>每列展示该月或该年讨论最多的标签，行表示当期排名；颜色越深，主题数或同期占比越高。</p></div>
          <div class="segmented compact-segmented" aria-label="标签数量">
            <button :class="{ active: topLimit === 10 }" @click="topLimit = 10">Top 10</button>
            <button :class="{ active: topLimit === 20 }" @click="topLimit = 20">Top 20</button>
            <button :class="{ active: topLimit === 30 }" @click="topLimit = 30">Top 30</button>
          </div>
        </header>
        <div class="chart-scroll" aria-label="话题演变横向滚动区域">
          <div id="topic-evolution" class="chart heatmap-wide" :style="topicEvolutionChartStyle"></div>
        </div>
        <div class="topic-evolution-analysis">
          <section class="evolution-rank">
            <h3>热点话题</h3>
            <button v-for="(item, index) in hotTopics" :key="item.tag" class="topic-rank-row" @click="chooseTag(item.tag, true)">
              <span class="topic-rank-index">{{ index + 1 }}</span><span class="topic-rank-name">{{ item.tag }}</span><strong>{{ formatNumber(item.count) }}</strong><em>{{ item.share.toFixed(2) }}%</em>
            </button>
          </section>
          <section class="evolution-rank">
            <h3>近12个月升温</h3>
            <button v-for="(item, index) in momentum.rising" :key="item.tag" class="topic-rank-row" @click="chooseTag(item.tag, true)">
              <span class="topic-rank-index">{{ index + 1 }}</span><span class="topic-rank-name">{{ item.tag }}</span><strong>+{{ item.delta.toFixed(2) }}pp</strong><em>{{ formatNumber(item.count) }}</em>
            </button>
          </section>
          <section class="evolution-rank">
            <h3>近12个月降温</h3>
            <button v-for="(item, index) in momentum.falling" :key="item.tag" class="topic-rank-row" @click="chooseTag(item.tag, true)">
              <span class="topic-rank-index">{{ index + 1 }}</span><span class="topic-rank-name">{{ item.tag }}</span><strong class="down">{{ item.delta.toFixed(2) }}pp</strong><em>{{ formatNumber(item.count) }}</em>
            </button>
          </section>
        </div>
      </article>

      <section class="topic-trend-view" aria-label="话题趋势分析">
        <article class="analysis-block full">
          <header class="block-header-with-control">
            <div><h2>话题趋势</h2><p>展示筛选区间内主要标签的连续变化。标签存在交叉，因此使用折线而非堆叠；点击折线可查看代表帖子。</p></div>
            <div class="segmented compact-segmented" aria-label="趋势标签数量">
              <button :class="{ active: trendLimit === 5 }" @click="trendLimit = 5">Top 5</button>
              <button :class="{ active: trendLimit === 10 }" @click="trendLimit = 10">Top 10</button>
              <button :class="{ active: trendLimit === 20 }" @click="trendLimit = 20">Top 20</button>
            </div>
          </header>
          <div id="topic-trend" class="chart tall"></div>
        </article>
      </section>

      <article class="analysis-block full">
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
      <div class="section-toolbar">
        <div><h2>成员趋势</h2><p>按月统计新注册成员，以及实际参与发帖和评论的唯一成员数。</p></div>
      </div>
      <div class="metric-grid five">
        <article class="metric"><span>新增成员</span><strong>{{ formatNumber(memberSummary.newMembers) }}</strong><em>筛选周期内注册</em></article>
        <article class="metric"><span>月均发帖者</span><strong>{{ formatNumber(memberSummary.averageAuthors) }}</strong><em>唯一用户名</em></article>
        <article class="metric"><span>月均评论者</span><strong>{{ formatNumber(memberSummary.averageCommenters) }}</strong><em>唯一用户名</em></article>
        <article class="metric"><span>发帖者峰值</span><strong>{{ formatNumber(memberSummary.peakAuthors[2]) }}</strong><em>{{ memberSummary.peakAuthors[0] || '-' }}</em></article>
        <article class="metric"><span>评论者峰值</span><strong>{{ formatNumber(memberSummary.peakCommenters[3]) }}</strong><em>{{ memberSummary.peakCommenters[0] || '-' }}</em></article>
      </div>
      <article class="analysis-block full member-evolution-block">
        <header class="block-header-with-control">
          <div><h2>成员演变</h2><p>展示每月或每个自然年贡献最高的成员，当前年度仅累计完整月份；悬停可追踪同一成员，点击可打开成员主页。感谢按内容发布时间归期，为当前累计快照。</p></div>
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
        <div class="chart-scroll" aria-label="成员演变横向滚动区域">
          <div id="member-evolution" class="chart heatmap-wide" :style="memberEvolutionChartStyle"></div>
        </div>
      </article>
      <div class="member-leader-grid">
        <article class="leader-board">
          <header><h2>发送帖子最多</h2><p>按有效主题作者统计。</p></header>
          <div class="ranking-list compact-ranking">
            <a v-for="(member, index) in community.top_topic_authors.slice(0, 10)" :key="member.username" :href="`https://www.v2ex.com/member/${member.username}`" target="_blank" rel="noreferrer">
              <span>{{ index + 1 }}</span><strong>{{ member.username }}</strong><em>{{ formatNumber(member.topic_count) }}</em>
            </a>
          </div>
        </article>
        <article class="leader-board">
          <header><h2>发送评论最多</h2><p>按已存评论作者统计。</p></header>
          <div class="ranking-list compact-ranking">
            <a v-for="(member, index) in community.top_commenters.slice(0, 10)" :key="member.username" :href="`https://www.v2ex.com/member/${member.username}`" target="_blank" rel="noreferrer">
              <span>{{ index + 1 }}</span><strong>{{ member.username }}</strong><em>{{ formatNumber(member.comment_count) }}</em>
            </a>
          </div>
        </article>
        <article class="leader-board">
          <header><h2>收到感谢最多</h2><p>主题感谢与评论感谢之和。</p></header>
          <div class="ranking-list compact-ranking">
            <a v-for="(member, index) in community.top_thanked.slice(0, 10)" :key="member.username" class="thank-ranking-row" :href="`https://www.v2ex.com/member/${member.username}`" target="_blank" rel="noreferrer">
              <span>{{ index + 1 }}</span><strong>{{ member.username }}</strong>
              <em>{{ formatNumber(member.total_thanks) }} <small>（主题 {{ formatNumber(member.topic_thanks) }} / 评论 {{ formatNumber(member.comment_thanks) }}）</small></em>
            </a>
          </div>
        </article>
      </div>
      <p class="method-note member-ranking-note">三组成员榜单为全站当前累计快照，不受时间筛选影响；成员演变和下方趋势使用当前筛选范围。账号 usdc 的评论感谢值明显异常，已从“收到感谢最多”榜单和成员演变感谢视图排除，汇总指标仍保留数据库原始值。</p>
      <article class="analysis-block full">
        <header><h2>成员增长与参与</h2><p>新增成员来自档案注册时间，发帖者和评论者来自当月实际内容。</p></header>
        <div id="member-trend" class="chart tall"></div>
      </article>
      <article class="analysis-block full">
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

    <section v-else-if="activeTab === 'content' && contentView === 'posts'" class="view-section">
      <div class="section-toolbar">
        <div><h2>代表帖子</h2><p>每月按回复、收藏、感谢和点击综合选取，避免榜单被单一高点击帖子支配。</p></div>
        <label class="inline-select"><span>标签</span><select v-model="selectedTag"><option value="">全部</option><option v-for="item in representativeTagOptions" :key="item.tag" :value="item.tag">{{ item.tag }}</option></select></label>
      </div>
      <div class="post-list">
        <article v-for="post in displayedRepresentativePosts" :key="post.id" class="post-row">
          <div class="post-main">
            <div class="post-meta"><span>{{ formatDateTime(post.create_at) }}</span><span>{{ nodeLabel(post.node) }}</span><span>#{{ post.id }}</span></div>
            <a :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">{{ post.title }}</a>
            <div class="post-tags"><button v-for="tag in post.tags.slice(0, 6)" :key="tag" @click="chooseTag(tag)">{{ tag }}</button></div>
          </div>
          <dl>
            <div><dt>点击</dt><dd>{{ formatNumber(post.clicks) }}</dd></div>
            <div><dt>回复</dt><dd>{{ formatNumber(post.reply_count) }}</dd></div>
            <div><dt>收藏</dt><dd>{{ formatNumber(post.favorite_count) }}</dd></div>
            <div><dt>感谢</dt><dd>{{ formatNumber(post.thank_count) }}</dd></div>
          </dl>
        </article>
        <div v-if="!filteredPosts.length" class="empty-state">当前筛选范围内没有该标签的代表帖子。</div>
        <footer v-else class="ranking-pagination post-pagination">
          <span>共 {{ formatNumber(filteredPosts.length) }} 帖 · 第 {{ representativePostPage }} / {{ representativePostPageCount }} 页</span>
          <div><button aria-label="上一页" title="上一页" :disabled="representativePostPage <= 1" @click="representativePostPage--">‹</button><button aria-label="下一页" title="下一页" :disabled="representativePostPage >= representativePostPageCount" @click="representativePostPage++">›</button></div>
        </footer>
      </div>
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
          <div><h2>热门帖</h2><p>按当前累计互动指标排序，不受上方时间筛选影响。</p></div>
          <div class="ranking-controls">
            <label class="inline-select"><span>排序指标</span><select v-model="interactionRanking"><option value="favorite_count">收藏</option><option value="thank_count">感谢</option><option value="votes">投票</option><option value="clicks">点击</option></select></label>
            <label class="inline-select compact-select"><span>榜单范围</span><select v-model.number="interactionPostDisplayLimit"><option :value="10">Top 10</option><option :value="30">Top 30</option><option :value="50">Top 50</option><option :value="100">Top 100</option></select></label>
          </div>
        </header>
        <div class="ranking-list interaction-post-list">
          <a v-for="(post, index) in displayedInteractionPosts" :key="post.id" :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">
            <span>{{ (postRankingPage - 1) * rankingPageSize + index + 1 }}</span>
            <span class="ranking-main">
              <strong>{{ post.title }}</strong>
              <small>{{ formatDateTime(post.create_at) }} · {{ nodeLabel(post.node) }} · #{{ post.id }}</small>
            </span>
            <em>{{ formatNumber(post.value) }}</em>
          </a>
        </div>
        <footer class="ranking-pagination">
          <span>第 {{ postRankingPage }} / {{ postPageCount }} 页</span>
          <div><button aria-label="上一页" title="上一页" :disabled="postRankingPage <= 1" @click="postRankingPage--">‹</button><button aria-label="下一页" title="下一页" :disabled="postRankingPage >= postPageCount" @click="postRankingPage++">›</button></div>
        </footer>
      </article>
      <article class="leader-board interaction-ranking">
        <header class="ranking-header">
          <div><h2>热门评论</h2><p>按累计感谢数排序，点击可跳转至原主题评论位置。</p></div>
          <label class="inline-select compact-select"><span>榜单范围</span><select v-model.number="interactionCommentDisplayLimit"><option :value="10">Top 10</option><option :value="30">Top 30</option><option :value="50">Top 50</option><option :value="100">Top 100</option></select></label>
        </header>
        <div class="comment-ranking-list">
          <a v-for="(comment, index) in displayedTopComments" :key="comment.id" class="comment-ranking-row" :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`" target="_blank" rel="noreferrer">
            <span class="comment-rank">{{ (commentRankingPage - 1) * rankingPageSize + index + 1 }}</span>
            <span class="comment-ranking-main">
              <strong>{{ comment.content || '评论原文未收录' }}</strong>
              <small>{{ formatDateTime(comment.create_at) }} · {{ comment.commenter }} · {{ comment.topic_title }} · #{{ comment.no }}</small>
            </span>
            <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
          </a>
        </div>
        <footer class="ranking-pagination">
          <span>第 {{ commentRankingPage }} / {{ commentPageCount }} 页</span>
          <div><button aria-label="上一页" title="上一页" :disabled="commentRankingPage <= 1" @click="commentRankingPage--">‹</button><button aria-label="下一页" title="下一页" :disabled="commentRankingPage >= commentPageCount" @click="commentRankingPage++">›</button></div>
        </footer>
      </article>
      <p class="method-note">账号 usdc 的评论感谢值明显异常，已从“热门评论”榜单排除；全站汇总与趋势仍保留数据库原始值。</p>
      <p class="method-note">V2EX 未提供收藏、感谢和投票的发生时间。这里展示的是按内容发布时间分组的当前累计值，不能解释为对应月份实际发生的互动；原始值为 -1 的未知互动按 0 处理。</p>
    </section>

  </main>
  <footer class="dashboard-footer">
    <div class="dashboard-footer-inner">
      <a href="https://github.com/taifuer/v2ex_scrapy" target="_blank" rel="noreferrer">© V2EX Dashboard</a>
      <span aria-hidden="true">·</span>
      <span>数据来源 <a href="https://v2ex.com/" target="_blank" rel="noreferrer">V2EX</a></span>
      <span aria-hidden="true">·</span>
      <span>仅供学习交流，如有侵权请联系删除</span>
    </div>
  </footer>
</template>
