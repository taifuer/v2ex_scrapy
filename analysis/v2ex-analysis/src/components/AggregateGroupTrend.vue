<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import type { DashboardChart } from "../chartRuntime"
import { categoricalColors, chartTheme } from "../chartTheme"
import type { Grain } from "../types/analytics"
import { clearLegendHoverAfterSelection, responsiveChartSides, wrappedLegendLayout } from "../utils/chartLayout"

type GroupDefinition = {
  id?: string
  name?: string
  label: string
  color?: string
}

const props = defineProps<{
  groups: GroupDefinition[]
  rows: Array<[string, string, number, ...unknown[]]>
  periodTotals: Record<string, number>
  fromPeriod: string
  toPeriod: string
  grain: Grain
}>()

const chartElement = ref<HTMLElement | null>(null)
let chart: DashboardChart | null = null
let chartRuntime: typeof import("../chartRuntime") | null = null
let renderId = 0

function escapeHtml(value: unknown) {
  const element = document.createElement("span")
  element.textContent = String(value ?? "")
  return element.innerHTML
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("zh-CN")
}

function groupId(group: GroupDefinition) {
  return group.id || group.name || group.label
}

function bucketFor(period: string) {
  return props.grain === "year" ? period.slice(0, 4) : period
}

async function renderChart() {
  const currentRender = ++renderId
  await nextTick()
  const element = chartElement.value
  if (!element || !props.groups.length || !props.fromPeriod || !props.toPeriod) return
  chartRuntime ||= await import("../chartRuntime")
  if (currentRender !== renderId || !element.isConnected) return
  if (!chart || chart.getDom() !== element) {
    chart?.dispose()
    chart = chartRuntime.initChart(element)
  }

  const totals = new Map<string, number>()
  for (const [period, total] of Object.entries(props.periodTotals || {})) {
    if (period < props.fromPeriod || period > props.toPeriod) continue
    const bucket = bucketFor(period)
    totals.set(bucket, (totals.get(bucket) || 0) + Number(total || 0))
  }
  const values = new Map<string, Map<string, number>>()
  for (const [period, id, rawCount] of props.rows || []) {
    if (period < props.fromPeriod || period > props.toPeriod) continue
    const bucket = bucketFor(period)
    if (!values.has(bucket)) values.set(bucket, new Map())
    const bucketValues = values.get(bucket)!
    bucketValues.set(id, (bucketValues.get(id) || 0) + Number(rawCount || 0))
  }
  const periods = [...totals.keys()].sort()
  const definitions = props.groups.map((group, index) => ({
    ...group,
    id: groupId(group),
    color: group.color || categoricalColors[index % categoricalColors.length],
  }))
  const legendLayout = wrappedLegendLayout(element, definitions.map(group => group.label))
  const chartSides = responsiveChartSides(element)
  chart.resize()
  chart.setOption({
    aria: { enabled: true },
    animation: false,
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "line", lineStyle: { color: chartTheme.pointer, width: 1 } },
      formatter(params: any[]) {
        const compact = element.clientWidth <= 680
        const items = [...params].sort((left, right) => Number(right.value) - Number(left.value))
        const period = String(items[0]?.axisValue || "")
        const rows = items.map(item => {
          const count = values.get(period)?.get(definitions[item.seriesIndex]?.id) || 0
          return `<span style="display:flex;align-items:center;justify-content:space-between;gap:12px;${compact ? "" : "min-width:170px"}">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${Number(item.value).toFixed(2)}% <small style="color:${chartTheme.axis};font-weight:400">${formatNumber(count)} 帖子</small></strong></span>`
        }).join("")
        return `<div style="min-width:${compact ? "220px" : "360px"}"><strong>${escapeHtml(period)}</strong><div style="display:grid;grid-template-columns:${compact ? "1fr" : "repeat(2,minmax(0,1fr))"};gap:6px 18px;margin-top:8px">${rows}</div></div>`
      },
    },
    legend: legendLayout.option,
    grid: { top: 24, ...chartSides, bottom: legendLayout.gridBottom },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: periods,
      axisLabel: { color: chartTheme.axis, fontSize: 11, showMinLabel: true, showMaxLabel: true },
      axisLine: { lineStyle: { color: chartTheme.axisLine } },
    },
    yAxis: {
      type: "value",
      name: "帖子占比 (%)",
      min: 0,
      nameTextStyle: { color: chartTheme.axis, fontSize: 12 },
      axisLabel: { color: chartTheme.axis, fontSize: 11, formatter: "{value}%" },
      splitLine: { lineStyle: { color: chartTheme.gridLine } },
    },
    series: definitions.map(group => ({
      name: group.label,
      type: "line",
      data: periods.map(period => {
        const count = values.get(period)?.get(group.id) || 0
        return count / Math.max(1, totals.get(period) || 0) * 100
      }),
      showSymbol: false,
      lineStyle: { color: group.color, width: 2 },
      itemStyle: { color: group.color },
      emphasis: { focus: "series", lineStyle: { width: 4 } },
    })),
  } as any, true)
  clearLegendHoverAfterSelection(chart)
  chart.resize()
}

function handleResize() {
  if (chart?.getDom().isConnected) void renderChart()
}

watch(
  () => [props.groups, props.rows, props.periodTotals, props.fromPeriod, props.toPeriod, props.grain],
  () => { void renderChart() },
)

onMounted(() => {
  window.addEventListener("resize", handleResize)
  void renderChart()
})

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize)
  renderId += 1
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="chartElement" class="chart aggregate-group-trend"></div>
</template>
