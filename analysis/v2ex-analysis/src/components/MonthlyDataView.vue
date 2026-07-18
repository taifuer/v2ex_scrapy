<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ChevronLeft, ChevronRight, ExternalLink, MessageSquareText } from "@lucide/vue"
import MetricTile from "./MetricTile.vue"
import PeriodSelect from "./PeriodSelect.vue"
import RankedColumns from "./RankedColumns.vue"

const props = withDefaults(defineProps<{
  profile: any
  loading: boolean
  periods: string[]
  selectedPeriod: string
  periodType?: "month" | "year"
}>(), { periodType: "month" })

const emit = defineEmits<{
  selectPeriod: [period: string]
  selectTag: [tag: string]
  selectMember: [username: string]
}>()

const selectedIndex = computed(() => props.periods.indexOf(props.selectedPeriod))
const previousPeriod = computed(() => selectedIndex.value > 0 ? props.periods[selectedIndex.value - 1] : "")
const nextPeriod = computed(() => selectedIndex.value >= 0 && selectedIndex.value < props.periods.length - 1 ? props.periods[selectedIndex.value + 1] : "")
const postSort = ref<"score" | "favorite_count" | "thank_count" | "clicks">("score")
const postPage = ref(1)
const commentPage = ref(1)
const postPageSize = 10
const postsById = computed(() => new Map((props.profile?.posts || []).map((post: any) => [post.id, post])))
const rankedPosts = computed(() => (props.profile?.postRankings?.[postSort.value] || [])
  .map((id: number) => postsById.value.get(id))
  .filter(Boolean))
const postPageCount = computed(() => Math.max(1, Math.ceil(rankedPosts.value.length / postPageSize)))
const displayedPosts = computed(() => rankedPosts.value.slice((postPage.value - 1) * postPageSize, postPage.value * postPageSize))
const rankedComments = computed(() => props.profile?.comments || [])
const commentPageCount = computed(() => Math.max(1, Math.ceil(rankedComments.value.length / postPageSize)))
const displayedComments = computed(() => rankedComments.value.slice((commentPage.value - 1) * postPageSize, commentPage.value * postPageSize))

watch(() => props.selectedPeriod, () => { postPage.value = 1; commentPage.value = 1 })
watch(postSort, () => { postPage.value = 1 })

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}

function formatPeriod(period: string) {
  if (props.periodType === "year") return `${period} 年`
  const [year, month] = period.split("-")
  return year && month ? `${year} 年 ${Number(month)} 月` : period
}

function formatDateTime(timestamp: number) {
  if (!timestamp) return "时间未知"
  return new Date(timestamp * 1000).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  })
}

function deltaText(value: number | null, label: string) {
  if (value === null) return `${label}暂无`
  return `${label}${value > 0 ? "+" : ""}${value.toFixed(1)}%`
}

function metricNote(metric: any) {
  if (props.periodType === "year") return deltaText(metric.yearDelta, "同比")
  return `${deltaText(metric.monthDelta, "环比")} · ${deltaText(metric.yearDelta, "同比")}`
}

const periodNoun = computed(() => props.periodType === "year" ? "年" : "月")
const periodViewLabel = computed(() => props.periodType === "year" ? "年度" : "月度")
const reportLabel = computed(() => props.periodType === "year" ? "社区年报" : "社区月报")
const previousPeriodLabel = computed(() => props.periodType === "year" ? "上一年" : "上个月")
const nextPeriodLabel = computed(() => props.periodType === "year" ? "下一年" : "下个月")
const rankingColumns = computed(() => [
  {
    key: "tags",
    title: "热门话题",
    items: (props.profile?.tags || []).slice(0, 20).map((item: any) => ({
      key: item.name, label: item.name, value: `${formatNumber(item.value)} 主题`, action: item.name,
    })),
  },
  {
    key: "nodes",
    title: "热门节点",
    items: (props.profile?.nodes || []).slice(0, 20).map((item: any) => ({
      key: item.name, label: item.label, value: `${formatNumber(item.value)} 主题`, href: `https://www.v2ex.com/go/${item.name}`,
    })),
  },
  {
    key: "members",
    title: "活跃用户",
    items: (props.profile?.members || []).slice(0, 20).map((item: any) => ({
      key: item.name, label: item.name, value: `${formatNumber(item.value)} 主题`, action: item.name,
    })),
  },
])

