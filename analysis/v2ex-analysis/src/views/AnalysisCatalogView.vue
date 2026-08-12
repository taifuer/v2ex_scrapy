<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import { Search } from "@lucide/vue"
import PageHeader from "../components/PageHeader.vue"
import PeriodSelect from "../components/PeriodSelect.vue"
import { getJson } from "../services/dataClient"

type CatalogType = "topics" | "content" | "nodes"
type CatalogSort = "count" | "name"
type CatalogCounts = { topics: number; content: number; nodes: number }
type CatalogEntityType = "tag" | "term" | "node"
type CatalogGroup = { id: string; label: string; items: string[] }
type CatalogEntry = {
  type: CatalogEntityType
  value: string
  label: string
  total: number
  groups: string[]
  note?: string
}

const props = defineProps<{
  type: CatalogType
  sort: CatalogSort
  group: string
  counts: CatalogCounts
  nodeLabel: (node: string) => string
}>()
const emit = defineEmits<{
  "update:type": [type: CatalogType]
  "update:sort": [sort: CatalogSort]
  "update:group": [group: string]
  select: [result: { type: CatalogEntityType; value: string }]
}>()

const query = ref("")
const mobileBatchSize = 60
const isMobile = ref(typeof window !== "undefined" && window.matchMedia("(max-width: 680px)").matches)
const visibleLimit = ref(mobileBatchSize)
const loading = ref(false)
const error = ref("")
const tagIndex = shallowRef<any>(null)
const topicGroups = shallowRef<any>(null)
const contentIndex = shallowRef<any>(null)
const nodeIndex = shallowRef<any>(null)
const requests = new Map<CatalogType, Promise<void>>()
let activeLoadId = 0
let mobileMedia: MediaQueryList | null = null
const collator = new Intl.Collator(["zh-CN-u-co-pinyin", "zh-CN"], {
  sensitivity: "base",
  numeric: true,
})

const typeDefinitions = [
  { id: "topics" as const, label: "话题" },
  { id: "content" as const, label: "标题关键词" },
  { id: "nodes" as const, label: "节点" },
]

const typeLabels: Record<CatalogType, string> = {
  topics: "话题",
  content: "标题关键词",
  nodes: "节点",
}

const countLabels: Record<CatalogType, string> = {
  topics: "帖子",
  content: "相关标题",
  nodes: "帖子",
}
const countUnits: Record<CatalogType, string> = {
  topics: "帖子",
  content: "标题",
  nodes: "帖子",
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("zh-CN")
}

function normalize(value: string) {
  return value.trim().toLocaleLowerCase("zh-CN")
}

function loaded(type: CatalogType) {
  if (type === "topics") return Boolean(tagIndex.value && topicGroups.value)
  if (type === "content") return Boolean(contentIndex.value)
  return Boolean(nodeIndex.value)
}

async function loadType(type: CatalogType) {
  const loadId = ++activeLoadId
  if (loaded(type)) {
    loading.value = false
    error.value = ""
    return
  }
  let request = requests.get(type)
  if (!request) {
    request = (async () => {
      if (type === "topics") {
        const [indexPayload, groupPayload] = await Promise.all([
          getJson("dynamic-tag-detail-index.json"),
          getJson("dynamic-topics.json"),
        ])
        tagIndex.value = indexPayload
        topicGroups.value = groupPayload
      } else if (type === "content") {
        contentIndex.value = await getJson("dynamic-content-hotspots-index.json")
      } else {
        nodeIndex.value = await getJson("dynamic-node-detail-index.json")
      }
    })().finally(() => requests.delete(type))
    requests.set(type, request)
  }
  loading.value = true
  error.value = ""
  try {
    await request
  } catch (cause) {
    if (loadId === activeLoadId) {
      error.value = cause instanceof Error ? cause.message : "数据索引加载失败"
    }
  } finally {
    if (loadId === activeLoadId) loading.value = false
  }
}

const groups = computed<CatalogGroup[]>(() => {
  if (props.type === "topics") {
    return (topicGroups.value?.groups || []).map((group: any) => ({
      id: String(group.name),
      label: String(group.label),
      items: (group.topics || []).map(String),
    }))
  }
  if (props.type === "content") {
    return (contentIndex.value?.content_groups || []).map((group: any) => ({
      id: String(group.id),
      label: String(group.label),
      items: (group.terms || []).map(String),
    }))
  }
  return []
})
const groupOptions = computed(() => ["", ...groups.value.map(group => group.id)])
const groupOptionLabels = computed(() => Object.fromEntries([
  ["", "全部板块"],
  ...groups.value.map(group => [group.id, group.label]),
]))

const itemGroups = computed(() => {
  const result = new Map<string, string[]>()
  for (const group of groups.value) {
    for (const item of group.items) {
      const key = normalize(item)
      const values = result.get(key) || []
      if (!values.includes(group.id)) values.push(group.id)
      result.set(key, values)
    }
  }
  return result
})

const entries = computed<CatalogEntry[]>(() => {
  if (props.type === "topics") {
    return Object.entries(tagIndex.value?.tags || {}).map(([value, rawEntry]) => ({
      type: "tag",
      value,
      label: value,
      total: Number((rawEntry as any).total || 0),
      groups: itemGroups.value.get(normalize(value)) || [],
    }))
  }
  if (props.type === "content") {
    return Object.entries(contentIndex.value?.terms || {}).map(([value, rawEntry]) => {
      const entry = rawEntry as any
      const note = entry.family
        ? `属于 ${entry.family} 关键词组`
        : entry.family_members?.length ? `聚合 ${entry.family_members.length} 个相关关键词` : ""
      return {
        type: "term",
        value,
        label: value,
        total: Number(entry.total || 0),
        groups: itemGroups.value.get(normalize(entry.family || value)) || [],
        note,
      }
    })
  }
  return Object.entries(nodeIndex.value?.nodes || {}).map(([value, rawEntry]) => ({
    type: "node",
    value,
    label: props.nodeLabel(value),
    total: Number((rawEntry as any).total || 0),
    groups: [],
  }))
})

