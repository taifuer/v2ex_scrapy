<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ChevronDown, Network, Search, Tag, UserRound } from "@lucide/vue"
import type { SearchOption } from "../types/analytics"

const props = withDefaults(defineProps<{
  label: string
  modelValue: string
  options: SearchOption[]
  placeholder?: string
  icon?: "tag" | "user" | "node"
  hideLabel?: boolean
}>(), {
  placeholder: "输入关键词搜索",
  icon: "tag",
  hideLabel: false,
})

const emit = defineEmits<{ "update:modelValue": [value: string] }>()
const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const query = ref("")
const open = ref(false)
const activeIndex = ref(0)
const selectedOption = computed(() => props.options.find((option) => option.value === props.modelValue))
const normalizedQuery = computed(() => query.value.trim().toLocaleLowerCase("zh-CN"))
const filteredOptions = computed(() => {
  const needle = normalizedQuery.value
  const matches = needle
    ? props.options.filter((option) => `${option.label} ${option.value} ${option.meta || ""}`.toLocaleLowerCase("zh-CN").includes(needle))
    : props.options
  return matches.slice(0, 100)
})
const activeDescendant = computed(() => open.value && filteredOptions.value[activeIndex.value]
  ? `search-option-${props.label}-${activeIndex.value}`
  : undefined)

watch(() => props.modelValue, () => {
  if (!open.value) query.value = selectedOption.value?.label || ""
}, { immediate: true })
watch(filteredOptions, () => { activeIndex.value = 0 })

function showOptions() {
  open.value = true
  query.value = ""
  activeIndex.value = Math.max(0, filteredOptions.value.findIndex((option) => option.value === props.modelValue))
  nextTick(() => input.value?.select())
}

function selectOption(option: SearchOption) {
  emit("update:modelValue", option.value)
  query.value = option.label
  open.value = false
}

function closeOptions() {
  open.value = false
  query.value = selectedOption.value?.label || ""
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault()
    if (!open.value) showOptions()
    const direction = event.key === "ArrowDown" ? 1 : -1
    activeIndex.value = Math.max(0, Math.min(filteredOptions.value.length - 1, activeIndex.value + direction))
  } else if (event.key === "Enter" && open.value) {
    event.preventDefault()
    const option = filteredOptions.value[activeIndex.value]
    if (option) selectOption(option)
  } else if (event.key === "Escape") {
    event.preventDefault()
    closeOptions()
  }
}

function handleOutside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) closeOptions()
}

onMounted(() => document.addEventListener("pointerdown", handleOutside))
onBeforeUnmount(() => document.removeEventListener("pointerdown", handleOutside))
</script>

<template>
  <label ref="root" class="search-select-control">
    <span v-if="!hideLabel" class="period-select-label">{{ label }}</span>
    <span class="search-select-shell">
      <Tag v-if="icon === 'tag'" :size="15" aria-hidden="true" />
      <UserRound v-else-if="icon === 'user'" :size="15" aria-hidden="true" />
      <Network v-else :size="15" aria-hidden="true" />
      <input
        ref="input"
        v-model="query"
        type="search"
        role="combobox"
        autocomplete="off"
        :aria-label="label"
        :aria-expanded="open"
        :aria-controls="`search-list-${label}`"
        :aria-activedescendant="activeDescendant"
        :placeholder="placeholder"
        @focus="showOptions"
        @input="open = true"
        @keydown="handleKeydown"
      />
      <Search v-if="open" class="search-select-chevron" :size="15" aria-hidden="true" />
      <ChevronDown v-else class="search-select-chevron" :size="15" aria-hidden="true" />
      <span v-if="open" :id="`search-list-${label}`" class="search-select-menu" role="listbox">
        <button
          v-for="(option, index) in filteredOptions"
          :id="`search-option-${label}-${index}`"
          :key="option.value"
          type="button"
          role="option"
          :class="{ active: index === activeIndex, selected: option.value === modelValue }"
          :aria-selected="option.value === modelValue"
          @mouseenter="activeIndex = index"
          @pointerdown.prevent="selectOption(option)"
        >
          <span><strong>{{ option.label }}</strong><small v-if="option.meta">{{ option.meta }}</small></span>
        </button>
        <span v-if="!filteredOptions.length" class="search-select-empty">没有匹配项</span>
        <span v-else-if="options.length > filteredOptions.length" class="search-select-hint">继续输入可缩小范围</span>
      </span>
    </span>
  </label>
</template>
