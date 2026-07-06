<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue"
// @ts-ignore
import Plotly from "plotly.js-dist-min"

type TabId = "overview" | "content" | "nodes" | "community" | "engagement"
type ContentView = "topics" | "lifecycle" | "posts"
type Grain = "month" | "year"
type ValueMode = "count" | "share"

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
  { id: "overview", label: "数据概览" },
  { id: "content", label: "帖子分析" },
  { id: "nodes", label: "节点生态" },
  { id: "community", label: "社区成员" },
  { id: "engagement", label: "互动反馈" },
]

const activeTab = ref<TabId>("overview")
const loading = ref(true)
const tabLoading = ref(false)
const overview = ref<any>({ periods: [], activity: [], metadata: {} })
const topics = ref<any>({ tags: [], rows: [], groups: [], group_rows: [], representative_posts: [] })
const nodes = ref<any>({ rows: [] })
const lifecycle = ref<any>({ first_reply_rows: [], comment_age_rows: [], long_tail_rows: [] })
const community = ref<any>({ rows: [], top_topic_authors: [], top_commenters: [], top_thanked: [] })
const engagement = ref<any>({ rows: [], top_posts: {}, top_comments: [] })
const loadedData = new Set<string>(["overview"])
const contentView = ref<ContentView>("topics")
const fromPeriod = ref("")
const toPeriod = ref("")
const grain = ref<Grain>("month")
const valueMode = ref<ValueMode>("count")
const topLimit = ref(12)
const selectedTag = ref("AI")
const interactionRanking = ref<"favorite_count" | "thank_count" | "votes" | "clicks">("favorite_count")
const quickRanges = [
  { id: "ytd", label: "今年来" },
  { id: "1y", label: "近1年", months: 12 },
  { id: "3y", label: "近3年", months: 36 },
  { id: "5y", label: "近5年", months: 60 },
  { id: "10y", label: "近10年", months: 120 },
] as const

const chartConfig = { responsive: true, displaylogo: false }
const categoricalColors = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
  "#59a14f", "#edc948", "#b07aa1", "#ff9da7",
  "#9c755f", "#6b7280", "#2563eb", "#c2410c",
  "#7c3aed", "#0f766e", "#be123c", "#4d7c0f",
]
const nodeLabels: Record<string, string> = {
  qna: "问与答", all4all: "二手交易", programmer: "程序员", jobs: "酷工作",
  share: "分享发现", create: "分享创造", career: "职场话题", life: "生活",
  internet: "互联网", ideas: "奇思妙想", invest: "投资", travel: "旅行",
  bb: "宽带症候群", pointless: "无要点", flamewar: "水深火热",
  home: "家居", car: "汽车", hardware: "硬件", cloud: "云计算",
  apple: "Apple", macos: "macOS", iphone: "iPhone", mbp: "MacBook Pro",
  android: "Android", linux: "Linux", python: "Python", java: "Java",
  javascript: "JavaScript", golang: "Go", ai: "人工智能",
}
const chartLayout = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor: "#ffffff",
  font: { family: "Inter, system-ui, sans-serif", color: "#263244", size: 12 },
  margin: { t: 28, r: 28, b: 56, l: 64 },
  hovermode: "x unified",
  legend: { orientation: "h", y: -0.2 },
}

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}

