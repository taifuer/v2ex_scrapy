<script setup lang="ts">
import { Bookmark, Heart, MessageCircle } from "@lucide/vue"
import { formatKnownNumber } from "../utils/format"
import type { PresentationPost } from "../types/presentation"

defineProps<{
  posts: PresentationPost[]
  nodeLabel: (node: string) => string
}>()
</script>

<template>
  <div class="deck-case-list" :style="{ '--case-count': posts.length }">
    <article v-for="post in posts" :key="post.id" class="deck-case">
      <header><span>{{ post.badge }}</span><time>{{ post.date }}</time></header>
      <h3><a :href="post.url" :title="post.title" target="_blank" rel="noreferrer">{{ post.title }}</a></h3>
      <blockquote v-if="post.excerpt">{{ post.excerpt }}</blockquote>
      <p v-if="post.note">{{ post.note }}</p>
      <footer>
        <small>{{ nodeLabel(post.node).split(" · ")[0] }} · #{{ post.id }}</small>
        <dl>
          <div><dt><Bookmark :size="14" /><span>收藏</span></dt><dd>{{ formatKnownNumber(post.favorites ?? undefined) }}</dd></div>
          <div><dt><Heart :size="14" /><span>感谢</span></dt><dd>{{ formatKnownNumber(post.thanks ?? undefined) }}</dd></div>
          <div><dt><MessageCircle :size="14" /><span>回复</span></dt><dd>{{ formatKnownNumber(post.replies ?? undefined) }}</dd></div>
        </dl>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.deck-case-list { display: grid; grid-template-columns: repeat(var(--case-count), minmax(0, 1fr)); align-items: stretch; gap: 18px; }
.deck-case { display: flex; min-width: 0; flex-direction: column; border: 1px solid var(--line); border-radius: 6px; background: #fff; padding: 22px; }
.deck-case header { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 6px 12px; font-size: 12px; }
.deck-case header span { color: var(--green); font-weight: 650; }
.deck-case time { color: var(--muted); font-variant-numeric: tabular-nums; }
.deck-case h3 { margin: 12px 0; color: var(--ink); font-size: 19px; font-weight: 650; line-height: 1.6; overflow-wrap: anywhere; }
.deck-case h3 a { color: inherit; text-decoration: none; text-underline-offset: 4px; }
.deck-case h3 a:hover { color: var(--blue); text-decoration: underline; }
.deck-case blockquote { margin: 0 0 12px; color: #344054; font-size: 16px; line-height: 1.8; overflow-wrap: anywhere; }
.deck-case blockquote::before { content: "\201c"; }
.deck-case blockquote::after { content: "\201d"; }
.deck-case p { margin: 0 0 18px; color: var(--muted); font-size: 14px; line-height: 1.7; overflow-wrap: anywhere; }
.deck-case footer { display: grid; gap: 10px; margin-top: auto; padding-top: 16px; }
.deck-case footer small { color: var(--muted); font-size: 12px; }
.deck-case dl { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 0; }
.deck-case dl > div, .deck-case dt { display: inline-flex; align-items: center; gap: 4px; }
.deck-case dt { color: var(--muted); font-size: 12px; }
.deck-case dd { margin: 0; font-size: 13px; font-weight: 650; font-variant-numeric: tabular-nums; }
@media (max-width: 680px) {
  .deck-case-list { grid-template-columns: 1fr; gap: 14px; }
  .deck-case { padding: 18px; }
  .deck-case h3 { font-size: 17px; }
  .deck-case blockquote { font-size: 15px; }
}
</style>
