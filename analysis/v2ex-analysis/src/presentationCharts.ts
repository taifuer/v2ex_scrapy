import { use } from "echarts/core"
import { MarkLineComponent } from "echarts/components"
import { initChart, type DashboardChart } from "./chartRuntime"
import { chartTheme } from "./chartTheme"

use([MarkLineComponent])

export type PresentationChartSpec = {
  kind: "line" | "small_multiples" | "hourly_bars" | "grouped_bar" | "horizontal_bar"
  categories: string[]
  series: { name: string; values: number[]; highlight?: { category: string; label: string } }[]
  axis_name?: string
  unit?: string
  partial?: string[]
  annotations?: { category: string; label: string }[]
  category_kind?: string | null
  series_kind?: string | null
}

type ChartContext = { nodeLabel?: (node: string) => string }
export type PresentationChartHandle = { resize: () => void; dispose: () => void }

const palette = ["#3678b5", "#d77a36", "#20887b", "#8857aa", "#cc5278", "#657482"]
const namedColors: Record<string, string> = {
  "帖子": "#d94841", "评论": "#4e79a7", "新增成员": "#21877c",
  "AI": "#d94841", "ChatGPT": "#d77a36", "模型": "#8857aa",
  "DeepSeek": "#21877c", "Cursor": "#b2762d", "Claude Code": "#8857aa",
  "Agent": "#0891a0", "Codex": "#3678b5", "Python": "#3678b5", "Java": "#d77a36",
  "招聘": "#21877c", "面试": "#3678b5", "裁员": "#d94841", "失业": "#8857aa",
  "投资与经济": "#3678b5", "加密与 Web3": "#d77a36",
  "买房": "#3678b5", "房价": "#d77a36", "房贷": "#8857aa", "租房": "#21877c",
  "拼车": "#0891a0", "订阅": "#8857aa", "88vip": "#b2762d",
}

function seriesColors(spec: PresentationChartSpec) {
  const used = new Set<string>()
  return spec.series.map((item, index) => {
    const preferred = namedColors[item.name] || palette[index % palette.length]
    const color = used.has(preferred) ? palette.find(value => !used.has(value)) || preferred : preferred
    used.add(color)
    return color
  })
}

function escapeHtml(value: unknown) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]!))
}

function formatNumber(value: number, digits = 0) {
  return Number(value).toLocaleString("zh-CN", { maximumFractionDigits: digits })
}

function shortNumber(value: number) {
  return Math.abs(value) >= 10_000 ? `${formatNumber(value / 10_000, 1)}万` : formatNumber(value, 1)
}

function displayValue(value: number, unit = "") {
  if (unit === "%") return `${formatNumber(value, 2)}%`
  if (unit === "帖/万帖") return formatNumber(value, 1)
  return formatNumber(value)
}

function displayLabel(value: string, kind: string | null | undefined, context: ChartContext) {
  return kind === "node" ? (context.nodeLabel?.(value) || value).split(" · ")[0] : value
}

function categoryAxis(data: string[], width: number, boundaryGap = false, fontSize = 12) {
  const step = Math.max(1, Math.ceil((data.length - 1) / Math.max(2, Math.floor(width / 110))))
  return {
    type: "category", boundaryGap, data,
    axisLine: { lineStyle: { color: chartTheme.axisLine } },
    axisTick: { show: false },
    axisLabel: {
      color: chartTheme.axis, fontSize, margin: 14, showMinLabel: true, showMaxLabel: true,
      interval: (index: number) => index === 0 || index === data.length - 1 || (index % step === 0 && index < data.length - 1 - Math.ceil(step / 2)),
      formatter: (value: string) => /^\d{2}:00$/.test(value) ? `${Number(value.slice(0, 2))}时` : value,
    },
  }
}

function valueAxis(name: string, unit = "", fontSize = 12) {
  return {
    type: "value", name, nameLocation: "end", nameGap: 18,
    nameTextStyle: { align: "left", color: chartTheme.axis, fontSize, padding: [0, 0, 0, -6] },
    min: 0, splitNumber: 4,
    axisLabel: { color: chartTheme.axis, fontSize, formatter: (value: number) => unit === "%" ? `${value}%` : shortNumber(value) },
    splitLine: { lineStyle: { color: chartTheme.gridLine } },
  }
}

function legendHeight(names: string[], width: number) {
  let rows = 1
  let used = 0
  for (const name of names) {
    const itemWidth = [...name].reduce((total, char) => total + (/[^\u0000-\u00ff]/.test(char) ? 12 : 7), 0) + 46
    if (used && used + itemWidth > width) { rows += 1; used = 0 }
    used += itemWidth
  }
  return rows * 25
}