function formatPercent(value: number | undefined, signed = false) {
  const number = Number(value || 0)
  return `${signed && number > 0 ? "+" : ""}${number.toFixed(1)}%`
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
  if (preset.id === "ytd") {
    const januaryIndex = periods.indexOf(`${end.slice(0, 4)}-01`)
    startIndex = januaryIndex >= 0 ? januaryIndex : 0
  } else {
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
      result.favorites += row.favorite_sum
      return result
    },
    { topics: 0, comments: 0, members: 0, replies: 0, zeroReplies: 0, favorites: 0 },
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
const selectedTags = computed(() => {
  const tags = selectTopNames(tagValues.value, topLimit.value)
  if (!selectedTag.value || tags.includes(selectedTag.value)) return tags
  return [selectedTag.value, ...tags.slice(0, Math.max(0, topLimit.value - 1))]
})
const topicBuckets = computed(() => [...tagValues.value.keys()].sort())

const topicLeaders = computed(() => {
  return topicBuckets.value.slice(-12).map((bucket) => ({
    bucket,
    tags: [...(tagValues.value.get(bucket) || new Map()).entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 10)
      .map(([tag, value]) => ({ tag, count: value.count })),
  }))
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

const selectedTagStats = computed(() => {
  const rows = topics.value.rows.filter((row: any[]) => row[1] === selectedTag.value && inRange(row[0]))
  const count = rows.reduce((sum: number, row: any[]) => sum + row[2], 0)
  const replies = rows.reduce((sum: number, row: any[]) => sum + row[3], 0)
  const peak = [...rows].sort((a, b) => b[2] - a[2])[0]
  return {
    count,
    share: currentSummary.value.topics ? (count / currentSummary.value.topics) * 100 : 0,
    repliesPerTopic: count ? replies / count : 0,
    peak: peak?.[0] || "-",
  }
})

const filteredPosts = computed<RepresentativePost[]>(() => {
  return topics.value.representative_posts
    .filter((post: RepresentativePost) => inRange(post.period) && (!selectedTag.value || post.tags.includes(selectedTag.value)))
    .sort((a: RepresentativePost, b: RepresentativePost) => b.score - a.score)
    .slice(0, 80)
})

function chooseTag(tag: string, openPosts = false) {
  selectedTag.value = tag
  if (openPosts) {
    activeTab.value = "content"
    contentView.value = "posts"
  }
}

function renderOverviewTrend() {
  Plotly.react("overview-trend", [
    {
      x: selectedMetrics.value.map((item) => item.period),
      y: selectedMetrics.value.map((item) => item.topic_count),
      name: "主题",
      type: "scatter",
      mode: "lines",
      line: { color: "#2563eb", width: 2.5 },
    },
    {
      x: selectedMetrics.value.map((item) => item.period),
      y: selectedMetrics.value.map((item) => item.comment_count),
      name: "评论",
      type: "scatter",
      mode: "lines",
      yaxis: "y2",
      line: { color: "#d94841", width: 2.5 },
    },
  ], {
    ...chartLayout,
    yaxis: { title: "主题数", rangemode: "tozero" },
    yaxis2: { title: "评论数", overlaying: "y", side: "right", rangemode: "tozero" },
  }, chartConfig)
}

function renderIntensity() {
  Plotly.react("discussion-intensity", [
    {
      x: selectedMetrics.value.map((item) => item.period),
      y: selectedMetrics.value.map((item) => item.topic_count ? item.comment_count / item.topic_count : 0),
      name: "评论/主题",
      type: "scatter",
      mode: "lines",
      line: { color: "#0f766e", width: 2.5 },
    },
    {
      x: selectedMetrics.value.map((item) => item.period),
      y: selectedMetrics.value.map((item) => item.topic_count ? item.zero_reply_count / item.topic_count * 100 : 0),
      name: "零回复率",
      type: "scatter",
      mode: "lines",
      yaxis: "y2",
      line: { color: "#b45309", width: 2 },
    },
  ], {
    ...chartLayout,
    yaxis: { title: "评论/主题", rangemode: "tozero" },
    yaxis2: { title: "零回复率 (%)", overlaying: "y", side: "right", rangemode: "tozero" },
  }, chartConfig)
}

function renderHeatmap() {
  const metric = new Map<string, number>()
  for (const row of overview.value.activity) {
    if (!inRange(row[0])) continue
    const key = `${row[1]}-${row[2]}`
    metric.set(key, (metric.get(key) || 0) + row[4])
  }
  const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
  const z = days.map((_, weekday) => Array.from({ length: 24 }, (_, hour) => metric.get(`${weekday}-${hour}`) || 0))
  Plotly.react("activity-heatmap", [{
    x: Array.from({ length: 24 }, (_, hour) => `${hour}:00`),
    y: days,
    z,
    type: "heatmap",
    colorscale: [[0, "#f7f8fa"], [0.35, "#b9d8d0"], [0.7, "#2f8f83"], [1, "#0b4f4a"]],
    hovertemplate: "%{y} %{x}<br>评论 %{z:,}<extra></extra>",
  }], { ...chartLayout, margin: { t: 20, r: 24, b: 44, l: 52 } }, chartConfig)
}

function renderTopicTrend() {
  const totals = periodsByBucket()
  const orderedTags = [...selectedTags.value].sort((a, b) => {
    if (a === selectedTag.value) return 1
    if (b === selectedTag.value) return -1
    return 0
  })
  const traces = orderedTags.map((tag, index) => ({
    x: topicBuckets.value,
    y: topicBuckets.value.map((bucket) => {
      const count = tagValues.value.get(bucket)?.get(tag)?.count || 0
      return valueMode.value === "share" ? (count / Math.max(1, totals.get(bucket) || 0)) * 100 : count
    }),
    name: tag === selectedTag.value ? `${tag}（当前）` : tag,
    type: "scatter",
    mode: "lines",
    line: { color: tag === selectedTag.value ? "#111827" : categoricalColors[index], width: tag === selectedTag.value ? 4 : 1.6 },
    opacity: tag === selectedTag.value ? 1 : 0.55,
  }))
  Plotly.react("topic-trend", traces, {
    ...chartLayout,
    yaxis: { title: valueMode.value === "share" ? "占同期主题 (%)" : "涉及该标签的主题数", rangemode: "tozero" },
  }, chartConfig)
}

function renderGroupTrend() {
  const values = aggregateSeriesRows(topics.value.group_rows, 1, 2, 3)
  const totals = periodsByBucket()
  const buckets = [...values.keys()].sort()
  const traces = topics.value.groups.map((group: any, index: number) => ({
    x: buckets,
    y: buckets.map((bucket) => {
      const count = values.get(bucket)?.get(group.name)?.count || 0
      return valueMode.value === "share" ? (count / Math.max(1, totals.get(bucket) || 0)) * 100 : count
    }),
    name: group.label,
    type: "scatter",
    mode: "lines",
    line: { color: categoricalColors[index], width: 2 },
  }))
  Plotly.react("group-trend", traces, {
    ...chartLayout,
    yaxis: { title: valueMode.value === "share" ? "占同期主题 (%)" : "主题数", rangemode: "tozero" },
  }, chartConfig)
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
      previousCount,
    }
  })
  return {
    top: [...rows].sort((a, b) => b.count - a.count).slice(0, 12),
    growing: [...rows].filter((item) => item.count >= 50 && item.growth !== null)
      .sort((a, b) => (b.growth || 0) - (a.growth || 0)).slice(0, 10),
    discussed: [...rows].filter((item) => item.count >= 100)
      .sort((a, b) => b.intensity - a.intensity).slice(0, 10),
  }
})

