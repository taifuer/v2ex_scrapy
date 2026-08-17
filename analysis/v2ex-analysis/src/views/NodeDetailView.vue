<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import PeriodSelect from "../components/PeriodSelect.vue"
import RepresentativeComments from "../components/RepresentativeComments.vue"
import SearchSelect from "../components/SearchSelect.vue"
import { formatDateTime, formatNumber } from "../utils/format"
import RankedColumns from "../components/RankedColumns.vue"
import { paginationItems } from "../utils/pagination"
import type {
  RankedColumn, RankedItem, RepresentativeComment, RepresentativeCommentSummary,
  RepresentativePost, SearchOption,
} from "../types/analytics"

const props = defineProps<{
  node: string
  loading: boolean
  detail: any
  summary: any
  options: SearchOption[]
  columns: RankedColumn[]
  label: string
  grain: "month" | "year"
  selectedPeriod: string
  periodOptions: string[]
  periodLabels: Record<string, string>
  periodPosts: RepresentativePost[]
  periodPostsLoading: boolean
  periodPostsError: string
  periodComments: RepresentativeComment[]
  periodCommentSummary: RepresentativeCommentSummary
  periodCommentsLoading: boolean
  periodCommentsError: string
}>()
const emit = defineEmits<{
  "update:node": [node: string]
  "update:selectedPeriod": [period: string]
  select: [item: RankedItem]
  topic: [tag: string]
  member: [username: string]
  ready: []
}>()
const pageSize = 10
const postPage = ref(1)
const postSource = computed<RepresentativePost[]>(() => props.selectedPeriod
  ? props.periodPosts
  : props.detail?.posts || [])
const postCount = computed(() => postSource.value.length)
const postPageCount = computed(() => Math.max(1, Math.ceil(postCount.value / pageSize)))
const postPaginationItems = computed(() => paginationItems(postPage.value, postPageCount.value))
const posts = computed<RepresentativePost[]>(() => postSource.value.slice(
  (postPage.value - 1) * pageSize,
  postPage.value * pageSize,
))
const postsTitle = computed(() => props.selectedPeriod
  ? `${props.selectedPeriod} 代表帖子`
  : "代表帖子")
const postsDescription = computed(() => {
  if (!props.selectedPeriod) return "根据回复、收藏、感谢、投票和点击计算综合得分，展示全部历史数据中的 Top 100。"
  return props.grain === "month"
    ? "按综合互动得分展示该月代表帖子：帖子不少于 100 个时显示 Top 10，不少于 20 个时显示 Top 5，其余显示 Top 3。"
    : "按综合互动得分展示该年度 Top 10；再次点击实心圆点或选择全部时间可恢复。"
})
const commentsDescription = computed(() => {
  if (props.selectedPeriod) return ""
  return `每年保留感谢数最高的 10 条相关评论，合并后按感谢数展示 Top ${formatNumber(props.periodComments.length)}；仅收录至少获得 1 次感谢的评论。`
})
watch([() => props.node, () => props.selectedPeriod], () => { postPage.value = 1 })
watch(postPageCount, (count) => {
  if (postPage.value > count) postPage.value = count
})
onMounted(() => emit("ready"))

</script>

