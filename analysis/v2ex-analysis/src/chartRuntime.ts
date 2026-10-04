import * as echarts from "echarts/core"
import { BarChart, HeatmapChart, LineChart } from "echarts/charts"
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendPlainComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapContinuousComponent,
} from "echarts/components"
import { CanvasRenderer } from "echarts/renderers"
import { chartTheme, dashboardFontFamily } from "./chartTheme"

echarts.use([
  BarChart,
  HeatmapChart,
  LineChart,
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendPlainComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapContinuousComponent,
  CanvasRenderer,
])

echarts.registerTheme("v2ex-dashboard", {
  textStyle: { color: chartTheme.axis, fontFamily: dashboardFontFamily, fontSize: 12 },
  legend: { textStyle: { color: chartTheme.axis, fontFamily: dashboardFontFamily, fontSize: 12 } },
  tooltip: { textStyle: { color: "#17212f", fontFamily: dashboardFontFamily, fontSize: 12 } },
  categoryAxis: { axisLabel: { color: chartTheme.axis, fontFamily: dashboardFontFamily, fontSize: 11 } },
  valueAxis: { axisLabel: { color: chartTheme.axis, fontFamily: dashboardFontFamily, fontSize: 11 } },
})

export function initChart(element: HTMLElement) {
  const chart = echarts.init(element, "v2ex-dashboard", { renderer: "canvas" })
  element.dispatchEvent(new CustomEvent("dashboard-chart-ready", { detail: chart }))
  return chart
}

export function chartFor(element: HTMLElement) {
  return echarts.getInstanceByDom(element)
}

export type DashboardChart = ReturnType<typeof initChart>