function tooltip(spec: PresentationChartSpec, context: ChartContext) {
  return (params: any[]) => {
    const items = [...params].sort((a, b) => Number(b.value) - Number(a.value))
    const category = displayLabel(String(items[0]?.axisValue ?? ""), spec.category_kind, context)
    const partial = spec.partial?.includes(category) ? " · 非完整年" : ""
    return `<strong>${escapeHtml(category + partial)}</strong><div style="display:grid;gap:7px;margin-top:9px">${items.map(item =>
      `<div style="display:flex;align-items:center;gap:14px">${item.marker}<span style="flex:1">${escapeHtml(item.seriesName)}</span><strong>${displayValue(Number(item.value), spec.unit)}</strong></div>`
    ).join("")}</div>`
  }
}

function markLines(spec: PresentationChartSpec, compact: boolean) {
  const annotations = (spec.annotations || []).filter(item => spec.categories.includes(item.category))
  if (!annotations.length) return undefined
  return {
    silent: true, symbol: ["none", "none"],
    lineStyle: { color: "#a5aeb9", type: "dashed", width: 1 },
    label: { show: !compact, color: chartTheme.axis, fontSize: 12, formatter: "{b}", position: "insideEndTop", distance: 8 },
    data: annotations.map(item => ({
      name: item.label, xAxis: item.category,
      label: item.category === spec.categories[0] && spec.partial?.includes(item.category) ? { show: false } : undefined,
    })),
  }
}

function highlightedValues(spec: PresentationChartSpec, item: PresentationChartSpec["series"][number], color: string) {
  return item.values.map((value, index) => spec.categories[index] === item.highlight?.category ? {
    value, symbol: "circle", symbolSize: 7,
    label: { show: true, formatter: item.highlight.label, position: index > item.values.length - 3 ? "left" : "top",
      color, fontSize: 12, backgroundColor: "#fff", padding: [4, 6], distance: 8 },
  } : spec.partial?.includes(spec.categories[index]) ? { value, symbol: "emptyCircle", symbolSize: 6 } : value)
}

function lineOptions(chart: DashboardChart, spec: PresentationChartSpec, context: ChartContext) {
  const width = chart.getWidth()
  const fontSize = width >= 1000 && chart.getHeight() >= 480 ? 14 : 12
  const compact = width < 600
  const names = spec.series.map(item => displayLabel(item.name, spec.series_kind, context))
  const colors = seriesColors(spec)
  const legend = legendHeight(names, width - 16)
  return {
    color: colors,
    tooltip: { trigger: "axis", confine: true, formatter: tooltip(spec, context), textStyle: { fontSize: 13 } },
    legend: { bottom: 0, left: "center", width: width - 8, type: "plain", itemWidth: 20, itemHeight: 3, itemGap: 18, textStyle: { color: "#475467", fontSize }, selectedMode: true },
    grid: { left: compact ? 49 : 65, right: compact ? 24 : 32, top: 42, bottom: legend + 48 },
    xAxis: categoryAxis(spec.categories, width - (compact ? 100 : 150), false, fontSize),
    yAxis: valueAxis(spec.axis_name || "帖子数", spec.unit, fontSize),
    series: spec.series.map((item, index) => ({
      name: names[index], type: "line", data: highlightedValues(spec, item, colors[index]),
      showSymbol: Boolean(item.highlight || spec.partial?.length), symbol: "emptyCircle",
      symbolSize: (_value: number, params: any) => spec.partial?.includes(spec.categories[params.dataIndex]) ? 8 : 0,
      lineStyle: { color: colors[index], width: 2.7 }, itemStyle: { color: colors[index] },
      legendHoverLink: false,
      emphasis: { disabled: window.matchMedia("(pointer: coarse)").matches, focus: "series", lineStyle: { width: 3.5 } },
      markLine: index === 0 ? markLines(spec, compact) : undefined,
    })),
  }
}

