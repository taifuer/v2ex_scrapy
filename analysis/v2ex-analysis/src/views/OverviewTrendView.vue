<script setup lang="ts">
import { onMounted } from "vue"
import MetricTile from "../components/MetricTile.vue"

const props = defineProps<{
  summary: Record<string, number>
  previous: Record<string, number>
}>()

const emit = defineEmits<{ ready: [] }>()

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
      <MetricTile label="主题" :value="formatNumber(summary.topics)" :note="changeNote('topics')" :down="change('topics') < 0" />
      <MetricTile label="评论" :value="formatNumber(summary.comments)" :note="changeNote('comments')" :down="change('comments') < 0" />
      <MetricTile label="新增成员" :value="formatNumber(summary.members)" :note="changeNote('members')" :down="change('members') < 0" />
      <MetricTile label="点击" :value="formatNumber(summary.clicks)" note="主题累计浏览量" />
      <MetricTile label="收藏" :value="formatNumber(summary.favorites)" :note="changeNote('favorites')" :down="change('favorites') < 0" />
      <MetricTile label="主题感谢" :value="formatNumber(summary.thanks)" :note="changeNote('thanks')" :down="change('thanks') < 0" />
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
</template>
