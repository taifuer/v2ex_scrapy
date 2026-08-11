<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { Plus, Search, X } from "@lucide/vue"
import { comparisonColors } from "../chartTheme"
import type { SearchOption } from "../types/analytics"

const props = withDefaults(defineProps<{
  label: string
  modelValue: string[]
  options: SearchOption[]
  exclude?: string[]
  max?: number
  loading?: boolean
}>(), {
  exclude: () => [],
  max: 4,
  loading: false,
})

const emit = defineEmits<{ "update:modelValue": [values: string[]] }>()
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const query = ref("")
const open = ref(false)
const openUp = ref(false)
const menuMaxHeight = ref(320)
const activeIndex = ref(0)

const optionMap = computed(() => new Map(props.options.map(option => [option.value, option])))
const selectedOptions = computed(() => props.modelValue
  .filter(value => !props.exclude.includes(value))
  .map(value => optionMap.value.get(value) || { value, label: value }))
const availableOptions = computed(() => props.options.filter(option => (
  !props.exclude.includes(option.value) && !props.modelValue.includes(option.value)
)))
const filteredOptions = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase("zh-CN")
  const matches = needle
    ? availableOptions.value.filter(option => (
      `${option.label} ${option.value} ${option.meta || ""}`.toLocaleLowerCase("zh-CN").includes(needle)
    ))
    : availableOptions.value
  return matches.slice(0, 100)
})
const atLimit = computed(() => selectedOptions.value.length >= props.max)
const activeDescendant = computed(() => open.value && filteredOptions.value[activeIndex.value]
  ? `comparison-option-${props.label}-${activeIndex.value}`
  : undefined)

watch(filteredOptions, () => { activeIndex.value = 0 })
watch(atLimit, value => { if (value) closeOptions() })

function chipStyle(index: number) {
  return { "--comparison-color": comparisonColors[index % comparisonColors.length] }
}

function toggleOptions() {
  if (open.value) {
    closeOptions()
    return
  }
  if (atLimit.value) return
  open.value = true
  query.value = ""
  nextTick(() => {
    input.value?.focus()
    positionMenu()
    requestAnimationFrame(positionMenu)
  })
}

function positionMenu() {
  if (!open.value || !trigger.value) return
  const rect = trigger.value.getBoundingClientRect()
  const viewport = window.visualViewport
  const viewportTop = viewport?.offsetTop || 0
  const viewportBottom = viewportTop + (viewport?.height || window.innerHeight)
  const spaceAbove = Math.max(0, rect.top - viewportTop - 8)
  const spaceBelow = Math.max(0, viewportBottom - rect.bottom - 8)
  openUp.value = spaceBelow < 260 && spaceAbove > spaceBelow
  const availableSpace = openUp.value ? spaceAbove : spaceBelow
  menuMaxHeight.value = Math.max(100, Math.min(360, Math.floor(availableSpace - 5)))
}

function addOption(option: SearchOption) {
  if (atLimit.value || props.exclude.includes(option.value) || props.modelValue.includes(option.value)) return
  emit("update:modelValue", [...props.modelValue, option.value].slice(0, props.max))
  closeOptions()
  nextTick(() => trigger.value?.focus())
}

function removeValue(value: string) {
  emit("update:modelValue", props.modelValue.filter(item => item !== value))
}

function closeOptions() {
  open.value = false
  query.value = ""
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault()
    const direction = event.key === "ArrowDown" ? 1 : -1
    activeIndex.value = Math.max(0, Math.min(filteredOptions.value.length - 1, activeIndex.value + direction))
  } else if (event.key === "Enter") {
    event.preventDefault()
    const option = filteredOptions.value[activeIndex.value]
    if (option) addOption(option)
  } else if (event.key === "Escape") {
    event.preventDefault()
    closeOptions()
    trigger.value?.focus()
  }
}

function handleOutside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) closeOptions()
}

onMounted(() => {
  document.addEventListener("pointerdown", handleOutside)
  window.addEventListener("resize", positionMenu)
  window.visualViewport?.addEventListener("resize", positionMenu)
  window.visualViewport?.addEventListener("scroll", positionMenu)
})

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleOutside)
  window.removeEventListener("resize", positionMenu)
  window.visualViewport?.removeEventListener("resize", positionMenu)
  window.visualViewport?.removeEventListener("scroll", positionMenu)
})
</script>

