<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import { ArrowRight } from "@lucide/vue"
import { initChart, type DashboardChart } from "../chartRuntime"
import { categoricalColors, chartTheme } from "../chartTheme"
import LoadingState from "../components/LoadingState.vue"
import MetricTile from "../components/MetricTile.vue"
import PageHeader from "../components/PageHeader.vue"
import { getJson } from "../services/dataClient"

type DistributionRow = { threshold: number; count: number }
type DistributionMetric = {
  id: string
  label: string
  observed_count: number
  maximum: number
  rows: DistributionRow[]
}
type ScaleDistribution = {
  metadata: {
    start_period: string
    end_period: string
    unknown_post_interactions: number
    excluded_thank_users: string[]
    counts: {
      posts: number
      comments: number
      topics: number
      nodes: number
      participants: number
    }
  }
  post_metrics: Record<"favorites" | "thanks" | "clicks", DistributionMetric>
  comment_thanks: DistributionMetric
  entity_metrics: Record<"topics" | "nodes", DistributionMetric>
  member_metrics: Record<"topics" | "comments" | "thanks", DistributionMetric>
}

const data = shallowRef<ScaleDistribution | null>(null)
const loading = ref(true)
const error = ref("")
const postMetric = ref<"favorites" | "thanks" | "clicks">("favorites")
const entityMetric = ref<"topics" | "nodes">("topics")
const memberMetric = ref<"topics" | "comments" | "thanks">("topics")
const postChartElement = ref<HTMLElement | null>(null)
const commentChartElement = ref<HTMLElement | null>(null)
const entityChartElement = ref<HTMLElement | null>(null)
const memberChartElement = ref<HTMLElement | null>(null)
const charts = new Map<string, DashboardChart>()
let resizeObserver: ResizeObserver | null = null

const selectedPostMetric = computed(() => data.value?.post_metrics[postMetric.value])
const selectedEntityMetric = computed(() => data.value?.entity_metrics[entityMetric.value])
const selectedMemberMetric = computed(() => data.value?.member_metrics[memberMetric.value])
const postLink = computed(() => {
  const sort = { favorites: "favorite_count", thanks: "thank_count", clicks: "clicks" }[postMetric.value]
  return `?tab=engagement&postSort=${sort}#engagement-posts`
})
const entityLink = computed(() => entityMetric.value === "topics"
  ? "?tab=content#topic-evolution-panel"
  : "?tab=content&view=nodes#node-structure-panel")

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("zh-CN")
}