function renderNodeStructure() {
  const rows = [...nodeInsights.value.top].reverse()
  Plotly.react("node-structure", [{
    x: rows.map((item) => item.count),
    y: rows.map((item) => item.label),
    text: rows.map((item) => `${item.share.toFixed(1)}%`),
    customdata: rows.map((item) => item.intensity),
    type: "bar",
    orientation: "h",
    marker: { color: "#4e79a7" },
    textposition: "outside",
    hovertemplate: "%{y}<br>主题 %{x:,}<br>份额 %{text}<br>平均回复 %{customdata:.1f}<extra></extra>",
  }], {
    ...chartLayout,
    margin: { t: 20, r: 60, b: 48, l: 150 },
    xaxis: { title: "主题数", rangemode: "tozero" },
    yaxis: { automargin: true },
    showlegend: false,
  }, chartConfig)
}

function renderNodeTrend() {
  const values = aggregateSeriesRows(nodes.value.rows, 1, 2, 3)
  const totals = periodsByBucket()
  const buckets = [...values.keys()].sort()
  const names = nodeInsights.value.top.slice(0, 6).map((item) => item.node)
  Plotly.react("node-trend", names.map((node, index) => ({
    x: buckets,
    y: buckets.map((bucket) => {
      const count = values.get(bucket)?.get(node)?.count || 0
      return valueMode.value === "share" ? (count / Math.max(1, totals.get(bucket) || 0)) * 100 : count
    }),
    name: nodeLabel(node),
    type: "scatter",
    mode: "lines",
    line: { color: categoricalColors[index], width: 2 },
  })), {
    ...chartLayout,
    yaxis: { title: valueMode.value === "share" ? "节点份额 (%)" : "主题数", rangemode: "tozero" },
  }, chartConfig)
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
  Plotly.react("member-trend", [
    { x: periods, y: periods.map((period) => values.get(period)![0]), name: "新增成员", type: "scatter", mode: "lines", line: { color: categoricalColors[0], width: 2 } },
    { x: periods, y: periods.map((period) => values.get(period)![1]), name: "发帖者", type: "scatter", mode: "lines", line: { color: categoricalColors[1], width: 2 } },
    { x: periods, y: periods.map((period) => values.get(period)![2]), name: "评论者", type: "scatter", mode: "lines", line: { color: categoricalColors[2], width: 2 } },
  ], { ...chartLayout, yaxis: { title: grain.value === "month" ? "每月人数" : "年度月份人数之和", rangemode: "tozero" } }, chartConfig)
}

