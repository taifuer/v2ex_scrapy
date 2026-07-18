<script setup lang="ts">
import { computed } from "vue"
import { CalendarDays, ChevronDown, Tag, UserRound } from "@lucide/vue"

const props = withDefaults(defineProps<{
  label: string
  modelValue: string
  periods: string[]
  incompletePeriods?: string[]
  latestFirst?: boolean
  optionLabels?: Record<string, string>
  icon?: "calendar" | "tag" | "user"
  hideLabel?: boolean
}>(), {
  incompletePeriods: () => [],
  latestFirst: true,
  optionLabels: () => ({}),
  icon: "calendar",
  hideLabel: false,
})

const emit = defineEmits<{ "update:modelValue": [period: string] }>()
const displayedPeriods = computed(() => props.latestFirst ? [...props.periods].reverse() : props.periods)

function updatePeriod(event: Event) {
  emit("update:modelValue", (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <label class="period-select-control">
    <span v-if="!hideLabel" class="period-select-label">{{ label }}</span>
    <span class="period-select-shell">
      <Tag v-if="icon === 'tag'" :size="15" :stroke-width="1.8" aria-hidden="true" />
      <UserRound v-else-if="icon === 'user'" :size="15" :stroke-width="1.8" aria-hidden="true" />
      <CalendarDays v-else :size="15" :stroke-width="1.8" aria-hidden="true" />
      <select :value="modelValue" :aria-label="label" @change="updatePeriod">
        <option v-for="period in displayedPeriods" :key="period" :value="period">
          {{ optionLabels[period] || period }}{{ incompletePeriods.includes(period) ? "（进行中）" : "" }}
        </option>
      </select>
      <ChevronDown class="period-select-chevron" :size="15" :stroke-width="1.8" aria-hidden="true" />
    </span>
  </label>
</template>
