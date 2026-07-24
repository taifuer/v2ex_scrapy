<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import SearchSelect from "../components/SearchSelect.vue"
import RankedColumns from "../components/RankedColumns.vue"
import { paginationItems } from "../utils/pagination"
import type { RankedColumn, RankedItem, RepresentativePost, SearchOption } from "../types/analytics"

const props = defineProps<{
  node: string
  loading: boolean
  detail: any
  summary: any
  options: SearchOption[]
  columns: RankedColumn[]
  label: string
}>()
const emit = defineEmits<{
  "update:node": [node: string]
  select: [item: RankedItem]
  topic: [tag: string]
  member: [username: string]
  ready: []
}>()
const pageSize = 10
const postPage = ref(1)
const postCount = computed(() => props.detail?.posts?.length || 0)
const postPageCount = computed(() => Math.max(1, Math.ceil(postCount.value / pageSize)))
const postPaginationItems = computed(() => paginationItems(postPage.value, postPageCount.value))
const posts = computed<RepresentativePost[]>(() => (props.detail?.posts || []).slice(
  (postPage.value - 1) * pageSize,
  postPage.value * pageSize,
))
watch(() => props.node, () => { postPage.value = 1 })
watch(postPageCount, (count) => {
  if (postPage.value > count) postPage.value = count
})
onMounted(() => emit("ready"))

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}

function formatDateTime(timestamp: number | undefined) {
  if (!timestamp) return "时间未知"
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(new Date(timestamp * 1000)).replace(/\//g, "-")
}
</script>

<template>
  <section class="view-section">
    <article id="node-detail" class="analysis-block full node-detail-block">
      <header class="block-header-with-control">
        <div>
          <h2>节点详情：{{ label }}</h2>
          <p>展示当前筛选范围内的规模与趋势，并使用全历史主题汇总主要标签、活跃用户和代表帖子。</p>
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
          <a :href="`https://www.v2ex.com/go/${encodeURIComponent(node)}`" target="_blank" rel="noreferrer">节点链接</a>
        </div>
      </header>
      <div v-if="loading" class="loading compact-loading"><span class="loading-spinner"></span></div>
      <template v-else-if="detail && summary">
        <div class="metric-grid five node-detail-metrics">
          <article class="metric"><span>主题</span><strong>{{ formatNumber(summary.count) }}</strong><em>当前筛选范围</em></article>
          <article class="metric"><span>主题份额</span><strong>{{ summary.share.toFixed(2) }}%</strong><em>占有效主题</em></article>
          <article class="metric"><span>平均回复</span><strong>{{ formatNumber(summary.repliesPerTopic, 1) }}</strong><em>每个主题</em></article>
          <article class="metric"><span>平均点击</span><strong>{{ formatNumber(summary.clicksPerTopic) }}</strong><em>每个主题</em></article>
          <article class="metric"><span>活跃峰值</span><strong>{{ summary.peak }}</strong><em>主题量最高时期</em></article>
        </div>
        <section class="topic-detail-trend">
          <header><h3>{{ label }}趋势</h3><p>主题数使用左轴，平均回复使用右轴，并随全局日期范围和时间粒度变化。</p></header>
          <div id="node-detail-trend" class="chart compact-chart"></div>
        </section>
        <p class="topic-detail-scope-note">以下结构按全历史统计：该节点共 {{ formatNumber(detail.total) }} 个主题；标签和用户数量均为该节点内对应主题数。</p>
        <RankedColumns :columns="columns" @select="(item) => emit('select', item)" />
        <section class="topic-detail-posts node-detail-posts">
          <header class="content-section-header">
            <div><h3>代表帖子</h3><p>按回复、收藏、感谢、投票和点击构成的综合分选取全历史 Top 100。</p></div>
          </header>
          <div class="post-list">
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
            <p v-if="!detail.posts.length" class="empty-state compact-empty">该节点暂无代表帖子。</p>
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
      </template>
      <p v-else class="empty-state compact-empty">该节点主题量不足，暂未纳入节点详情。</p>
    </article>
  </section>
</template>
