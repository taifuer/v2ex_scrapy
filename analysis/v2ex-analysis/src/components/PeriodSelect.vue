<script setup lang="ts">
import { computed } from "vue"
import { CalendarDays, ChevronDown } from "@lucide/vue"

const props = withDefaults(defineProps<{
  label: string
  modelValue: string
  periods: string[]
  incompletePeriods?: string[]
  latestFirst?: boolean
}>(), {
  incompletePeriods: () => [],
  latestFirst: true,
})

const emit = defineEmits<{ "update:modelValue": [period: string] }>()
const displayedPeriods = computed(() => props.latestFirst ? [...props.periods].reverse() : props.periods)

function updatePeriod(event: Event) {
  emit("update:modelValue", (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <label class="period-select-control">
    <span class="period-select-label">{{ label }}</span>
    <span class="period-select-shell">
      <CalendarDays :size="15" :stroke-width="1.8" aria-hidden="true" />
      <select :value="modelValue" :aria-label="label" @change="updatePeriod">
        <option v-for="period in displayedPeriods" :key="period" :value="period">
          {{ period }}{{ incompletePeriods.includes(period) ? "（进行中）" : "" }}
        </option>
      </select>
      <ChevronDown class="period-select-chevron" :size="15" :stroke-width="1.8" aria-hidden="true" />
    </span>
  </label>
</template>
