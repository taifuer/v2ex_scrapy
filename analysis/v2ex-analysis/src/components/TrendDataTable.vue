<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue"
import { trendTable, type TrendTable } from "../utils/trendTable"
import type { DashboardChart } from "../chartRuntime"

const props = defineProps<{
  chartId: string
  periods: string[]
  selectedPeriod: string
}>()
const emit = defineEmits<{ select: [period: string] }>()
const open = ref(false)
const data = ref<TrendTable>({ columns: [], rows: [] })
let chart: DashboardChart | undefined
let element: HTMLElement | null = null
let request = 0

function refresh() {
  if (chart && !chart.isDisposed()) data.value = trendTable(chart.getOption())
}

function detach() {
  chart?.off("finished", refresh)
  chart = undefined
  element?.removeEventListener("dashboard-chart-ready", ready)
  element = null
}

function bind(instance: DashboardChart | undefined) {
  chart?.off("finished", refresh)
  chart = instance
  chart?.on("finished", refresh)
  refresh()
}

function ready(event: Event) {
  bind((event as CustomEvent<DashboardChart>).detail)
}

async function toggle(event: Event) {
  open.value = (event.currentTarget as HTMLDetailsElement).open
  const token = ++request
  detach()
  if (!open.value) return
  element = document.getElementById(props.chartId)
  element?.addEventListener("dashboard-chart-ready", ready)
  const { chartFor } = await import("../chartRuntime")
  if (token !== request) return
  bind(element ? chartFor(element) : undefined)
}

onBeforeUnmount(() => { request++; detach() })
</script>

<template>
  <details class="trend-data" @toggle="toggle">
    <summary>趋势数据</summary>
    <div v-if="open" class="trend-data-scroll" role="region" aria-label="趋势数据表" tabindex="0">
      <table>
        <caption class="sr-only">当前图表的逐期数值，按时间倒序</caption>
        <thead><tr><th scope="col">时间</th><th v-for="column in data.columns" :key="column" scope="col">{{ column }}</th></tr></thead>
        <tbody>
          <tr v-for="row in data.rows" :key="row.period">
            <th scope="row">
              <button v-if="periods.includes(row.period)" class="text-action" :aria-pressed="selectedPeriod === row.period" :aria-label="`${row.period} 代表帖子`" @click="emit('select', selectedPeriod === row.period ? '' : row.period)">{{ row.period }}</button>
              <span v-else>{{ row.period }}</span>
            </th>
            <td v-for="(value, index) in row.values" :key="index">{{ value === null ? '未知' : value.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </details>
</template>

<style scoped>
.trend-data { margin-top: 8px; color: var(--muted); font-size: 13px; }
summary { width: fit-content; padding: 6px 0; cursor: pointer; }
.trend-data-scroll { max-height: 320px; overflow: auto; margin-top: 8px; border: 1px solid var(--line, #e4e7ec); border-radius: 4px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 12px; text-align: right; border-bottom: 1px solid var(--line, #e4e7ec); white-space: nowrap; }
th:first-child { text-align: left; }
thead th { position: sticky; top: 0; background: #f8fafc; color: var(--ink); font-weight: 600; }
tbody th { font-weight: 400; }
button[aria-pressed="true"] { color: var(--accent); font-weight: 700; text-decoration: underline; }
summary:focus-visible, .trend-data-scroll:focus-visible, button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