<template>
  <section class="view-section">
    <article id="node-detail" class="analysis-block full node-detail-block">
      <header class="block-header-with-control">
        <div>
          <h2>节点详情：{{ label }}</h2>
          <p>规模与趋势按所选时间范围统计；主要话题、主要标题关键词、活跃用户、代表帖子和代表评论按全部历史数据统计。</p>
        </div>
        <div class="detail-actions topic-detail-actions">
          <SearchSelect
            :model-value="node"
            class="node-detail-select"
            label="选择节点"
            icon="node"
            hide-label
            :options="options"
            @update:model-value="emit('update:node', $event)"
          />
          <a :href="`https://www.v2ex.com/go/${encodeURIComponent(node)}`" target="_blank" rel="noreferrer">查看 V2EX 节点</a>
        </div>
      </header>
      <div v-if="loading" class="loading compact-loading"><span class="loading-spinner"></span></div>
      <template v-else-if="detail && summary">
        <div class="metric-grid five node-detail-metrics">
          <article class="metric"><span>帖子</span><strong>{{ formatNumber(summary.count) }}</strong><em>所选时间范围</em></article>
          <article class="metric"><span>帖子份额</span><strong>{{ summary.share.toFixed(2) }}%</strong><em>占有效帖子</em></article>
          <article class="metric"><span>平均回复</span><strong>{{ formatNumber(summary.repliesPerTopic, 1) }}</strong><em>每个帖子</em></article>
          <article class="metric"><span>平均点击</span><strong>{{ formatNumber(summary.clicksPerTopic) }}</strong><em>每个帖子</em></article>
          <article class="metric"><span>活跃峰值</span><strong>{{ summary.peak }}</strong><em>帖子数最高时期</em></article>
        </div>
        <section class="topic-detail-trend">
          <header><h3>{{ label }}趋势</h3><p>帖子数使用左轴，平均回复使用右轴；点击帖子折线的空心圆点可查看该期代表帖子，实心圆点表示已选中。</p></header>
          <div id="node-detail-trend" class="chart compact-chart"></div>
        </section>
        <p class="topic-detail-scope-note">以下数据按全部历史记录统计：该节点共 {{ formatNumber(detail.total) }} 个帖子；话题、标题关键词和用户数量均按该节点内的相关帖子数计算。</p>
        <RankedColumns :columns="columns" @select="(item) => emit('select', item)" />
        <section id="node-representative-posts" class="topic-detail-posts node-detail-posts representative-posts-anchor">
          <header class="content-section-header">
            <div><h3>{{ postsTitle }}</h3><p>{{ postsDescription }}</p></div>
            <PeriodSelect
              :model-value="selectedPeriod"
              class="topic-post-period-select"
              label="代表帖子时间"
              hide-label
              :periods="periodOptions"
              :option-labels="periodLabels"
              @update:model-value="emit('update:selectedPeriod', $event)"
            />
          </header>
          <div v-if="periodPostsLoading" class="loading compact-loading"><span class="loading-spinner"></span></div>
          <p v-else-if="periodPostsError" class="empty-state compact-empty">{{ periodPostsError }}</p>
          <div v-else class="post-list">
            <article v-for="post in posts" :key="post.id" class="post-row">
              <div class="post-main">
                <div class="post-meta">
                  <span>{{ formatDateTime(post.create_at) }}</span>
                  <button v-if="post.author" class="text-action" @click="emit('member', post.author)">{{ post.author }}</button>
                  <span>#{{ post.id }}</span>
                </div>
                <a :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">{{ post.title }}</a>
                <div class="post-tags"><button v-for="tag in post.tags.slice(0, 6)" :key="tag" @click="emit('topic', tag)">{{ tag }}</button></div>
              </div>
              <dl>
                <div><dt>点击</dt><dd>{{ formatNumber(post.clicks) }}</dd></div>
                <div><dt>回复</dt><dd>{{ formatNumber(post.reply_count) }}</dd></div>
                <div><dt>收藏</dt><dd>{{ formatNumber(post.favorite_count) }}</dd></div>
                <div><dt>感谢</dt><dd>{{ formatNumber(post.thank_count) }}</dd></div>
              </dl>
            </article>
            <p v-if="!postSource.length" class="empty-state compact-empty">该节点在所选时间范围内暂无代表帖子。</p>
            <footer v-else-if="postCount > pageSize" class="ranking-pagination detail-pagination">
              <span>共 {{ formatNumber(postCount) }} 帖 · 第 {{ postPage }} / {{ postPageCount }} 页</span>
              <nav aria-label="节点代表帖子分页">
                <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="postPage <= 1" @click="postPage--">‹</button>
                <template v-for="item in postPaginationItems" :key="item">
                  <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === postPage }" :aria-current="item === postPage ? 'page' : undefined" @click="postPage = item">{{ item }}</button>
                  <span v-else class="pagination-gap" aria-hidden="true">…</span>
                </template>
                <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="postPage >= postPageCount" @click="postPage++">›</button>
              </nav>
            </footer>
          </div>
          <p v-if="node === 'promotions'" class="method-note representative-note">推广节点保留规模与结构统计，但不输出代表帖子。</p>
        </section>
        <RepresentativeComments
          :comments="periodComments"
          :summary="periodCommentSummary"
          :title="selectedPeriod ? `${selectedPeriod} 代表评论` : '代表评论'"
          :period="selectedPeriod"
          :description="commentsDescription"
          :loading="periodCommentsLoading"
          :error="periodCommentsError"
          empty-text="该节点相关帖子暂无获得感谢的代表评论。"
        />
      </template>
      <p v-else class="empty-state compact-empty">该节点帖子数较少，暂未收录详细数据。</p>
    </article>
  </section>
</template>
