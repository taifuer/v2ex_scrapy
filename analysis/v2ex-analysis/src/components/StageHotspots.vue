<script setup lang="ts">
import { computed } from "vue"
import type { StageHotspot } from "../utils/stageHotspots"
import { formatNumber } from "../utils/format"

const props = defineProps<{
  id: string
  items: StageHotspot[]
  periods: string[]
  entityLabel: string
}>()

const emit = defineEmits<{ select: [key: string] }>()

const periodIndices = computed(() => new Map(props.periods.map((period, index) => [period, index])))

function timelineStyle(item: StageHotspot) {
  const denominator = Math.max(1, props.periods.length - 1)
  const start = (periodIndices.value.get(item.start) || 0) / denominator * 100
  const end = (periodIndices.value.get(item.end) || 0) / denominator * 100
  const peak = (periodIndices.value.get(item.peak) || 0) / denominator * 100
  return {
    "--stage-start": `${start}%`,
    "--stage-width": `${Math.max(1.2, end - start)}%`,
    "--stage-peak": `${peak}%`,
  }
}

function rangeLabel(item: StageHotspot) {
  return item.start === item.end ? item.start : `${item.start} 至 ${item.end}`
}
</script>

<template>
  <article :id="id" class="analysis-block full stage-hotspots section-anchor">
    <header>
      <h2>阶段热点</h2>
      <p>识别{{ entityLabel }}在所选时间范围内相对自身过去水平明显升高、且达到最低帖子量的阶段，用于定位关注转折，不推断事件原因或讨论态度。</p>
    </header>
    <div v-if="items.length" class="stage-hotspot-list">
      <div v-for="(item, index) in items" :key="item.key" class="stage-hotspot-row">
        <span class="stage-hotspot-rank">{{ String(index + 1).padStart(2, "0") }}</span>
        <button type="button" @click="emit('select', item.key)">{{ item.key }}</button>
        <div class="stage-hotspot-period">
          <strong>{{ rangeLabel(item) }}</strong>
          <span>峰值 {{ item.peak }}</span>
        </div>
        <div class="stage-hotspot-track" :style="timelineStyle(item)" aria-hidden="true">
          <span></span><i></i>
        </div>
        <div class="stage-hotspot-value">
          <strong>{{ formatNumber(item.peakCount) }} 帖子</strong>
          <span>{{ item.lift === null ? "由低基数出现" : `约为基线 ${item.lift.toFixed(1)} 倍` }}</span>
        </div>
      </div>
    </div>
    <p v-else class="empty-state compact-empty">当前时间范围内没有达到识别条件的阶段热点。</p>
    <p v-if="periods.length" class="stage-hotspot-axis"><span>{{ periods[0] }}</span><span>{{ periods[periods.length - 1] }}</span></p>
  </article>
</template>
