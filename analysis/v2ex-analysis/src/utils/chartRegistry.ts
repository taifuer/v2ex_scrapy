import type { DashboardChart } from "../chartRuntime"

export function createChartRegistry(
  initialize: (element: HTMLElement) => DashboardChart,
  findElement: (id: string) => HTMLElement | null = id => document.getElementById(id),
) {
  const charts = new Map<string, DashboardChart>()

  function prune() {
    for (const [id, chart] of charts) {
      if (chart.isDisposed() || !chart.getDom()?.isConnected) {
        if (!chart.isDisposed()) chart.dispose()
        charts.delete(id)
      }
    }
  }

  return {
    get(id: string) {
      const element = findElement(id)
      if (!element) return null
      const current = charts.get(id)
      if (current && !current.isDisposed() && current.getDom() === element) return current
      if (current && !current.isDisposed()) current.dispose()
      const chart = initialize(element)
      charts.set(id, chart)
      return chart
    },
    prune,
    resize() {
      prune()
      for (const chart of charts.values()) chart.resize()
    },
    dispose() {
      for (const chart of charts.values()) if (!chart.isDisposed()) chart.dispose()
      charts.clear()
    },
  }
}