function renderMemberRoles() {
  const aggregated = aggregateNumericRows(community.value.rows, [2, 3])
  const values = [...aggregated.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([period, row]) => ({
    period,
    ratio: row[0] ? row[1] / row[0] : 0,
  }))
  Plotly.react("member-roles", [{
    x: values.map((item: any) => item.period),
    y: values.map((item: any) => item.ratio),
    name: "评论者/发帖者",
    type: "scatter",
    mode: "lines",
    line: { color: "#0f766e", width: 2.5 },
    fill: "tozeroy",
    fillcolor: "rgba(15,118,110,0.12)",
  }], { ...chartLayout, yaxis: { title: "人数比", rangemode: "tozero" }, showlegend: false }, chartConfig)
}

function renderEngagementVolume() {
  const values = aggregateNumericRows(engagement.value.rows, [3, 4, 5, 8])
  const periods = [...values.keys()].sort()
  const labels = ["收藏", "主题感谢", "投票", "评论感谢"]
  Plotly.react("engagement-volume", labels.map((label, index) => ({
    x: periods,
    y: periods.map((period) => values.get(period)![index]),
    name: label,
    type: "scatter",
    mode: "lines",
    line: { color: categoricalColors[index], width: 2 },
  })), { ...chartLayout, yaxis: { title: "累计互动量", rangemode: "tozero" } }, chartConfig)
}

function renderEngagementEfficiency() {
  const values = aggregateNumericRows(engagement.value.rows, [1, 2, 3, 4, 5, 6])
  const periods = [...values.keys()].sort()
  Plotly.react("engagement-efficiency", [
    { x: periods, y: periods.map((period) => { const row = values.get(period)!; return row[1] ? row[2] / row[1] * 1000 : 0 }), name: "每千次点击收藏", type: "scatter", mode: "lines", line: { color: categoricalColors[0], width: 2 } },
    { x: periods, y: periods.map((period) => { const row = values.get(period)!; return row[5] ? row[3] / row[5] * 1000 : 0 }), name: "每千次回复主题感谢", type: "scatter", mode: "lines", line: { color: categoricalColors[1], width: 2 } },
    { x: periods, y: periods.map((period) => { const row = values.get(period)!; return row[0] ? row[4] / row[0] * 1000 : 0 }), name: "每千个主题投票", type: "scatter", mode: "lines", line: { color: categoricalColors[2], width: 2 } },
  ], { ...chartLayout, yaxis: { title: "标准化互动率", rangemode: "tozero" } }, chartConfig)
}

const firstReplyOrder = ["10m", "1h", "6h", "24h", "3d", "7d", "none"]
const commentAgeOrder = ["10m", "1h", "6h", "24h", "3d", "7d"]
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
  const traces = firstReplyOrder.map((replyBucket, index) => ({
    x: periods,
    y: periods.map((period) => {
      const counts = values.get(period)!
      const total = [...counts.values()].reduce((sum, value) => sum + value, 0)
      return total ? ((counts.get(replyBucket) || 0) / total) * 100 : 0
    }),
    name: lifecycleLabels[replyBucket],
    type: "bar",
    marker: { color: colors[index] },
    hovertemplate: "%{y:.1f}%<extra>%{fullData.name}</extra>",
  }))
  Plotly.react("first-reply-trend", traces, {
    ...chartLayout,
    barmode: "stack",
    yaxis: { title: "符合条件的主题占比 (%)", range: [0, 100] },
  }, chartConfig)
}