const filteredEntries = computed(() => {
  const needle = normalize(query.value)
  return entries.value
    .filter(entry => !needle || normalize(`${entry.label} ${entry.value}`).includes(needle))
    .filter(entry => !props.group || entry.groups.includes(props.group))
    .sort((left, right) => props.sort === "count"
      ? right.total - left.total || collator.compare(left.label, right.label)
      : collator.compare(left.label, right.label) || right.total - left.total)
})
const displayedEntries = computed(() => isMobile.value
  ? filteredEntries.value.slice(0, visibleLimit.value)
  : filteredEntries.value)
const remainingEntries = computed(() => Math.max(0, filteredEntries.value.length - displayedEntries.value.length))

function selectType(type: CatalogType) {
  query.value = ""
  emit("update:type", type)
  emit("update:group", "")
}

function selectSort(sort: CatalogSort) {
  emit("update:sort", sort)
}

function selectGroup(group: string) {
  emit("update:group", group)
}

function resetVisibleLimit() {
  visibleLimit.value = mobileBatchSize
}

function updateMobileState() {
  isMobile.value = Boolean(mobileMedia?.matches)
  resetVisibleLimit()
}

function showMore() {
  visibleLimit.value += mobileBatchSize
}

watch(() => props.type, type => { void loadType(type) })
watch(() => [props.type, props.sort, props.group, query.value], resetVisibleLimit)
watch(groups, current => {
  if (props.group && !current.some(group => group.id === props.group)) emit("update:group", "")
})

onMounted(() => {
  mobileMedia = window.matchMedia("(max-width: 680px)")
  mobileMedia.addEventListener("change", updateMobileState)
  updateMobileState()
  void loadType(props.type)
})
onBeforeUnmount(() => mobileMedia?.removeEventListener("change", updateMobileState))
</script>

<template>
  <section class="view-section analysis-catalog-view">
    <PageHeader title="数据索引" description="浏览看板已收录并提供详情的话题、标题关键词和节点；点击条目即可查看详情。" />
    <article class="analysis-block full catalog-panel">
      <header class="catalog-header">
        <div>
          <h2>收录数据</h2>
          <p>默认按相关帖子数排序；按名称排序时采用适合中英文混排的顺序。</p>
        </div>
        <nav class="catalog-type-tabs segmented compact-segmented" aria-label="数据索引类型">
          <button
            v-for="item in typeDefinitions"
            :key="item.id"
            type="button"
            :class="{ active: type === item.id }"
            :aria-pressed="type === item.id"
            @click="selectType(item.id)"
          >
            <span>{{ item.label }}</span>
            <small>{{ formatNumber(counts[item.id]) }}</small>
          </button>
        </nav>
      </header>

      <div class="catalog-toolbar">
        <PeriodSelect
          v-if="type !== 'nodes'"
          class="catalog-group-filter"
          :model-value="group"
          label="相关板块"
          :periods="groupOptions"
          :option-labels="groupOptionLabels"
          :latest-first="false"
          icon="tag"
          @update:model-value="selectGroup"
        />
        <div class="catalog-sort">
          <span>排序</span>
          <div class="segmented compact-segmented" aria-label="数据索引排序方式">
            <button :class="{ active: sort === 'count' }" @click="selectSort('count')">数量</button>
            <button :class="{ active: sort === 'name' }" @click="selectSort('name')">名称</button>
          </div>
        </div>
        <label class="catalog-search">
          <span class="sr-only">搜索{{ typeLabels[type] }}</span>
          <Search :size="17" aria-hidden="true" />
          <input v-model="query" type="search" :placeholder="`搜索${typeLabels[type]}名称`" />
        </label>
      </div>

      <p class="catalog-scope">
        当前显示 {{ formatNumber(filteredEntries.length) }} 个{{ typeLabels[type] }}，右侧为{{ countLabels[type] }}数。板块可以交叉，不代表互斥分类；这里只展示看板已提供详情的项目。
      </p>

      <div v-if="loading" class="loading compact-loading"><span class="loading-spinner"></span></div>
      <p v-else-if="error" class="empty-state compact-empty">{{ error }}</p>
      <div v-else class="catalog-list">
        <button
          v-for="(entry, index) in displayedEntries"
          :key="`${entry.type}:${entry.value}`"
          type="button"
          class="ranked-item catalog-entry"
          :title="entry.note ? `打开${typeLabels[type]}详情：${entry.label}；${entry.note}` : `打开${typeLabels[type]}详情：${entry.label}`"
          @click="emit('select', { type: entry.type, value: entry.value })"
        >
          <span>{{ index + 1 }}</span>
          <strong>{{ entry.label }}</strong>
          <em>{{ formatNumber(entry.total) }} {{ countUnits[type] }}</em>
        </button>
        <p v-if="!filteredEntries.length" class="empty-state compact-empty">没有符合当前条件的{{ typeLabels[type] }}。</p>
      </div>
      <button v-if="isMobile && remainingEntries" type="button" class="catalog-load-more" @click="showMore">
        继续显示 {{ formatNumber(Math.min(mobileBatchSize, remainingEntries)) }} 项
        <small>剩余 {{ formatNumber(remainingEntries) }} 项</small>
      </button>
    </article>
  </section>
</template>