function smallMultipleOptions(chart: DashboardChart, spec: PresentationChartSpec) {
  const bars = spec.kind === "hourly_bars"
  const width = chart.getWidth()
  const fontSize = width >= 1000 && chart.getHeight() >= 480 ? 14 : 12
  const colors = seriesColors(spec)
  const step = (chart.getHeight() - 34) / spec.series.length
  return {
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    tooltip: {
      trigger: "axis", confine: true,
      formatter: (params: any[]) => {
        const item = params[0]
        if (!item) return ""
        return `<strong>${escapeHtml(item.axisValue)}</strong><div style="margin-top:8px">${spec.series.map((series, index) => `<div style="display:flex;gap:24px;justify-content:space-between;margin:5px 0;color:${colors[index]}"><span>${escapeHtml(series.name)}</span><strong>${bars ? displayValue(series.values[item.dataIndex], "%") : formatNumber(series.values[item.dataIndex]) + "/月"}</strong></div>`).join("")}</div>`
      },
    },
    grid: spec.series.map((_, index) => ({ left: width < 600 ? 54 : 70, right: 28, top: 26 + index * step, height: step - 44 })),
    xAxis: spec.series.map((_, index) => ({ ...categoryAxis(spec.categories, width - 120, bars, fontSize), gridIndex: index, axisLabel: index === spec.series.length - 1 ? categoryAxis(spec.categories, width - 120, bars, fontSize).axisLabel : { show: false } })),
    yAxis: spec.series.map((item, index) => ({ ...valueAxis(bars ? item.name + "占比" : `${item.name} / 月`, bars ? "%" : "", fontSize), ...(bars ? { max: Math.ceil(Math.max(...spec.series.flatMap(row => row.values))) } : {}), splitNumber: 2, gridIndex: index, nameTextStyle: { align: "left", fontSize, color: colors[index], fontWeight: 600 } })),
    series: spec.series.map((item, index) => ({ name: item.name, type: bars ? "bar" : "line", barMaxWidth: 26, xAxisIndex: index, yAxisIndex: index, data: bars ? item.values : highlightedValues(spec, item, colors[index]), showSymbol: true, symbolSize: 0, lineStyle: { color: colors[index], width: 2.7 }, itemStyle: { color: colors[index] }, areaStyle: { color: colors[index], opacity: .06 } })),
  }
}

function barOptions(chart: DashboardChart, spec: PresentationChartSpec, context: ChartContext) {
  const grouped = spec.kind === "grouped_bar"
  const threshold = spec.category_kind === "threshold"
  const city = spec.category_kind === "city"
  const width = chart.getWidth()
  const fontSize = (threshold ? width >= 600 && chart.getHeight() >= 220 : width >= 1000 && chart.getHeight() >= 480) ? 14 : 12
  const compact = width < 600
  const colors = seriesColors(spec)
  const categories = spec.categories.map(item => displayLabel(item, spec.category_kind, context))
  return {
    color: colors,
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, confine: true, formatter: tooltip(spec, context) },
    legend: { show: grouped, bottom: 0, left: "center", width: width - 8, itemWidth: 18, itemHeight: 6, itemGap: 18, textStyle: { fontSize }, selectedMode: false },
    grid: { left: city ? 44 : threshold ? 100 : compact ? 106 : 150, right: compact ? 48 : 70, top: 14, bottom: grouped ? legendHeight(spec.series.map(item => item.name), width - 16) + 46 : 54 },
    xAxis: { ...valueAxis(spec.axis_name || "帖子数", spec.unit, fontSize), nameLocation: "middle", nameGap: 32, nameTextStyle: { align: "center", color: chartTheme.axis, fontSize }, splitNumber: compact ? 2 : 4 },
    yAxis: { type: "category", inverse: true, data: categories, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#344054", fontSize, width: city ? 32 : compact ? 94 : 135, overflow: "break", lineHeight: 18 } },
    series: spec.series.map((item, index) => ({
      name: item.name, type: "bar", barMaxWidth: grouped ? 16 : 28, barMinHeight: 3, barGap: "30%", data: item.values,
      itemStyle: { color: grouped ? colors[index] : "#3678b5", borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: "right", color: "#475467", fontSize, formatter: (params: any) => displayValue(Number(params.value), spec.unit) },
      emphasis: { disabled: true },
    })),
  }
}

export function createPresentationChart(element: HTMLElement, spec: PresentationChartSpec, context: ChartContext = {}): PresentationChartHandle {
  const chart = initChart(element)
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  let dimensions = ""
  function render() {
    const option = spec.kind === "small_multiples" || spec.kind === "hourly_bars" ? smallMultipleOptions(chart, spec)
      : spec.kind === "line" ? lineOptions(chart, spec, context) : barOptions(chart, spec, context)
    const selected = (chart.getOption()?.legend as any[])?.[0]?.selected
    chart.setOption({ animation: !reducedMotion, animationDuration: 240, animationDurationUpdate: 0, ...option } as any, true)
    if (selected) chart.setOption({ legend: { selected } })
    dimensions = `${chart.getWidth()}:${chart.getHeight()}`
  }
  render()
  return {
    resize() {
      chart.resize()
      if (`${chart.getWidth()}:${chart.getHeight()}` !== dimensions) render()
    },
    dispose() { chart.dispose() },
  }
}