function selectRankingItem(item: any, column: any) {
  if (column.key === "tags") emit("selectTag", item.action)
  if (column.key === "members") emit("selectMember", item.action)
}

function displayIndex(index: string | number) {
  return Number(index) + 1
}

function postMetric(post: any) {
  if (postSort.value === "favorite_count") return `${formatNumber(post.favorite_count)} 收藏`
  if (postSort.value === "thank_count") return `${formatNumber(post.thank_count)} 感谢`
  if (postSort.value === "clicks") return `${formatNumber(post.clicks)} 点击`
  return `综合 ${formatNumber(post.score, 1)}`
}
</script>

<template>
  <section class="view-section monthly-data-view" :aria-label="periodViewLabel">
    <header class="monthly-data-header">
      <div>
        <span class="section-eyebrow">{{ reportLabel }}</span>
        <h2>{{ formatPeriod(selectedPeriod) }}数据<span v-if="profile?.periodNote" class="period-status">（{{ profile.periodNote }}）</span></h2>
        <p v-if="periodType === 'year'">集中查看年度规模、成员参与、热门话题、热门节点与代表内容；未满年度按相同月份范围同比。</p>
        <p v-else>集中查看单月规模、成员参与、热门话题、热门节点与代表内容；变化率分别与上月和上年同月比较。</p>
      </div>
      <div class="month-navigation" :aria-label="`${periodNoun}份选择`">
        <button type="button" :title="previousPeriodLabel" :aria-label="previousPeriodLabel" :disabled="!previousPeriod" @click="emit('selectPeriod', previousPeriod)">
          <ChevronLeft :size="18" aria-hidden="true" />
        </button>
        <PeriodSelect :label="`选择${periodNoun}份`" :model-value="selectedPeriod" :periods="periods" @update:model-value="emit('selectPeriod', $event)" />
        <button type="button" :title="nextPeriodLabel" :aria-label="nextPeriodLabel" :disabled="!nextPeriod" @click="emit('selectPeriod', nextPeriod)">
          <ChevronRight :size="18" aria-hidden="true" />
        </button>
      </div>
    </header>

    <div v-if="loading || !profile" class="profile-loading"><span class="loading-spinner"></span><strong>正在整理该{{ periodNoun }}数据</strong></div>
    <template v-else>
      <div class="monthly-metrics">
        <MetricTile label="主题" :value="formatNumber(profile.metrics.topics.value)" :note="metricNote(profile.metrics.topics)" :down="profile.metrics.topics.monthDelta < 0" compact />
        <MetricTile label="评论" :value="formatNumber(profile.metrics.comments.value)" :note="metricNote(profile.metrics.comments)" :down="profile.metrics.comments.monthDelta < 0" compact />
        <MetricTile label="新增成员" :value="formatNumber(profile.metrics.members.value)" :note="metricNote(profile.metrics.members)" :down="profile.metrics.members.monthDelta < 0" compact />
        <MetricTile label="发帖用户" :value="formatNumber(profile.metrics.authors.value)" :note="metricNote(profile.metrics.authors)" :down="profile.metrics.authors.monthDelta < 0" compact />
        <MetricTile label="评论用户" :value="formatNumber(profile.metrics.commenters.value)" :note="metricNote(profile.metrics.commenters)" :down="profile.metrics.commenters.monthDelta < 0" compact />
        <MetricTile label="收藏" :value="formatNumber(profile.metrics.favorites.value)" :note="metricNote(profile.metrics.favorites)" :down="profile.metrics.favorites.monthDelta < 0" compact />
        <MetricTile label="主题感谢" :value="formatNumber(profile.metrics.thanks.value)" :note="metricNote(profile.metrics.thanks)" :down="profile.metrics.thanks.monthDelta < 0" compact />
        <MetricTile label="平均回复" :value="formatNumber(profile.metrics.commentsPerTopic.value, 1)" :note="metricNote(profile.metrics.commentsPerTopic)" :down="profile.metrics.commentsPerTopic.monthDelta < 0" compact />
      </div>

      <section v-if="profile.events.length" class="period-events">
        <strong>{{ periodType === 'year' ? '年度事件' : '当月事件' }}</strong>
        <a v-for="event in profile.events" :key="event.title" :href="event.url" target="_blank" rel="noreferrer">
          <span>{{ event.date }}</span>{{ event.title }}<ExternalLink :size="12" aria-hidden="true" />
        </a>
      </section>

      <RankedColumns :columns="rankingColumns" @select="selectRankingItem" />

      <section class="analysis-block full monthly-posts">
        <header class="block-header-with-control">
          <div><h2><MessageSquareText :size="16" aria-hidden="true" />代表帖子</h2><p>每个排序指标都从该{{ periodNoun }}全部有效帖子中独立选取 Top 100，推广节点除外。</p></div>
          <div class="control-group monthly-post-sort">
            <span>排序指标</span>
            <div class="segmented compact-segmented" :aria-label="`${periodViewLabel}代表帖子排序指标`">
              <button :class="{ active: postSort === 'score' }" @click="postSort = 'score'">综合</button>
              <button :class="{ active: postSort === 'favorite_count' }" @click="postSort = 'favorite_count'">收藏</button>
              <button :class="{ active: postSort === 'thank_count' }" @click="postSort = 'thank_count'">感谢</button>
              <button :class="{ active: postSort === 'clicks' }" @click="postSort = 'clicks'">点击</button>
            </div>
          </div>
        </header>
        <a v-for="post in displayedPosts" :key="post.id" :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">
          <span><strong>{{ post.title }}</strong><small>{{ formatDateTime(post.create_at) }} · {{ post.author }} · {{ post.nodeLabel }} · #{{ post.id }}</small></span>
          <em>{{ postMetric(post) }}</em>
        </a>
        <p v-if="!rankedPosts.length" class="empty-state compact-empty">该{{ periodNoun }}没有可用代表帖子。</p>
        <footer v-if="rankedPosts.length" class="ranking-pagination monthly-post-pagination">
          <span>Top {{ formatNumber(rankedPosts.length) }} · 第 {{ postPage }} / {{ postPageCount }} 页</span>
          <nav :aria-label="`${periodViewLabel}代表帖子分页`">
            <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="postPage <= 1" @click="postPage--">‹</button>
            <button v-for="page in postPageCount" :key="page" class="pagination-number" :class="{ active: page === postPage }" :aria-current="page === postPage ? 'page' : undefined" @click="postPage = page">{{ page }}</button>
            <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="postPage >= postPageCount" @click="postPage++">›</button>
          </nav>
        </footer>
      </section>

      <section class="analysis-block full monthly-comments">
        <header><h2><MessageSquareText :size="16" aria-hidden="true" />代表评论</h2><p>按评论发布时间归入该{{ periodNoun }}，展示累计感谢最多的 Top 100 评论。</p></header>
        <a v-for="(comment, index) in displayedComments" :key="comment.id" class="comment-ranking-row" :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`" target="_blank" rel="noreferrer">
          <span class="comment-rank">{{ (commentPage - 1) * postPageSize + displayIndex(index) }}</span>
          <span class="comment-ranking-main">
            <strong>{{ comment.content || "评论原文未收录" }}</strong>
            <small>{{ formatDateTime(comment.create_at) }} · {{ comment.commenter }} · {{ comment.topic_title }} · #{{ comment.no }}</small>
          </span>
          <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
        </a>
        <p v-if="!rankedComments.length" class="empty-state compact-empty">该{{ periodNoun }}没有获得感谢的评论。</p>
        <footer v-if="rankedComments.length" class="ranking-pagination monthly-comment-pagination">
          <span>Top {{ formatNumber(rankedComments.length) }} · 第 {{ commentPage }} / {{ commentPageCount }} 页</span>
          <nav :aria-label="`${periodViewLabel}代表评论分页`">
            <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="commentPage <= 1" @click="commentPage--">‹</button>
            <button v-for="page in commentPageCount" :key="page" class="pagination-number" :class="{ active: page === commentPage }" :aria-current="page === commentPage ? 'page' : undefined" @click="commentPage = page">{{ page }}</button>
            <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="commentPage >= commentPageCount" @click="commentPage++">›</button>
          </nav>
        </footer>
      </section>
    </template>
  </section>
</template>
