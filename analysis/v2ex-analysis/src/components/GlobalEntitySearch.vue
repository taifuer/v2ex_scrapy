<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"
import { FileText, LoaderCircle, Network, Search, Tag, UserRound, X } from "@lucide/vue"
import { getJson } from "../services/dataClient"

type EntityType = "tag" | "term" | "node" | "member"
type EntityResult = {
  type: EntityType
  value: string
  label: string
  meta: string
  total: number
}
type SuggestionItem = { value: string; count: number }
type SuggestionPayload = {
  metadata?: { from_period?: string; to_period?: string }
  topics?: SuggestionItem[]
  content?: SuggestionItem[]
}

const props = defineProps<{ nodeLabel: (node: string) => string }>()
const emit = defineEmits<{ select: [result: EntityResult] }>()
const open = ref(false)
const loading = ref(false)
const loaded = ref(false)
const loadError = ref("")
const query = ref("")
const input = ref<HTMLInputElement | null>(null)
const activeIndex = ref(0)
const entities = ref<EntityResult[]>([])
const suggestions = ref<EntityResult[]>([])
const suggestionPeriod = ref("")

const typeLabels: Record<EntityType, string> = {
  tag: "话题",
  term: "内容",
  node: "节点",
  member: "成员",
}

const typeIcons = { tag: Tag, term: FileText, node: Network, member: UserRound }

const results = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase("zh-CN")
  if (!needle) return []
  return entities.value
    .filter(item => `${item.label} ${item.value}`.toLocaleLowerCase("zh-CN").includes(needle))
    .sort((a, b) => {
      const aLabel = a.label.toLocaleLowerCase("zh-CN")
      const bLabel = b.label.toLocaleLowerCase("zh-CN")
      const aExact = aLabel === needle ? 0 : aLabel.startsWith(needle) ? 1 : 2
      const bExact = bLabel === needle ? 0 : bLabel.startsWith(needle) ? 1 : 2
      return aExact - bExact || b.total - a.total || a.label.localeCompare(b.label, "zh-CN")
    })
    .slice(0, 40)
})
const visibleResults = computed(() => query.value.trim() ? results.value : suggestions.value)
const activeDescendant = computed(() => visibleResults.value[activeIndex.value]
  ? `global-search-option-${activeIndex.value}`
  : undefined)

watch(visibleResults, () => { activeIndex.value = 0 })
watch(open, value => {
  document.body.classList.toggle("dialog-open", value)
  if (value) nextTick(() => input.value?.focus())
})

async function loadEntities() {
  if (loaded.value || loading.value) return
  loading.value = true
  loadError.value = ""
  try {
    const [tagIndex, termIndex, nodeIndex, memberIndex, suggestionData] = await Promise.all([
      getJson("dynamic-tag-detail-index.json"),
      getJson("dynamic-content-hotspots-index.json"),
      getJson("dynamic-node-detail-index.json"),
      getJson("dynamic-member-profile-index.json"),
      getJson<SuggestionPayload>("dynamic-search-suggestions.json"),
    ])
    entities.value = [
      ...Object.entries(tagIndex.tags || {}).map(([value, entry]: [string, any]) => ({
        type: "tag" as const, value, label: value, total: Number(entry.total || 0), meta: `${Number(entry.total || 0).toLocaleString("zh-CN")} 帖子`,
      })),
      ...Object.entries(termIndex.terms || {}).map(([value, entry]: [string, any]) => ({
        type: "term" as const, value, label: value, total: Number(entry.total || 0), meta: `${Number(entry.total || 0).toLocaleString("zh-CN")} 个相关标题`,
      })),
      ...Object.entries(nodeIndex.nodes || {}).map(([value, entry]: [string, any]) => ({
        type: "node" as const, value, label: props.nodeLabel(value), total: Number(entry.total || 0), meta: `${value} · ${Number(entry.total || 0).toLocaleString("zh-CN")} 帖子`,
      })),
      ...Object.entries(memberIndex.members || {}).map(([value, entry]: [string, any]) => ({
        type: "member" as const, value, label: value, total: Number(entry.topics || 0) + Number(entry.comments || 0), meta: `${Number(entry.topics || 0).toLocaleString("zh-CN")} 帖子 · ${Number(entry.comments || 0).toLocaleString("zh-CN")} 评论`,
      })),
    ]
    suggestions.value = [
      ...(suggestionData.topics || []).map(item => ({
        type: "tag" as const,
        value: item.value,
        label: item.value,
        total: Number(item.count || 0),
        meta: `${Number(item.count || 0).toLocaleString("zh-CN")} 帖子`,
      })),
      ...(suggestionData.content || []).map(item => ({
        type: "term" as const,
        value: item.value,
        label: item.value,
        total: Number(item.count || 0),
        meta: `${Number(item.count || 0).toLocaleString("zh-CN")} 个相关标题`,
      })),
    ].sort((left, right) => right.total - left.total || left.label.localeCompare(right.label, "zh-CN")).slice(0, 10)
    const from = suggestionData.metadata?.from_period
    const to = suggestionData.metadata?.to_period
    suggestionPeriod.value = from && to ? `${from} 至 ${to}` : "最近 12 个完整月份"
    loaded.value = true
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : "搜索索引加载失败"
  } finally {
    loading.value = false
  }
}

