type Item = { name?: string; type?: string; data?: unknown[] }
type ChartDescriptionInput = {
  title?: { text?: string } | { text?: string }[]
  xAxis?: { data?: unknown[] } | { data?: unknown[] }[]
  series?: Item | Item[]
}

export function describeChart(option: ChartDescriptionInput): string {
  const titles = Array.isArray(option.title) ? option.title : [option.title]
  const series = Array.isArray(option.series) ? option.series : option.series ? [option.series] : []
  const axes = Array.isArray(option.xAxis) ? option.xAxis : [option.xAxis]
  const periods = axes.flatMap(axis => axis?.data || []).filter((value): value is string =>
    typeof value === "string" && /^\d{4}(-\d{2}|-?Q[1-4])?$/.test(value))
  const names = [...new Set(series.map(item => item.name).filter(Boolean))]
  const text = titles.map(title => title?.text).filter(Boolean).join("，") || (series.some(item => item.type === "heatmap") ? "排名热力图" : "统计图表")
  const range = periods.length ? `。时间范围 ${periods[0]} 至 ${periods[periods.length - 1]}` : ""
  const measures = names.length ? `。包含 ${names.slice(0, 5).join("、")}${names.length > 5 ? `等 ${names.length} 项` : ""}` : ""
  return `${text}${range}${measures}。`
}
