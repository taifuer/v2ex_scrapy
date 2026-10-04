export type TrendTable = { columns: string[]; rows: { period: string; values: (number | null)[] }[] }

export function trendTable(option: any = {}): TrendTable {
  const axis = Array.isArray(option.xAxis) ? option.xAxis[0] : option.xAxis
  const periods = axis?.data || []
  const series = (option.series || []).filter((item: any) => item.type === "line")
  return {
    columns: series.map((item: any) => String(item.name || "数值")),
    rows: periods.map((period: any, index: number) => ({
      period: String(typeof period === "object" ? period.value : period),
      values: series.map((item: any) => {
        const datum = item.data?.[index]
        const value = datum && typeof datum === "object" ? datum.value : datum
        return typeof value === "number" && Number.isFinite(value) ? value : null
      }),
    })).reverse(),
  }
}
