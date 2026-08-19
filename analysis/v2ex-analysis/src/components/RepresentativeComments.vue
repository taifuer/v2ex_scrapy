<script setup lang="ts">
import { computed, ref, watch } from "vue"
import type { RepresentativeComment, RepresentativeCommentSummary } from "../types/analytics"
import { formatCommentContent, formatDateTime, formatNumber } from "../utils/format"
import { paginationItems } from "../utils/pagination"

const props = withDefaults(defineProps<{
  comments?: RepresentativeComment[]
  summary?: RepresentativeCommentSummary
  title?: string
  emptyText?: string
  loading?: boolean
  error?: string
  period?: string
  description?: string
}>(), {
  comments: () => [],
  summary: () => ({}),
  title: "代表评论",
  emptyText: "相关帖子暂无至少获得 3 次感谢的代表评论。",
  loading: false,
  error: "",
  period: "",
  description: "",
})

const page = ref(1)
const pageSize = 10
const pageCount = computed(() => Math.max(1, Math.ceil(props.comments.length / pageSize)))
const pages = computed(() => paginationItems(page.value, pageCount.value))
const displayed = computed(() => props.comments.slice(
  (page.value - 1) * pageSize,
  page.value * pageSize,
))
const description = computed(() => {
  if (props.description) return props.description
  const thanked = Number(props.summary.thanked_comments || 0)
  const thanks = Number(props.summary.comment_thanks || 0)
  const scope = props.period ? `${props.period} 发布的相关帖子` : "全部历史相关帖子"
  if (!thanked) return `按累计感谢数展示${scope}中至少获得 3 次感谢的评论。`
  return `${scope}中有 ${formatNumber(thanked)} 条评论至少获得 3 次感谢，累计 ${formatNumber(thanks)} 次；这里展示 Top ${formatNumber(props.comments.length)}。`
})

watch(() => props.comments, () => { page.value = 1 })
watch(pageCount, count => {
  if (page.value > count) page.value = count
})
</script>

<template>
  <section class="entity-representative-comments">
    <header class="content-section-header">
      <div><h3>{{ title }}</h3><p>{{ description }}</p></div>
    </header>
    <div v-if="loading" class="loading compact-loading"><span class="loading-spinner"></span></div>
    <p v-else-if="error" class="empty-state compact-empty">{{ error }}</p>
    <div v-else class="comment-ranking-list entity-comment-list">
      <a
        v-for="(comment, index) in displayed"
        :key="comment.id"
        class="comment-ranking-row"
        :href="`https://www.v2ex.com/t/${comment.topic_id}#r_${comment.id}`"
        target="_blank"
        rel="noreferrer"
      >
        <span class="comment-rank">{{ (page - 1) * pageSize + index + 1 }}</span>
        <span class="comment-ranking-main">
          <strong>{{ formatCommentContent(comment.content) }}</strong>
          <small>{{ formatDateTime(comment.create_at) }} · {{ comment.commenter }} · {{ comment.topic_title }} · #{{ comment.no }}</small>
        </span>
        <em>{{ formatNumber(comment.thank_count) }} 感谢</em>
      </a>
      <p v-if="!comments.length" class="empty-state compact-empty">{{ emptyText }}</p>
    </div>
    <footer v-if="!loading && !error && comments.length > pageSize" class="ranking-pagination detail-pagination">
      <span>共 {{ formatNumber(comments.length) }} 条 · 第 {{ page }} / {{ pageCount }} 页</span>
      <nav :aria-label="`${title}分页`">
        <button class="pagination-arrow" aria-label="上一页" title="上一页" :disabled="page <= 1" @click="page--">‹</button>
        <template v-for="item in pages" :key="item">
          <button v-if="typeof item === 'number'" class="pagination-number" :class="{ active: item === page }" :aria-current="item === page ? 'page' : undefined" @click="page = item">{{ item }}</button>
          <span v-else class="pagination-gap" aria-hidden="true">…</span>
        </template>
        <button class="pagination-arrow" aria-label="下一页" title="下一页" :disabled="page >= pageCount" @click="page++">›</button>
      </nav>
    </footer>
  </section>
</template>
