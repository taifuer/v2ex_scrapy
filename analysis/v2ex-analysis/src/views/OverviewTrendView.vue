<script setup lang="ts">
import { onMounted } from "vue"
import MetricTile from "../components/MetricTile.vue"

const props = defineProps<{
  summary: Record<string, number>
  previous: Record<string, number>
  activityMetric: "topics" | "comments"
}>()

const emit = defineEmits<{
  ready: []
  "select-activity-metric": [metric: "topics" | "comments"]
}>()

function formatNumber(value: number | undefined) {
  return Number(value || 0).toLocaleString("zh-CN")
}

function change(key: string) {
  const previous = Number(props.previous[key] || 0)
  return previous ? ((Number(props.summary[key] || 0) - previous) / previous) * 100 : 0
}

function changeNote(key: string) {
  const value = change(key)
  return `较上期 ${value > 0 ? "+" : ""}${value.toFixed(1)}%`
}

onMounted(() => emit("ready"))
</script>

<template>
  <section class="view-section">
    <div class="metric-grid six">
      <MetricTile label="帖子" :value="formatNumber(summary.topics)" :note="changeNote('topics')" :down="change('topics') < 0" />
      <MetricTile label="评论" :value="formatNumber(summary.comments)" :note="changeNote('comments')" :down="change('comments') < 0" />
      <MetricTile label="新增成员" :value="formatNumber(summary.members)" :note="changeNote('members')" :down="change('members') < 0" />
      <MetricTile label="点击" :value="formatNumber(summary.clicks)" note="帖子累计浏览量" compact />
      <MetricTile label="收藏" :value="formatNumber(summary.favorites)" :note="changeNote('favorites')" :down="change('favorites') < 0" />
      <MetricTile label="帖子感谢" :value="formatNumber(summary.thanks)" :note="changeNote('thanks')" :down="change('thanks') < 0" />
    </div>
    <div class="chart-grid two">
      <article class="analysis-block">
        <header><h2>社区规模与参与</h2><p>成员表示首次发帖成员；成员、帖子与评论使用独立刻度，共享时间轴观察参与规模变化。</p></header>
        <div id="overview-trend" class="chart overview-metric-chart"></div>
      </article>
      <article class="analysis-block">
        <header><h2>帖子互动反馈</h2><p>点击、收藏与感谢按帖子发布时间归期；感谢仅统计帖子收到的感谢，数值为当前累计快照。</p></header>
        <div id="overview-participation" class="chart overview-metric-chart"></div>
      </article>
    </div>
    <article class="analysis-block full">
      <header class="activity-chart-header">
        <div><h2>活跃时段</h2><p>筛选周期内，发帖或评论在星期与小时上的累计分布。</p></div>
        <div class="segmented activity-metric-toggle" aria-label="活跃时段指标">
          <button type="button" :class="{ active: activityMetric === 'topics' }" :aria-pressed="activityMetric === 'topics'" @click="emit('select-activity-metric', 'topics')">发帖</button>
          <button type="button" :class="{ active: activityMetric === 'comments' }" :aria-pressed="activityMetric === 'comments'" @click="emit('select-activity-metric', 'comments')">评论</button>
        </div>
      </header>
      <div id="activity-heatmap" class="chart heatmap"></div>
    </article>
  </section>
</template>