function formatCompactNumber(value: number) {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(value >= 1_000_000_000 ? 0 : 1)}亿`
  if (value >= 10_000) {
    const scaled = value / 10_000
    return `${scaled.toFixed(Number.isInteger(scaled) ? 0 : 1)}万`
  }
  return formatNumber(value)
}

function thresholdLabel(value: number) {
  return `≥ ${formatCompactNumber(value)}`
}

function formatShare(count: number, denominator: number) {
  if (!denominator || !count) return "0.00%"
  const percentage = count / denominator * 100
  return percentage < 0.01 ? "<0.01%" : `${percentage.toFixed(2)}%`
}

function chartFor(key: string, element: HTMLElement) {
  const current = charts.get(key)
  if (current && !current.isDisposed()) return current
  const chart = initChart(element)
  charts.set(key, chart)
  return chart
}

function renderDistributionChart(
  key: string,
  element: HTMLElement | null,
  metric: DistributionMetric | undefined,
  denominator: number,
  color: string,
) {
  if (!element || !metric) return
  const rows = [...(metric.rows || [])].reverse()
  const chart = chartFor(key, element)
  chart.setOption({
    animationDuration: 260,
    aria: { enabled: true, description: `${metric.label}不同累计量级的对象数量` },
    grid: { left: 18, right: 18, top: 58, bottom: 46, containLabel: true },
    tooltip: {
      trigger: "item",
      borderColor: "#d9dee7",
      formatter: (params: any) => [
        `${metric.label} ${params.name}`,
        `对象数：${formatNumber(params.data.actual)}`,
        `占比：${params.data.share}`,
      ].join("<br/>"),
    },
    xAxis: {
      type: "category",
      data: rows.map(row => thresholdLabel(row.threshold)),
      name: "累计值",
      nameLocation: "middle",
      nameGap: 31,
      nameTextStyle: { color: chartTheme.axis, fontSize: 11 },
      axisLabel: { color: chartTheme.axis, fontSize: 11, interval: 0 },
      axisTick: { alignWithLabel: true, lineStyle: { color: chartTheme.axisLine } },
      axisLine: { lineStyle: { color: chartTheme.axisLine } },
    },
    yAxis: {
      type: "log",
      min: 0.9,
      name: "对象数",
      nameTextStyle: { color: chartTheme.axis, fontSize: 11, align: "right" },
      axisLabel: { color: chartTheme.axis, formatter: (value: number) => formatCompactNumber(value) },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: chartTheme.gridLine } },
    },
    series: [{
      type: "bar",
      barMaxWidth: 42,
      barMinHeight: 4,
      itemStyle: { color, borderRadius: [3, 3, 0, 0] },
      label: {
        show: true,
        position: "top",
        distance: 5,
        color: "#344054",
        fontSize: 11,
        lineHeight: 13,
        formatter: (params: any) => `${formatNumber(params.data.actual)}\n${params.data.share}`,
      },
      data: rows.map(row => ({
        value: Math.max(1, row.count),
        actual: row.count,
        share: formatShare(row.count, denominator),
      })),
    }],
  }, true)
}

async function renderCharts() {
  await nextTick()
  if (!data.value) return
  renderDistributionChart("posts", postChartElement.value, selectedPostMetric.value, selectedPostMetric.value?.observed_count || 0, categoricalColors[0])
  renderDistributionChart("comments", commentChartElement.value, data.value.comment_thanks, data.value.comment_thanks.observed_count, categoricalColors[2])
  renderDistributionChart("entities", entityChartElement.value, selectedEntityMetric.value, selectedEntityMetric.value?.observed_count || 0, categoricalColors[3])
  renderDistributionChart("members", memberChartElement.value, selectedMemberMetric.value, data.value.metadata.counts.participants, categoricalColors[4])
  for (const element of [postChartElement.value, commentChartElement.value, entityChartElement.value, memberChartElement.value]) {
    if (element) resizeObserver?.observe(element)
  }
}

async function loadData() {
  loading.value = true
  error.value = ""
  try {
    data.value = await getJson<ScaleDistribution>("dynamic-scale-distribution.json")
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "规模分布加载失败"
  } finally {
    loading.value = false
  }
  if (data.value && !error.value) await renderCharts()
}

watch([postMetric, entityMetric, memberMetric], renderCharts)

onMounted(async () => {
  await loadData()
  resizeObserver = new ResizeObserver(() => {
    for (const chart of charts.values()) chart.resize()
  })
  for (const element of [postChartElement.value, commentChartElement.value, entityChartElement.value, memberChartElement.value]) {
    if (element) resizeObserver.observe(element)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  for (const chart of charts.values()) chart.dispose()
  charts.clear()
})
</script>

<template>
  <section class="view-section scale-distribution-view" aria-label="规模分布">
    <PageHeader
      title="规模分布"
      description="统计全部完整月份中帖子、评论、话题、节点和用户的累计规模；互动数据为抓取时的累计值。"
    />

    <LoadingState v-if="loading" label="正在加载规模分布" />
    <LoadingState v-else-if="error" :label="error" retry @retry="loadData" />

    <template v-else-if="data">
      <div class="metric-grid five distribution-summary">
        <MetricTile label="参与用户" :value="formatNumber(data.metadata.counts.participants)" note="发帖或评论" compact />
        <MetricTile label="帖子" :value="formatNumber(data.metadata.counts.posts)" :note="`${data.metadata.start_period} 至 ${data.metadata.end_period}`" compact />
        <MetricTile label="评论" :value="formatNumber(data.metadata.counts.comments)" note="完整月份" compact />
        <MetricTile label="话题" :value="formatNumber(data.metadata.counts.topics)" note="同义写法已合并" compact />
        <MetricTile label="节点" :value="formatNumber(data.metadata.counts.nodes)" note="有帖子记录" compact />
      </div>

      <p class="distribution-scope-note">
        未知互动值不按 0 计入；成员感谢统计排除已知异常账号 {{ data.metadata.excluded_thank_users.join("、") }}。横轴为累计值，纵轴为对象数（对数刻度）；柱顶同时显示数量和占比。参与用户按发帖或评论账号去重，与按公开档案统计的新增成员定义不同。
      </p>

      <div class="distribution-grid">
        <article class="analysis-block distribution-card">
          <header class="block-header-with-control">
            <div><h2>帖子互动分布</h2><p>按累计收藏、感谢或浏览量观察帖子分布。</p></div>
            <div class="segmented compact-segmented" aria-label="帖子互动指标">
              <button type="button" :class="{ active: postMetric === 'favorites' }" @click="postMetric = 'favorites'">收藏</button>
              <button type="button" :class="{ active: postMetric === 'thanks' }" @click="postMetric = 'thanks'">感谢</button>
              <button type="button" :class="{ active: postMetric === 'clicks' }" @click="postMetric = 'clicks'">浏览</button>
            </div>
          </header>
          <div ref="postChartElement" class="distribution-chart"></div>
          <footer class="distribution-card-footer">
            <span>占比基数 {{ formatNumber(selectedPostMetric?.observed_count || 0) }} 个已知帖子</span>
            <a :href="postLink">查看热门帖子 <ArrowRight :size="14" aria-hidden="true" /></a>
          </footer>
        </article>

        <article class="analysis-block distribution-card">
          <header>
            <div><h2>评论感谢分布</h2><p>按累计感谢数观察评论分布。</p></div>
          </header>
          <div ref="commentChartElement" class="distribution-chart"></div>
          <footer class="distribution-card-footer">
            <span>占比基数 {{ formatNumber(data.comment_thanks.observed_count) }} 条评论</span>
            <a href="?tab=engagement#engagement-comments">查看热门评论 <ArrowRight :size="14" aria-hidden="true" /></a>
          </footer>
        </article>

        <article class="analysis-block distribution-card">
          <header class="block-header-with-control">
            <div><h2>话题与节点分布</h2><p>按累计帖子数观察话题与节点分布。</p></div>
            <div class="segmented compact-segmented" aria-label="讨论对象类型">
              <button type="button" :class="{ active: entityMetric === 'topics' }" @click="entityMetric = 'topics'">话题</button>
              <button type="button" :class="{ active: entityMetric === 'nodes' }" @click="entityMetric = 'nodes'">节点</button>
            </div>
          </header>
          <div ref="entityChartElement" class="distribution-chart"></div>
          <footer class="distribution-card-footer">
            <span>占比基数 {{ formatNumber(selectedEntityMetric?.observed_count || 0) }} 个{{ selectedEntityMetric?.label }}</span>
            <a :href="entityLink">查看{{ selectedEntityMetric?.label }}分析 <ArrowRight :size="14" aria-hidden="true" /></a>
          </footer>
        </article>

        <article class="analysis-block distribution-card">
          <header class="block-header-with-control">
            <div><h2>成员参与分布</h2><p>按累计发帖、评论或收到感谢数观察用户分布。</p></div>
            <div class="segmented compact-segmented" aria-label="成员参与指标">
              <button type="button" :class="{ active: memberMetric === 'topics' }" @click="memberMetric = 'topics'">发帖</button>
              <button type="button" :class="{ active: memberMetric === 'comments' }" @click="memberMetric = 'comments'">评论</button>
              <button type="button" :class="{ active: memberMetric === 'thanks' }" @click="memberMetric = 'thanks'">感谢</button>
            </div>
          </header>
          <div ref="memberChartElement" class="distribution-chart"></div>
          <footer class="distribution-card-footer">
            <span>占比基数 {{ formatNumber(data.metadata.counts.participants) }} 位参与用户</span>
            <a href="?tab=community#member-evolution-panel">查看成员分析 <ArrowRight :size="14" aria-hidden="true" /></a>
          </footer>
        </article>
      </div>
    </template>
  </section>
</template>
