import * as echarts from "echarts/core"
import { BarChart, HeatmapChart, LineChart } from "echarts/charts"
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
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
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
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
  return echarts.init(element, "v2ex-dashboard", { renderer: "canvas" })
}

export type DashboardChart = ReturnType<typeof initChart>