<template>
  <div ref="root" class="comparison-select" :aria-busy="loading">
    <div class="comparison-selection">
      <span v-for="(option, index) in selectedOptions" :key="option.value" class="comparison-chip" :style="chipStyle(index)">
        <i aria-hidden="true"></i>
        <span>{{ option.label }}</span>
        <button type="button" :aria-label="`移除对比 ${option.label}`" :title="`移除 ${option.label}`" @click="removeValue(option.value)">
          <X :size="13" aria-hidden="true" />
        </button>
      </span>
      <button
        ref="trigger"
        class="comparison-trigger"
        type="button"
        :disabled="atLimit"
        :aria-label="atLimit ? `最多对比 ${max} 项` : '添加对比'"
        :aria-expanded="open"
        @click="toggleOptions"
      >
        <Plus :size="15" aria-hidden="true" />
        <span>{{ loading ? "加载中" : "添加对比" }}</span>
        <small v-if="selectedOptions.length">{{ selectedOptions.length }}/{{ max }}</small>
      </button>
    </div>

    <div v-if="open" class="comparison-menu" :class="{ 'drop-up': openUp }" :style="{ maxHeight: `${menuMaxHeight}px` }">
      <label class="comparison-search">
        <Search :size="15" aria-hidden="true" />
        <input
          ref="input"
          v-model="query"
          type="search"
          role="combobox"
          autocomplete="off"
          :aria-label="`搜索${label}`"
          :aria-expanded="open"
          :aria-controls="`comparison-list-${label}`"
          :aria-activedescendant="activeDescendant"
          placeholder="输入关键词搜索"
          @keydown="handleKeydown"
        />
      </label>
      <div :id="`comparison-list-${label}`" class="comparison-options" role="listbox" aria-multiselectable="true">
        <button
          v-for="(option, index) in filteredOptions"
          :id="`comparison-option-${label}-${index}`"
          :key="option.value"
          type="button"
          role="option"
          :class="{ active: index === activeIndex }"
          aria-selected="false"
          @mouseenter="activeIndex = index"
          @click="addOption(option)"
        >
          <span><strong>{{ option.label }}</strong><small v-if="option.meta">{{ option.meta }}</small></span>
        </button>
        <span v-if="!filteredOptions.length" class="comparison-empty">没有可添加的匹配项</span>
        <span v-else-if="availableOptions.length > filteredOptions.length" class="comparison-hint">继续输入可缩小范围</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.comparison-select { position: relative; min-width: 0; }
.comparison-selection { display: flex; min-height: 36px; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 6px; }
.comparison-chip { display: inline-flex; max-width: 180px; height: 32px; align-items: center; gap: 6px; border: 1px solid #d9dee7; border-radius: 5px; background: #f8fafb; color: #344054; padding: 0 5px 0 8px; font-size: 12px; font-weight: 600; }
.comparison-chip > i { width: 8px; height: 8px; flex: 0 0 auto; border-radius: 50%; background: var(--comparison-color); }
.comparison-chip > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.comparison-chip > button { display: inline-grid; width: 22px; height: 22px; flex: 0 0 auto; border: 0; border-radius: 4px; background: transparent; color: #667085; padding: 0; place-items: center; }
.comparison-chip > button:hover { background: #e9edf2; color: #1d2939; }
.comparison-trigger { display: inline-flex; height: 36px; align-items: center; gap: 6px; border: 1px solid #c6ced9; border-radius: 5px; background: #fff; color: #344054; padding: 0 10px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.comparison-trigger:hover:not(:disabled) { border-color: #98a2b3; background: #f8fafb; }
.comparison-trigger:focus-visible { outline: 3px solid rgba(220, 63, 58, 0.16); outline-offset: 1px; }
.comparison-trigger:disabled { cursor: default; opacity: 0.6; }
.comparison-trigger small { color: #667085; font-size: 11px; font-weight: 500; }
.comparison-menu { position: absolute; z-index: 90; top: calc(100% + 6px); right: 0; display: flex; width: min(340px, calc(100vw - 32px)); min-height: 100px; flex-direction: column; overflow: hidden; border: 1px solid #cfd6e1; border-radius: 7px; background: #fff; padding: 6px; box-shadow: 0 14px 34px rgba(16, 24, 40, 0.16); }
.comparison-menu.drop-up { top: auto; bottom: calc(100% + 6px); }
.comparison-search { position: relative; display: flex; flex: 0 0 auto; align-items: center; color: #667085; }
.comparison-search > svg { position: absolute; left: 10px; pointer-events: none; }
.comparison-search input { width: 100%; height: 38px; border: 1px solid #cfd6e1; border-radius: 5px; color: #1d2939; padding: 0 10px 0 32px; font: inherit; font-size: 13px; outline: 0; }
.comparison-search input:focus { border-color: #d94841; box-shadow: 0 0 0 3px rgba(220, 63, 58, 0.12); }
.comparison-search input::-webkit-search-cancel-button { display: none; }
.comparison-options { min-height: 0; overflow-y: auto; overscroll-behavior-y: contain; touch-action: pan-y; -webkit-overflow-scrolling: touch; padding-top: 5px; }
.comparison-options > button { display: block; width: 100%; min-height: 42px; touch-action: pan-y; border: 0; border-radius: 5px; background: transparent; color: #1d2939; padding: 7px 9px; text-align: left; }
.comparison-options > button.active { background: #f2f4f7; }
.comparison-options strong, .comparison-options small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.comparison-options strong { font-size: 13px; }
.comparison-options small { margin-top: 3px; color: #667085; font-size: 11px; font-weight: 400; }
.comparison-empty, .comparison-hint { display: block; color: #667085; padding: 12px 9px; font-size: 12px; }
.comparison-hint { border-top: 1px solid #edf0f3; text-align: center; }
@media (max-width: 680px) {
  .comparison-select, .comparison-selection { width: 100%; }
  .comparison-selection { justify-content: flex-start; }
  .comparison-chip { max-width: calc(50% - 3px); }
  .comparison-trigger { flex: 1 1 130px; justify-content: center; }
  .comparison-menu { right: auto; left: 0; width: 100%; }
}
</style>