async function showSearch() {
  open.value = true
  query.value = ""
  await loadEntities()
  await nextTick()
  input.value?.focus()
}

function closeSearch() {
  open.value = false
  query.value = ""
}

function choose(result: EntityResult) {
  emit("select", result)
  closeSearch()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape") closeSearch()
  else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault()
    const direction = event.key === "ArrowDown" ? 1 : -1
    activeIndex.value = Math.max(0, Math.min(visibleResults.value.length - 1, activeIndex.value + direction))
  } else if (event.key === "Enter" && visibleResults.value[activeIndex.value]) {
    event.preventDefault()
    choose(visibleResults.value[activeIndex.value])
  }
}

function suggestionIndex(result: EntityResult) {
  return suggestions.value.indexOf(result)
}

onBeforeUnmount(() => document.body.classList.remove("dialog-open"))
</script>

<template>
  <button class="icon-button header-search-button" type="button" title="全局搜索" aria-label="全局搜索" @click="showSearch">
    <Search :size="17" aria-hidden="true" />
  </button>

  <Teleport to="body">
    <div v-if="open" class="global-search-backdrop" @mousedown.self="closeSearch">
      <section class="global-search-dialog" role="dialog" aria-modal="true" aria-labelledby="global-search-title" @keydown="handleKeydown">
        <header>
          <div><span>快速跳转</span><h2 id="global-search-title">搜索看板数据</h2></div>
          <button class="icon-button" type="button" title="关闭" aria-label="关闭全局搜索" @click="closeSearch"><X :size="18" aria-hidden="true" /></button>
        </header>
        <label class="global-search-input">
          <Search :size="18" aria-hidden="true" />
          <input
            ref="input"
            v-model="query"
            type="search"
            role="combobox"
            autocomplete="off"
            aria-autocomplete="list"
            aria-haspopup="listbox"
            :aria-expanded="open"
            aria-controls="global-search-list"
            :aria-activedescendant="activeDescendant"
            placeholder="搜索话题、内容、节点或成员"
            aria-label="搜索看板数据"
          />
          <LoaderCircle v-if="loading" class="global-search-spinner" :size="18" aria-hidden="true" />
        </label>
        <div id="global-search-list" class="global-search-results" role="listbox" aria-label="搜索结果">
          <div v-if="!loading && !query.trim() && suggestions.length" class="global-search-suggestions">
            <section role="group" aria-label="近期热点">
              <header><h3>近期热点</h3><small>{{ suggestionPeriod }}</small></header>
              <div>
                <button
                  v-for="result in suggestions"
                  :id="`global-search-option-${suggestionIndex(result)}`"
                  :key="`${result.type}:${result.value}`"
                  type="button"
                  role="option"
                  :aria-selected="suggestionIndex(result) === activeIndex"
                  :class="{ active: suggestionIndex(result) === activeIndex }"
                  @mouseenter="activeIndex = suggestionIndex(result)"
                  @click="choose(result)"
                >
                  <strong>{{ result.label }}</strong><small>{{ result.total.toLocaleString("zh-CN") }} 次</small>
                </button>
              </div>
            </section>
            <p>按最近 12 个完整月份的相关帖子数整理；仅覆盖看板已聚合数据，并非 V2EX 全文搜索。</p>
          </div>
          <button
            v-for="(result, index) in results"
            v-show="query.trim()"
            :id="`global-search-option-${index}`"
            :key="`${result.type}:${result.value}`"
            type="button"
            role="option"
            :aria-selected="index === activeIndex"
            :class="{ active: index === activeIndex }"
            @mouseenter="activeIndex = index"
            @click="choose(result)"
          >
            <component :is="typeIcons[result.type]" :size="17" aria-hidden="true" />
            <span><strong>{{ result.label }}</strong><small>{{ result.meta }}</small></span>
            <em>{{ typeLabels[result.type] }}</em>
          </button>
          <p v-if="loadError" class="global-search-empty global-search-error">{{ loadError }}，请关闭后重试。</p>
          <p v-else-if="loading" class="global-search-empty">正在载入搜索索引。</p>
          <p v-else-if="!query.trim() && !suggestions.length" class="global-search-empty">搜索看板已收录的话题、内容热词、节点和部分活跃成员，结果可直接打开对应详情。</p>
          <p v-else-if="!loading && query.trim() && !results.length" class="global-search-empty">没有匹配结果。</p>
        </div>
        <footer><span>↑↓ 选择</span><span>Enter 打开</span><span>Esc 关闭</span></footer>
      </section>
    </div>
  </Teleport>
</template>
