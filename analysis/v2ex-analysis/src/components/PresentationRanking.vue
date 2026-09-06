<script setup lang="ts">
import { computed } from "vue"
import { formatKnownNumber } from "../utils/format"
import type { PresentationSlide } from "../types/presentation"

const props = defineProps<{
  posts?: PresentationSlide["posts"]
  comments?: PresentationSlide["comments"]
  nodeLabel: (node: string) => string
}>()
const ranked = computed(() => Boolean(props.comments || props.posts?.[0]?.rank))
const metrics = [
  { key: "favorites", label: "收藏" },
  { key: "thanks", label: "感谢" },
  { key: "replies", label: "回复" },
] as const
const items = computed(() => props.comments?.map(comment => ({
  ...comment, title: comment.topic_title || "相关帖子", badge: comment.label, quote: comment.text,
  value: comment.thanks, metric: "感谢", context: comment.username, topicId: comment.topic_id, favorites: null, replies: null,
})) ?? props.posts?.map(post => ({
  ...post, quote: post.rank ? "" : post.excerpt, value: post.ranking_metric ? post[post.ranking_metric] : null,
  metric: post.ranking_metric === "favorites" ? "收藏" : "感谢",
  context: props.nodeLabel(post.node).split(" · ")[0], topicId: post.id,
})) ?? [])
</script>

<template>
  <div class="deck-ranking" :class="{ 'deck-ranking-single': !ranked }">
    <article v-for="item in items" :key="item.id" class="deck-ranking-item deck-case">
      <div class="deck-ranking-content">
        <header><span>{{ item.badge }}</span><time>{{ item.date }}</time></header>
        <h3><a :href="item.url" target="_blank" rel="noreferrer">{{ item.title }}</a></h3>
        <blockquote v-if="item.quote">{{ item.quote }}</blockquote>
      </div>
      <p class="deck-ranking-note">{{ item.note }}</p>
      <footer>
        <strong v-if="ranked" class="deck-rank-value">{{ formatKnownNumber(item.value ?? undefined) }}<span>{{ item.metric }}</span></strong>
        <small>{{ item.context }} · #{{ item.topicId }}</small>
        <dl v-if="!ranked">
          <div v-for="metric in metrics" :key="metric.key"><dt>{{ metric.label }}</dt><dd>{{ formatKnownNumber(item[metric.key] ?? undefined) }}</dd></div>
        </dl>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.deck-ranking { display: grid; flex: 0 0 auto; gap: 16px; min-width: 0; }
.deck-ranking-item { display: grid; grid-template-columns: minmax(0, 1.45fr) minmax(0, 1fr) 140px; align-items: start; gap: 24px; border: 1px solid var(--line); border-radius: 6px; background: #fff; padding: 16px; }
.deck-ranking-content { min-width: 0; }
header { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 6px 12px; font-size: 12px; }
header span { color: var(--green); font-weight: 650; }
time, small { color: var(--muted); font-variant-numeric: tabular-nums; }
h3 { margin: 8px 0 0; color: var(--ink); font-size: 18px; font-weight: 650; line-height: 1.5; overflow-wrap: anywhere; }
h3 a { color: inherit; text-decoration: none; text-underline-offset: 4px; }
h3 a:hover { color: var(--blue); text-decoration: underline; }
blockquote { margin: 8px 0 0; color: #344054; font-size: 15px; line-height: 1.5; overflow-wrap: anywhere; }
.deck-ranking-note { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.65; overflow-wrap: anywhere; }
footer { display: grid; gap: 10px; min-width: 0; }
small { font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.deck-rank-value { display: flex; align-items: baseline; gap: 6px; color: #245899; font-size: 24px; font-variant-numeric: tabular-nums; }
.deck-rank-value span { color: var(--muted); font-size: 13px; font-weight: 500; }
.deck-ranking-single .deck-ranking-item { display: flex; flex-direction: column; gap: 12px; }
.deck-ranking-single footer { display: grid; }
dl { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 0; }
dl > div, dt { display: inline-flex; align-items: center; gap: 4px; }
dt { color: var(--muted); font-size: 12px; }
dd { margin: 0; font-size: 13px; font-weight: 650; font-variant-numeric: tabular-nums; }
@container (min-width: 1000px) and (min-height: 650px) {
  .deck-ranking-item { padding: 24px; gap: 28px; }
  h3 { font-size: 20px; }
  header, small { font-size: 14px; }
  blockquote { font-size: 17px; }
  .deck-ranking-note { font-size: 16px; }
}
@container (min-width: 901px) and (max-height: 450px) {
  .deck-ranking { gap: 12px; }
  .deck-ranking-item { padding: 10px 14px; gap: 20px; }
  h3 { font-size: 17px; margin-top: 6px; }
  blockquote { font-size: 14px; margin-top: 6px; }
  .deck-ranking-note { font-size: 13px; }
}
@media (max-width: 900px) {
  .deck-ranking-item { grid-template-columns: minmax(0, 1fr); gap: 12px; padding: 14px; }
  h3 { font-size: 17px; }
  footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  small { text-align: right; }
  .deck-rank-value { flex: 0 0 auto; }
}
</style>
