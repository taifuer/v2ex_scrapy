<script setup lang="ts">
import { onMounted } from "vue"
import ViewSectionNav from "../components/ViewSectionNav.vue"
import type { PaginationItem } from "../types/analytics"

defineProps<{
  summary: any
  engagement: any
  interactionRanking: string
  displayedPosts: any[]
  displayedComments: any[]
  postPage: number
  commentPage: number
  postPageCount: number
  commentPageCount: number
  postPaginationItems: PaginationItem[]
  commentPaginationItems: PaginationItem[]
  rankingPageSize: number
  topPostsLength: number
}>()
const emit = defineEmits<{
  "update:interactionRanking": [value: "favorite_count" | "thank_count" | "votes" | "clicks"]
  "update:postPage": [value: number]
  "update:commentPage": [value: number]
  ready: []
}>()
onMounted(() => emit("ready"))

function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}
function displayIndex(index: number) { return index + 1 }
function formatDateTime(timestamp: number | undefined) {
  if (!timestamp) return "时间未知"
  const formatter = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  })
  return formatter.format(new Date(timestamp * 1000)).replace(/\//g, "-")
}
</script>

<template>
  <section class="view-section">
    <div class="section-toolbar">
      <div><h2>互动</h2><p>比较不同发布时期内容最终积累的点击、收藏、感谢与投票。</p></div>
    </div>
    <div class="metric-grid five">
      <article class="metric"><span>点击</span><strong>{{ formatNumber(summary.clicks) }}</strong><em>主题累计快照</em></article>
      <article class="metric"><span>收藏</span><strong>{{ formatNumber(summary.favorites) }}</strong><em>{{ formatNumber(summary.favoriteRate, 2) }}/千次点击</em></article>
      <article class="metric"><span>主题感谢</span><strong>{{ formatNumber(summary.topicThanks) }}</strong><em>{{ formatNumber(summary.topicThankRate, 2) }}/千次回复</em></article>
      <article class="metric"><span>投票</span><strong>{{ formatNumber(summary.votes) }}</strong><em>{{ formatNumber(summary.voteRate, 1) }}/千主题</em></article>
      <article class="metric"><span>评论感谢</span><strong>{{ formatNumber(summary.commentThanks) }}</strong><em>按评论发布期归入</em></article>
    </div>
    <ViewSectionNav :items="[
      { id: 'engagement-trends', label: '互动趋势' },
      { id: 'engagement-posts', label: '热门帖子' },
      { id: 'engagement-comments', label: '热门评论' },
    ]" />
    <div class="chart-grid two">
      <article id="engagement-trends" class="analysis-block section-anchor">
        <header><h2>互动规模变化</h2><p>主题互动按主题发布期归入，评论感谢按评论发布期归入。</p></header>
        <div id="engagement-volume" class="chart"></div>
      </article>
      <article class="analysis-block">
        <header><h2>互动效率变化</h2><p>使用点击、回复和主题数标准化，降低社区规模变化的影响。</p></header>
        <div id="engagement-efficiency" class="chart"></div>
      </article>
    </div>
    <article id="engagement-posts" class="leader-board interaction-ranking section-anchor">
      <header class="ranking-header">
        <div><h2>热门帖子</h2><p>按当前累计互动指标展示 Top 200，不受上方时间筛选影响。</p></div>
        <div class="control-group interaction-metric-control">
          <span>排序指标</span>
          <div class="segmented compact-segmented" aria-label="热门帖子排序指标">
            <button :class="{ active: interactionRanking === 'favorite_count' }" @click="emit('update:interactionRanking', 'favorite_count')">收藏</button>
            <button :class="{ active: interactionRanking === 'thank_count' }" @click="emit('update:interactionRanking', 'thank_count')">感谢</button>
            <button :class="{ active: interactionRanking === 'votes' }" @click="emit('update:interactionRanking', 'votes')">投票</button>
            <button :class="{ active: interactionRanking === 'clicks' }" @click="emit('update:interactionRanking', 'clicks')">点击</button>
          </div>
        </div>
      </header>
      <div class="content-list interaction-post-list">
        <a v-for="(post, index) in displayedPosts" :key="post.id" class="content-list-row" :href="`https://www.v2ex.com/t/${post.id}`" target="_blank" rel="noreferrer">
          <span class="content-list-rank">{{ (postPage - 1) * rankingPageSize + displayIndex(index) }}</span>
          <span class="content-list-main"><strong>{{ post.title }}</strong><small>{{ formatDateTime(post.create_at) }} · {{ post.node_label }} · #{{ post.id }}</small></span>
          <em class="content-list-value">{{ formatNumber(post.value) }}</em>
        </a>
      </div>
      <footer class="ranking-pagination">
        <span>Top {{ formatNumber(topPostsLength) }} · 第 {{ postPage }} / {{ postPageCount }} 页</span>
        <nav aria-label="热门帖子分页">
          <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="postPage <= 1" @click="emit('update:postPage', postPage - 1)">‹</button>
          <template v-for="item in postPaginationItems" :key="item">
            <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === postPage }" :aria-current="item === postPage ? 'page' : undefined" @click="emit('update:postPage', item)">{{ item }}</button>
            <span v-else class="pagination-gap" aria-hidden="true">…</span>
          </template>
          <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="postPage >= postPageCount" @click="emit('update:postPage', postPage + 1)">›</button>
        </nav>
      </footer>
    </article>
    <article id="engagement-comments" class="leader-board interaction-ranking section-anchor">
      <header><h2>热门评论</h2><p>按累计感谢数展示 Top 500，点击可跳转至原主题评论位置。</p></header>
      <div class="comment-ranking-list">
        <a v-for="(comment, index) in displayedComments" :key="comment.id" class="comment-ranking-row" :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`" target="_blank" rel="noreferrer">
          <span class="comment-rank">{{ (commentPage - 1) * rankingPageSize + displayIndex(index) }}</span>
          <span class="comment-ranking-main"><strong>{{ comment.content || "评论原文未收录" }}</strong><small>{{ formatDateTime(comment.create_at) }} · {{ comment.commenter }} · {{ comment.topic_title }} · #{{ comment.no }}</small></span>
          <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
        </a>
      </div>
      <footer class="ranking-pagination">
        <span>Top {{ formatNumber(engagement.top_comments.length) }} · 第 {{ commentPage }} / {{ commentPageCount }} 页</span>
        <nav aria-label="热门评论分页">
          <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="commentPage <= 1" @click="emit('update:commentPage', commentPage - 1)">‹</button>
          <template v-for="item in commentPaginationItems" :key="item">
            <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === commentPage }" :aria-current="item === commentPage ? 'page' : undefined" @click="emit('update:commentPage', item)">{{ item }}</button>
            <span v-else class="pagination-gap" aria-hidden="true">…</span>
          </template>
          <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="commentPage >= commentPageCount" @click="emit('update:commentPage', commentPage + 1)">›</button>
        </nav>
      </footer>
    </article>
    <p class="method-note">账号 usdc 的评论感谢值明显异常，已从“热门评论”榜单排除；全站汇总与趋势仍保留数据库原始值。</p>
    <p class="method-note">V2EX 未提供收藏、感谢和投票的发生时间。这里展示的是按内容发布时间分组的当前累计值，不能解释为对应月份实际发生的互动；原始值为 -1 的未知互动按 0 处理。</p>
  </section>
</template>