function renderCommentArrival() {
  const rows = lifecycle.value.comment_age_rows.filter((row: any[]) => lifecycleInRange(row[0], "first"))
  const counts = new Map<string, number>()
  for (const row of rows) counts.set(row[1], (counts.get(row[1]) || 0) + row[2])
  const values = commentAgeOrder.map((bucket) => counts.get(bucket) || 0)
  const total = values.reduce((sum, value) => sum + value, 0)
  let cumulative = 0
  const cumulativeValues = values.map((value) => {
    cumulative += value
    return total ? (cumulative / total) * 100 : 0
  })
  const labels = commentAgeOrder.map((bucket) => lifecycleLabels[bucket])
  Plotly.react("comment-arrival", [
    { x: labels, y: values, name: "评论数", type: "bar", marker: { color: "#2563eb" } },
    { x: labels, y: cumulativeValues, name: "累计占比", type: "scatter", mode: "lines+markers", yaxis: "y2", line: { color: "#d94841", width: 2 } },
  ], {
    ...chartLayout,
    hovermode: "x unified",
    xaxis: { tickangle: -20 },
    yaxis: { title: "评论数", rangemode: "tozero" },
    yaxis2: { title: "累计占比 (%)", overlaying: "y", side: "right", range: [0, 100] },
  }, chartConfig)
}

function renderLongTailTrend() {
  const values = new Map<string, { total: number; after24h: number; after7d: number }>()
  for (const row of lifecycle.value.long_tail_rows) {
    if (!lifecycleInRange(row[0], "tail")) continue
    const period = bucketFor(row[0])
    const current = values.get(period) || { total: 0, after24h: 0, after7d: 0 }
    current.total += row[1]
    current.after24h += row[2]
    current.after7d += row[3]
    values.set(period, current)
  }
  const periods = [...values.keys()].sort()
  Plotly.react("long-tail-trend", [
    { x: periods, y: periods.map((period) => values.get(period)!.total ? values.get(period)!.after24h / values.get(period)!.total * 100 : 0), name: "24小时后", type: "scatter", mode: "lines", line: { color: "#b45309", width: 2 } },
    { x: periods, y: periods.map((period) => values.get(period)!.total ? values.get(period)!.after7d / values.get(period)!.total * 100 : 0), name: "7天后", type: "scatter", mode: "lines", line: { color: "#7c3aed", width: 2 } },
  ], {
    ...chartLayout,
    yaxis: { title: "30日内评论占比 (%)", rangemode: "tozero" },
  }, chartConfig)
}

