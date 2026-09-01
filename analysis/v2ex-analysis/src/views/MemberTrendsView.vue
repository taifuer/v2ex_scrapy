<script setup lang="ts">
import { onMounted } from "vue"
import MetricTile from "../components/MetricTile.vue"
import PageHeader from "../components/PageHeader.vue"
import RankedColumns from "../components/RankedColumns.vue"
import ViewSectionNav from "../components/ViewSectionNav.vue"
import type {
  MemberConcentrationLimit, MemberEvolutionMetric, RankedColumn, RankedItem,
} from "../types/analytics"
import { formatNumber } from "../utils/format"

defineProps<{
  summary: any
  evolutionMetric: MemberEvolutionMetric
  concentrationLimit: MemberConcentrationLimit
  evolutionChartStyle: Record<string, string>
  rankingColumns: RankedColumn[]
}>()

const emit = defineEmits<{
  "update:evolutionMetric": [metric: MemberEvolutionMetric]
  "update:concentrationLimit": [limit: MemberConcentrationLimit]
  select: [item: RankedItem, column: RankedColumn]
  ready: []
}>()

function selectItem(item: RankedItem, column: RankedColumn) {
  emit("select", item, column)
}

onMounted(() => emit("ready"))
</script>

<template>
  <section class="view-section">
    <PageHeader title="成员趋势" description="按月统计新注册成员，以及实际参与发帖和评论的去重用户数。" />
    <div class="metric-grid five">
      <MetricTile label="新增成员" :value="formatNumber(summary.newMembers)" note="所选时间范围内注册" />
      <MetricTile label="月均发帖用户" :value="formatNumber(summary.averageAuthors)" note="按用户名去重" />
      <MetricTile label="月均评论用户" :value="formatNumber(summary.averageCommenters)" note="按用户名去重" />
      <MetricTile label="发帖用户峰值" :value="formatNumber(summary.peakAuthors[2])" :note="summary.peakAuthors[0] || '-'" />
      <MetricTile label="评论用户峰值" :value="formatNumber(summary.peakCommenters[3])" :note="summary.peakCommenters[0] || '-'" />
    </div>
    <ViewSectionNav :items="[
      { id: 'member-evolution-panel', label: '成员演变' },
      { id: 'member-growth-panel', label: '增长参与' },
      { id: 'member-roles-panel', label: '角色结构' },
    ]" />
    <article id="member-evolution-panel" class="analysis-block full member-evolution-block section-anchor">
      <header class="block-header-with-control">
        <div><h2>成员演变</h2><p>展示每月或每年发帖、评论最多的 Top 10 成员；当前年度只统计完整月份。拖动底部时间条可浏览历史，悬停可追踪同一成员，点击可查看详情。</p></div>
        <div class="member-evolution-controls">
          <div class="segmented compact-segmented" aria-label="成员排名指标">
            <button :class="{ active: evolutionMetric === 'topics' }" @click="emit('update:evolutionMetric', 'topics')">发帖</button>
            <button :class="{ active: evolutionMetric === 'comments' }" @click="emit('update:evolutionMetric', 'comments')">评论</button>
          </div>
        </div>
      </header>
      <div id="member-evolution" class="chart evolution-heatmap" :style="evolutionChartStyle"></div>
      <RankedColumns :columns="rankingColumns" @select="selectItem" />
    </article>
    <p class="method-note member-ranking-note">三组累计 Top 10 榜单使用全部历史公开数据，不受时间筛选影响；成员演变使用所选时间范围。账号 usdc 的评论感谢值明显异常，已从累计感谢榜排除，汇总指标仍保留数据库原始值。</p>
    <article id="member-growth-panel" class="analysis-block full section-anchor">
      <header><h2>成员增长与参与</h2><p>新增成员按公开档案中的注册时间统计，发帖用户和评论用户按当月实际内容去重。</p></header>
      <div id="member-trend" class="chart tall"></div>
    </article>
    <article id="member-roles-panel" class="analysis-block full section-anchor">
      <header><h2>参与角色结构</h2><p>评论用户与发帖用户人数比越高，表示更多用户通过回复参与讨论。</p></header>
      <div id="member-roles" class="chart"></div>
      <section class="member-concentration-panel">
        <header class="block-header-with-control">
          <div><h3>头部参与占比</h3><p>每期发帖或评论量排名前 N 的成员贡献，占该期对应总量的比例；数值越高，参与越集中于少数成员。</p></div>
          <div class="segmented compact-segmented member-concentration-controls" aria-label="头部成员范围">
            <button :class="{ active: concentrationLimit === 10 }" @click="emit('update:concentrationLimit', 10)">Top 10</button>
            <button :class="{ active: concentrationLimit === 50 }" @click="emit('update:concentrationLimit', 50)">Top 50</button>
            <button :class="{ active: concentrationLimit === 100 }" @click="emit('update:concentrationLimit', 100)">Top 100</button>
          </div>
        </header>
        <div id="member-concentration" class="chart member-concentration-chart"></div>
      </section>
    </article>
  </section>
</template>
