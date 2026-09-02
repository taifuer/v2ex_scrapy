<script setup lang="ts">
import { onMounted } from "vue"
import AggregateGroupCards from "../components/AggregateGroupCards.vue"
import AggregateGroupTrend from "../components/AggregateGroupTrend.vue"
import MetricTile from "../components/MetricTile.vue"
import PageHeader from "../components/PageHeader.vue"
import RankedColumns from "../components/RankedColumns.vue"
import StageHotspots from "../components/StageHotspots.vue"
import ViewSectionNav from "../components/ViewSectionNav.vue"
import type { Grain, RankedColumn, RankedItem } from "../types/analytics"
import type { StageHotspot } from "../utils/stageHotspots"
import { formatNumber } from "../utils/format"

defineProps<{
  summary: any
  previousSummary: any
  postSummary: any
  topLimit: number
  trendLimit: number
  evolutionChartStyle: Record<string, string>
  rankingColumns: RankedColumn[]
  groups: any[]
  groupRows: any[]
  groupCards: any[]
  stageHotspots: StageHotspot[]
  stagePeriods: string[]
  periodTotals: Record<string, number>
  fromPeriod: string
  toPeriod: string
  grain: Grain
}>()

const emit = defineEmits<{
  "update:topLimit": [limit: number]
  "update:trendLimit": [limit: number]
  select: [item: RankedItem, column: RankedColumn]
  selectGroupTopic: [key: string, action?: string]
  selectStageTopic: [key: string]
  ready: []
}>()

function change(current: number, previous: number) {
  return previous ? ((current - previous) / previous) * 100 : 0
}

function formatPercent(value: number, signed = false) {
  return `${signed && value > 0 ? "+" : ""}${value.toFixed(1)}%`
}

function selectItem(item: RankedItem, column: RankedColumn) {
  emit("select", item, column)
}

function selectGroupTopic(key: string, action?: string) {
  emit("selectGroupTopic", key, action)
}

onMounted(() => emit("ready"))
</script>

<template>
  <section class="view-section">
    <PageHeader title="话题演变" description="默认展示所选时间范围内帖子数最多的话题；点击话题即可查看详情。" />

    <div class="metric-grid six">
      <MetricTile label="帖子" :value="formatNumber(summary.topics)" :note="`较上期 ${formatPercent(change(summary.topics, previousSummary.topics), true)}`" :down="change(summary.topics, previousSummary.topics) < 0" />
      <MetricTile label="评论" :value="formatNumber(summary.comments)" :note="`较上期 ${formatPercent(change(summary.comments, previousSummary.comments), true)}`" :down="change(summary.comments, previousSummary.comments) < 0" />
      <MetricTile label="月均帖子" :value="formatNumber(postSummary.monthlyTopics)" note="所选时间范围" />
      <MetricTile label="平均回复" :value="formatNumber(summary.commentsPerTopic, 1)" note="每个帖子" />
      <MetricTile label="零回复率" :value="formatPercent(summary.zeroReplyRate)" :note="`${formatNumber(summary.zeroReplies)} 个帖子`" />
      <MetricTile label="活跃话题" :value="formatNumber(postSummary.activeTags)" note="所选时间范围内有发帖" />
    </div>

    <ViewSectionNav :items="[
      { id: 'topic-evolution-panel', label: '话题演变' },
      { id: 'topic-stage-panel', label: '阶段热点' },
      { id: 'topic-trend-panel', label: '话题趋势' },
      { id: 'group-trend-panel', label: '话题板块' },
    ]" />

    <article id="topic-evolution-panel" class="analysis-block full section-anchor">
      <header class="block-header-with-control">
        <div><h2>各期话题排名</h2><p>每列展示该月或该年帖子数最多的话题，行表示当期排名；颜色越深，帖子数越多，拖动底部时间条可浏览历史。</p></div>
        <div class="segmented compact-segmented" aria-label="话题数量">
          <button :class="{ active: topLimit === 10 }" @click="emit('update:topLimit', 10)">Top 10</button>
          <button :class="{ active: topLimit === 20 }" @click="emit('update:topLimit', 20)">Top 20</button>
          <button :class="{ active: topLimit === 30 }" @click="emit('update:topLimit', 30)">Top 30</button>
        </div>
      </header>
      <div id="topic-evolution" class="chart evolution-heatmap" :style="evolutionChartStyle"></div>
      <RankedColumns :columns="rankingColumns" @select="selectItem" />
      <p class="method-note">说明：本看板将 V2EX 帖子携带的原始标签统一称为“话题”；同一帖子可包含多个话题。区间热门话题按所选时间范围累计；上升和下降话题比较筛选结束月份之前的最近 12 个完整月与此前 12 个月的帖子占比变化。由标题分词得到的“标题关键词”单独统计，不等同于话题。</p>
    </article>

    <StageHotspots
      id="topic-stage-panel"
      :items="stageHotspots"
      :periods="stagePeriods"
      entity-label="话题"
      @select="emit('selectStageTopic', $event)"
    />

    <section id="topic-trend-panel" class="topic-trend-view section-anchor" aria-label="话题趋势分析">
      <article class="analysis-block full">
        <header class="block-header-with-control">
          <div><h2>话题趋势</h2><p>展示所选时间范围内主要话题的连续变化。一个帖子可以包含多个话题，因此使用折线图；点击折线可查看话题详情。</p></div>
          <div class="segmented compact-segmented" aria-label="趋势话题数量">
            <button :class="{ active: trendLimit === 10 }" @click="emit('update:trendLimit', 10)">Top 10</button>
            <button :class="{ active: trendLimit === 20 }" @click="emit('update:trendLimit', 20)">Top 20</button>
            <button :class="{ active: trendLimit === 30 }" @click="emit('update:trendLimit', 30)">Top 30</button>
          </div>
        </header>
        <div id="topic-trend" class="chart tall"></div>
      </article>
    </section>

    <section id="group-trend-panel" class="topic-group-section section-anchor">
      <article class="analysis-block full">
        <header><h2>话题板块趋势</h2><p>按各期帖子占比观察板块结构变化。一个帖子可以属于多个板块，因此使用折线图。</p></header>
        <AggregateGroupTrend
          :groups="groups"
          :rows="groupRows"
          :period-totals="periodTotals"
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
          :cards="groupCards"
          count-label="相关帖子"
          item-label="主要话题"
          empty-text="暂无符合展示条件的话题"
          @select="selectGroupTopic"
        />
        <p class="method-note topic-group-note">板块只使用帖子所在节点和 V2EX 原始话题，不读取标题关键词。同一帖子在单个板块内只计一次，但可以进入多个板块，因此各板块数量不能相加。话题至少涉及 3 个帖子且达到板块帖子数的 1%，或累计达到 100 个帖子时显示。推广、拼车、免费和优惠节点不计入；标题中的讨论线索可在“标题关键词演变”中查看。</p>
      </article>
    </section>
  </section>
</template>