async function renderActiveTab() {
  await nextTick()
  if (loading.value) return
  if (activeTab.value === "overview") {
    renderOverviewTrend()
    renderIntensity()
    renderHeatmap()
  }
  if (activeTab.value === "content" && contentView.value === "topics") {
    renderTopicTrend()
    renderGroupTrend()
  }
  if (activeTab.value === "nodes") {
    renderNodeStructure()
    renderNodeTrend()
  }
  if (activeTab.value === "community") {
    renderMemberTrend()
    renderMemberRoles()
  }
  if (activeTab.value === "content" && contentView.value === "lifecycle") {
    renderFirstReplyTrend()
    renderCommentArrival()
    renderLongTailTrend()
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

async function loadActiveData() {
  let key: string = activeTab.value
  if (activeTab.value === "content") key = contentView.value === "lifecycle" ? "lifecycle" : "topics"
  if (activeTab.value === "community") key = "members"
  if (loadedData.has(key)) return
  tabLoading.value = true
  try {
    if (key === "topics") {
      topics.value = await getJson("dynamic-topics.json")
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

watch([fromPeriod, toPeriod, grain, valueMode, topLimit, selectedTag], renderActiveTab)
watch([activeTab, contentView], async () => {
  await loadActiveData()
  renderActiveTab()
})

onMounted(async () => {
  overview.value = await getJson("dynamic-overview.json")
  applyQuickRange(quickRanges[3])
  loading.value = false
  await loadActiveData()
  renderActiveTab()
})
</script>

<template>
  <main class="dashboard-shell">
    <header class="dashboard-header">
      <div>
        <h1>V2EX 社区看板</h1>
        <p class="data-scope" v-if="overview.metadata.start_period">
          数据分析范围 {{ overview.metadata.start_period }} 至 {{ overview.metadata.end_period }} ·
          {{ formatNumber(allTimeSummary.topics) }} 个有效主题 ·
          {{ formatNumber(allTimeSummary.comments) }} 条评论
        </p>
      </div>
    </header>

    <nav class="tab-list" aria-label="分析视图">
      <button v-for="tab in tabs" :key="tab.id" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">
        {{ tab.label }}
      </button>
    </nav>

    <nav v-if="activeTab === 'content'" class="subtab-list" aria-label="帖子分析视图">
      <button :class="{ active: contentView === 'topics' }" @click="contentView = 'topics'">话题演变</button>
      <button :class="{ active: contentView === 'lifecycle' }" @click="contentView = 'lifecycle'">生命周期</button>
      <button :class="{ active: contentView === 'posts' }" @click="contentView = 'posts'">代表帖子</button>
    </nav>
    <section class="filter-band" aria-label="全局数据筛选">
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
      <div v-if="(activeTab === 'content' && contentView === 'topics') || activeTab === 'nodes'" class="control-group">
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

    <div v-if="loading" class="loading">正在加载聚合数据...</div>
    <div v-else-if="tabLoading" class="loading">正在加载当前分析视图...</div>

    <section v-else-if="activeTab === 'overview'" class="view-section">
      <div class="metric-grid five">
        <article class="metric">
          <span>主题</span><strong>{{ formatNumber(currentSummary.topics) }}</strong>
          <em :class="{ down: change(currentSummary.topics, previousSummary.topics) < 0 }">较上期 {{ formatPercent(change(currentSummary.topics, previousSummary.topics), true) }}</em>
        </article>
        <article class="metric">
          <span>评论</span><strong>{{ formatNumber(currentSummary.comments) }}</strong>
          <em :class="{ down: change(currentSummary.comments, previousSummary.comments) < 0 }">较上期 {{ formatPercent(change(currentSummary.comments, previousSummary.comments), true) }}</em>
        </article>
        <article class="metric">
          <span>评论/主题</span><strong>{{ formatNumber(currentSummary.commentsPerTopic, 1) }}</strong>
          <em>讨论强度</em>
        </article>
        <article class="metric">
          <span>零回复率</span><strong>{{ formatPercent(currentSummary.zeroReplyRate) }}</strong>
          <em>同期发布主题</em>
        </article>
        <article class="metric">
          <span>新增成员</span><strong>{{ formatNumber(currentSummary.members) }}</strong>
          <em>同期注册成员</em>
        </article>
      </div>

      <div class="chart-grid two">
        <article class="analysis-block">
          <header><h2>社区发布与讨论规模</h2><p>评论使用右轴，观察发帖规模与讨论量是否同步。</p></header>
          <div id="overview-trend" class="chart"></div>
        </article>
        <article class="analysis-block">
          <header><h2>讨论强度变化</h2><p>评论密度与零回复率共同刻画社区反馈质量。</p></header>
          <div id="discussion-intensity" class="chart"></div>
        </article>
      </div>
      <article class="analysis-block full">
        <header><h2>评论活跃时段</h2><p>筛选周期内，星期与小时的累计评论分布。</p></header>
        <div id="activity-heatmap" class="chart heatmap"></div>
      </article>
    </section>

    <section v-else-if="activeTab === 'content' && contentView === 'topics'" class="view-section">
      <div class="section-toolbar">
        <div><h2>话题演变</h2><p>默认展示筛选区间内总量最高的标签；观察标签会固定加入趋势图并高亮。</p></div>
        <div class="toolbar-controls">
          <label class="inline-select topic-tag-select"><span>观察标签</span><select v-model="selectedTag"><option v-for="item in topics.tags" :key="item.tag" :value="item.tag">{{ item.tag }}</option></select></label>
          <select v-model="topLimit" aria-label="话题数量">
            <option :value="8">Top 8</option><option :value="12">Top 12</option><option :value="16">Top 16</option>
          </select>
        </div>
      </div>

      <article class="analysis-block full">
        <header><h2>标签趋势</h2><p>按涉及该标签的主题数统计，不使用正文词频重复放大。</p></header>
        <div id="topic-trend" class="chart tall"></div>
      </article>
      <article class="analysis-block full">
        <header><h2>聚合话题趋势</h2><p>同一主题可属于多个类别，因此类别之间不做堆叠求和。</p></header>
        <div id="group-trend" class="chart"></div>
      </article>

      <div class="topic-insights">
        <article class="rank-panel">
          <h3>近12个月升温</h3>
          <button v-for="item in momentum.rising" :key="item.tag" @click="chooseTag(item.tag)">
            <span>{{ item.tag }}</span><strong>+{{ item.delta.toFixed(2) }}pp</strong><em>{{ formatNumber(item.count) }}</em>
          </button>
        </article>
        <article class="rank-panel">
          <h3>近12个月降温</h3>
          <button v-for="item in momentum.falling" :key="item.tag" @click="chooseTag(item.tag)">
            <span>{{ item.tag }}</span><strong class="down">{{ item.delta.toFixed(2) }}pp</strong><em>{{ formatNumber(item.count) }}</em>
          </button>
        </article>
        <article class="tag-detail">
          <div><span>当前观察</span><h3>{{ selectedTag }}</h3></div>
          <dl>
            <div><dt>主题数</dt><dd>{{ formatNumber(selectedTagStats.count) }}</dd></div>
            <div><dt>同期占比</dt><dd>{{ selectedTagStats.share.toFixed(2) }}%</dd></div>
            <div><dt>平均回复</dt><dd>{{ selectedTagStats.repliesPerTopic.toFixed(1) }}</dd></div>
            <div><dt>峰值月份</dt><dd>{{ selectedTagStats.peak }}</dd></div>
          </dl>
          <button class="command" @click="contentView = 'posts'">查看代表帖子</button>
        </article>
      </div>

      <article class="leader-board">
        <header><h2>最近周期话题接力</h2><p>每期发帖量最高的10个标签。</p></header>
        <div class="leader-scroll">
          <div v-for="column in topicLeaders" :key="column.bucket" class="leader-column">
            <strong>{{ column.bucket }}</strong>
            <button v-for="(item, index) in column.tags" :key="item.tag" @click="chooseTag(item.tag)">
              <span>{{ index + 1 }}</span>{{ item.tag }}<em>{{ formatNumber(item.count) }}</em>
            </button>
          </div>
        </div>
      </article>
    </section>

    <section v-else-if="activeTab === 'nodes'" class="view-section">
      <div class="section-toolbar">
        <div><h2>节点生态</h2><p>节点是 V2EX 的内容分区；常见节点同时显示中文名称和 URL 标识。</p></div>
      </div>
      <div class="chart-grid two">
        <article class="analysis-block">
          <header><h2>主要节点结构</h2><p>筛选周期内主题最多的12个节点，条末为其主题份额。</p></header>
          <div id="node-structure" class="chart tall"></div>
        </article>
        <article class="analysis-block">
          <header><h2>主要节点趋势</h2><p>仅展示当前规模最大的6个节点，避免多条折线互相遮挡。</p></header>
          <div id="node-trend" class="chart tall"></div>
        </article>
      </div>
      <div class="node-insights">
        <article class="rank-panel">
          <h3>增长最快</h3>
          <div v-for="(item, index) in nodeInsights.growing" :key="item.node" class="insight-row">
            <span>{{ index + 1 }}</span><a :href="`https://www.v2ex.com/go/${item.node}`" target="_blank" rel="noreferrer">{{ item.label }}</a>
            <strong>{{ formatPercent(item.growth || 0, true) }}</strong><em>{{ formatNumber(item.count) }} 主题</em>
          </div>
        </article>
        <article class="rank-panel">
          <h3>讨论最充分</h3>
          <div v-for="(item, index) in nodeInsights.discussed" :key="item.node" class="insight-row">
            <span>{{ index + 1 }}</span><a :href="`https://www.v2ex.com/go/${item.node}`" target="_blank" rel="noreferrer">{{ item.label }}</a>
            <strong>{{ item.intensity.toFixed(1) }} 回复/主题</strong><em>{{ formatNumber(item.count) }} 主题</em>
          </div>
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
      <p class="method-note member-ranking-note">以上成员榜单为全站当前累计快照，不受时间筛选影响；下方趋势图使用当前筛选范围。账号 usdc 的评论感谢值明显异常，已从“收到感谢最多”榜单排除，汇总指标仍保留数据库原始值。</p>
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
        <header><h2>首回复速度变化</h2><p>只纳入已观察满7天的帖子；灰色部分表示7日内没有已存回复。</p></header>
        <div id="first-reply-trend" class="chart tall"></div>
      </article>
      <div class="chart-grid two">
        <article class="analysis-block">
          <header><h2>评论到达曲线</h2><p>展示发布后7日内评论数量及累计到达比例。</p></header>
          <div id="comment-arrival" class="chart"></div>
        </article>
        <article class="analysis-block">
          <header><h2>长尾讨论变化</h2><p>仅使用已观察满30天的帖子，比较24小时后与7天后的评论份额。</p></header>
          <div id="long-tail-trend" class="chart"></div>
        </article>
      </div>
      <p class="method-note">生命周期按帖子发布时间归入月份，仅统计数据库中实际保存的评论。删除、不可见及尚未补齐的评论会使响应率偏低。</p>
    </section>

    <section v-else-if="activeTab === 'content' && contentView === 'posts'" class="view-section">
      <div class="section-toolbar">
        <div><h2>代表帖子</h2><p>每月按回复、收藏、感谢和点击综合选取，避免榜单被单一高点击帖子支配。</p></div>
        <label class="inline-select"><span>标签</span><select v-model="selectedTag"><option value="">全部</option><option v-for="item in topics.tags" :key="item.tag" :value="item.tag">{{ item.tag }}</option></select></label>
      </div>
      <div class="post-list">
        <article v-for="post in filteredPosts" :key="post.id" class="post-row">
          <div class="post-main">
            <div class="post-meta"><span>{{ post.period }}</span><span>{{ post.node }}</span><span>#{{ post.id }}</span></div>
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
      </div>
    </section>

    <section v-else-if="activeTab === 'engagement'" class="view-section">
      <div class="section-toolbar">
        <div><h2>互动反馈</h2><p>比较不同发布时期内容最终积累的点击、收藏、感谢与投票。</p></div>
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
          <div><h2>全站互动代表帖</h2><p>该榜单为当前数据库快照，不受上方时间筛选影响。</p></div>
          <label class="inline-select"><span>排序指标</span><select v-model="interactionRanking"><option value="favorite_count">收藏</option><option value="thank_count">主题感谢</option><option value="votes">投票</option><option value="clicks">点击</option></select></label>
        </header>
        <div class="ranking-list">
          <a v-for="(post, index) in topInteractionPosts" :key="post.id" :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">
            <span>{{ index + 1 }}</span><strong>{{ post.title }}</strong><em>{{ formatNumber(post.value) }}</em>
          </a>
        </div>
      </article>
      <article class="leader-board interaction-ranking">
        <header><h2>感谢最多的评论</h2><p>全站当前累计快照，展示评论原文摘要，点击可跳转至原主题评论位置。</p></header>
        <div class="comment-ranking-list">
          <a v-for="(comment, index) in engagement.top_comments.slice(0, 20)" :key="comment.id" class="comment-ranking-row" :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`" target="_blank" rel="noreferrer">
            <span class="comment-rank">{{ index + 1 }}</span>
            <span class="comment-ranking-main">
              <strong>{{ comment.content || '评论原文未收录' }}</strong>
              <small>{{ comment.commenter }} · {{ comment.topic_title }} · #{{ comment.no }}</small>
            </span>
            <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
          </a>
        </div>
      </article>
      <p class="method-note">账号 usdc 的评论感谢值明显异常，已从“感谢最多的评论”榜单排除；全站汇总与趋势仍保留数据库原始值。</p>
      <p class="method-note">V2EX 未提供收藏、感谢和投票的发生时间。这里展示的是按内容发布时间分组的当前累计值，不能解释为对应月份实际发生的互动；原始值为 -1 的未知互动按 0 处理。</p>
    </section>

  </main>
</template>
