<script setup lang="ts">
type AggregateItem = {
  key: string
  label: string
  count: number
  clickable?: boolean
  action?: string
  hint?: string
}

type AggregateCard = {
  id: string
  label: string
  description: string
  count: number
  share: number
  shareDelta: number | null
  coverage?: number
  items: AggregateItem[]
}

withDefaults(defineProps<{
  cards: AggregateCard[]
  countLabel: string
  itemLabel: string
  emptyText?: string
  embedded?: boolean
}>(), {
  emptyText: "暂无达到门槛的项目",
  embedded: false,
})

const emit = defineEmits<{
  select: [key: string, action?: string]
}>()

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-CN").format(Math.round(value || 0))
}
</script>

<template>
  <div class="aggregate-group-list" :class="{ embedded }">
    <article v-for="card in cards" :key="card.id" class="aggregate-group-card">
      <div class="aggregate-group-summary">
        <header>
          <h3>{{ card.label }}</h3>
          <span class="aggregate-group-total"><strong>{{ formatNumber(card.count) }}</strong><small>{{ countLabel }}</small></span>
        </header>
        <p>{{ card.description }}</p>
        <div class="aggregate-group-metrics">
          <span>占全部帖子 <strong>{{ card.share.toFixed(2) }}%</strong></span>
          <span v-if="card.shareDelta !== null" :class="card.shareDelta >= 0 ? 'group-rise' : 'group-fall'">
            近 12 月 <strong>{{ card.shareDelta >= 0 ? '+' : '' }}{{ card.shareDelta.toFixed(2) }}pp</strong>
          </span>
          <span v-else>近 12 月 <strong>基期不足</strong></span>
          <span v-if="card.coverage !== undefined" title="至少命中一个原始话题的板块帖子占比">
            话题覆盖 <strong>{{ card.coverage.toFixed(1) }}%</strong>
          </span>
        </div>
      </div>
      <div class="aggregate-group-items">
        <span class="aggregate-group-label">{{ itemLabel }}</span>
        <div>
          <template v-for="item in card.items" :key="item.key">
            <button v-if="item.clickable !== false" type="button" :title="item.hint" @click="emit('select', item.key, item.action)">{{ item.label }} <small>{{ formatNumber(item.count) }}</small></button>
            <span v-else class="aggregate-group-static" :title="item.hint">{{ item.label }} <small>{{ formatNumber(item.count) }}</small></span>
          </template>
          <span v-if="!card.items.length" class="aggregate-group-empty">{{ emptyText }}</span>
        </div>
      </div>
    </article>
  </div>
</template>

<style scoped>
.aggregate-group-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 12px; }
.aggregate-group-card { display: flex; min-width: 0; flex-direction: column; gap: 14px; border: 1px solid var(--line); border-radius: 8px; background: #fff; box-shadow: var(--shadow-sm); padding: 17px 18px; }
.aggregate-group-summary { min-width: 0; }
.aggregate-group-summary > header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.aggregate-group-summary h3 { margin: 0; font-size: 15px; }
.aggregate-group-summary > p { margin: 5px 0 0; color: var(--muted); font-size: 11px; line-height: 1.55; }
.aggregate-group-total { flex: 0 0 auto; text-align: right; }
.aggregate-group-total strong, .aggregate-group-total small { display: block; }
.aggregate-group-total strong { font-size: 17px; font-variant-numeric: tabular-nums; line-height: 1; }
.aggregate-group-total small { margin-top: 4px; color: var(--muted); font-size: 9px; font-weight: 500; }
.aggregate-group-metrics { display: flex; flex-wrap: wrap; gap: 5px 14px; margin-top: 10px; color: var(--muted); font-size: 10px; }
.aggregate-group-metrics strong { color: #344054; font-variant-numeric: tabular-nums; }
.aggregate-group-metrics .group-rise strong { color: var(--green); }
.aggregate-group-metrics .group-fall strong { color: var(--accent); }
.aggregate-group-items { min-width: 0; }
.aggregate-group-label { display: block; margin-bottom: 8px; color: #667085; font-size: 10px; font-weight: 650; }
.aggregate-group-items > div { display: flex; align-content: flex-start; flex-wrap: wrap; gap: 6px; }
.aggregate-group-items button, .aggregate-group-items > div > span { display: inline-flex; min-height: 27px; align-items: center; gap: 5px; border: 1px solid #d9dee7; border-radius: 5px; background: #f8fafc; color: #344054; padding: 4px 7px; font-size: 11px; line-height: 1.3; }
.aggregate-group-items button:hover { border-color: #98a2b3; background: #fff; color: var(--accent); }
.aggregate-group-items button { cursor: pointer; }
.aggregate-group-items > div > span.aggregate-group-static { border-color: #e7eaf0; background: #fafbfc; color: #667085; }
.aggregate-group-items small { color: var(--muted); font-size: 9px; font-variant-numeric: tabular-nums; }
.aggregate-group-items .aggregate-group-empty { border-style: dashed; color: var(--muted); }
.aggregate-group-list.embedded { align-items: stretch; gap: 0; }
.aggregate-group-list.embedded .aggregate-group-card { border: 0; border-bottom: 1px solid #edf0f3; border-radius: 0; background: transparent; box-shadow: none; padding: 18px 18px 18px 0; }
.aggregate-group-list.embedded .aggregate-group-card:nth-child(even) { border-left: 1px solid #edf0f3; padding-right: 0; padding-left: 18px; }
.aggregate-group-list.embedded .aggregate-group-card:nth-last-child(-n+2) { border-bottom: 0; }
@media (max-width: 860px) {
  .aggregate-group-list { grid-template-columns: 1fr; }
  .aggregate-group-list.embedded .aggregate-group-card,
  .aggregate-group-list.embedded .aggregate-group-card:nth-child(even) { border-left: 0; border-bottom: 1px solid #edf0f3; padding-right: 0; padding-left: 0; }
  .aggregate-group-list.embedded .aggregate-group-card:last-child { border-bottom: 0; }
}
@media (max-width: 680px) {
  .aggregate-group-card { gap: 13px; padding: 15px 14px; }
  .aggregate-group-summary > header { align-items: center; }
  .aggregate-group-total { display: flex; align-items: baseline; gap: 5px; }
  .aggregate-group-total small { margin-top: 0; }
}
</style>
