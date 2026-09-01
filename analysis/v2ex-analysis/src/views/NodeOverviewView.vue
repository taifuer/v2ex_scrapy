<script setup lang="ts">
import { onMounted } from "vue"
import PageHeader from "../components/PageHeader.vue"
import ViewSectionNav from "../components/ViewSectionNav.vue"
import { formatNumber } from "../utils/format"

defineProps<{
  trendLimit: number
  insights: {
    rising: any[]
    coreDiscussed: any[]
  }
}>()

const emit = defineEmits<{
  "update:trendLimit": [limit: number]
  openDetail: [node: string]
  ready: []
}>()

function formatPercent(value: number, signed = false) {
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(1)}%`
}

onMounted(() => emit("ready"))
</script>

<template>
  <section class="view-section">
    <PageHeader title="节点分布" description="从帖子分区观察主要节点的规模、占比和长期变化，并通过最低帖子数限制减少小样本干扰。" />
    <ViewSectionNav :items="[
      { id: 'node-structure-panel', label: '主要结构' },
      { id: 'node-trend-panel', label: '趋势变化' },
      { id: 'node-insights-panel', label: '节点观察' },
    ]" />
    <article id="node-structure-panel" class="analysis-block full section-anchor">
      <header><h2>主要节点结构</h2><p>展示所选时间范围内帖子数最多的 20 个节点，柱形标注节点帖子占比。</p></header>
      <div id="node-structure" class="chart tall"></div>
    </article>
    <article id="node-trend-panel" class="analysis-block full section-anchor">
      <header class="block-header-with-control">
        <div><h2>主要节点趋势</h2><p>展示当前帖子数最多的节点，观察主要讨论分区随时间的变化。</p></div>
        <div class="segmented compact-segmented" aria-label="趋势节点数量">
          <button :class="{ active: trendLimit === 5 }" @click="emit('update:trendLimit', 5)">Top 5</button>
          <button :class="{ active: trendLimit === 10 }" @click="emit('update:trendLimit', 10)">Top 10</button>
          <button :class="{ active: trendLimit === 20 }" @click="emit('update:trendLimit', 20)">Top 20</button>
        </div>
      </header>
      <div id="node-trend" class="chart tall"></div>
    </article>
    <div id="node-insights-panel" class="node-insights section-anchor">
      <article class="rank-panel">
        <h3>活跃上升节点</h3>
        <div v-for="(item, index) in insights.rising" :key="item.node" class="insight-row">
          <span>{{ index + 1 }}</span><button class="insight-action" @click="emit('openDetail', item.node)">{{ item.label }}</button>
          <strong>+{{ formatNumber(item.delta) }}</strong><em>{{ formatPercent(item.growth || 0, true) }}</em>
        </div>
        <p class="rank-note">仅统计当前不少于 500 个帖子且上一周期不少于 200 个帖子的节点，并按新增帖子数排序。</p>
      </article>
      <article class="rank-panel">
        <h3>高回复节点</h3>
        <div v-for="(item, index) in insights.coreDiscussed" :key="item.node" class="insight-row">
          <span>{{ index + 1 }}</span><button class="insight-action" @click="emit('openDetail', item.node)">{{ item.label }}</button>
          <strong>{{ item.intensity.toFixed(1) }} 回复/帖子</strong><em>{{ formatNumber(item.count) }} 帖子</em>
        </div>
        <p class="rank-note">仅统计当前不少于 1,000 个帖子的节点，减少小节点偶发热门帖的影响。</p>
      </article>
    </div>
  </section>
</template>
