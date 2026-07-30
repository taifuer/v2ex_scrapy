<script setup lang="ts">
import { onMounted } from "vue"
import MetricTile from "../components/MetricTile.vue"
import PageHeader from "../components/PageHeader.vue"

defineProps<{
  summary: Record<string, number>
  completeThrough?: string
}>()

const emit = defineEmits<{ ready: [] }>()

function formatPercent(value: number | undefined) {
  return `${Number(value || 0).toFixed(1)}%`
}

onMounted(() => emit("ready"))
</script>

<template>
  <section class="view-section">
    <PageHeader
      title="帖子生命周期"
      :description="`衡量帖子获得首条回复的速度，以及讨论从发布后数小时延续到数天的过程。完整观察截至 ${completeThrough || '未知'}。`"
    />
    <div class="metric-grid five">
      <MetricTile label="7日内获得回复" :value="formatPercent(summary.responseRate)" note="已观察满7天的主题" />
      <MetricTile label="1小时内首回" :value="formatPercent(summary.within1hRate)" note="占符合条件主题" />
      <MetricTile label="24小时内首回" :value="formatPercent(summary.within24hRate)" note="占符合条件主题" />
      <MetricTile label="首小时评论" :value="formatPercent(summary.firstHourShare)" note="占前7日评论" />
      <MetricTile label="7天后评论" :value="formatPercent(summary.after7dShare)" note="占前30日评论" />
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
</template>
