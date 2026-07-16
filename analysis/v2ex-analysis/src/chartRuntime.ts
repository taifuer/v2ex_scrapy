import * as echarts from "echarts/core"
import { BarChart, HeatmapChart, LineChart } from "echarts/charts"
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components"
import { CanvasRenderer } from "echarts/renderers"

echarts.use([
  BarChart,
  HeatmapChart,
  LineChart,
  AriaComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

export function initChart(element: HTMLElement) {
  return echarts.init(element, undefined, { renderer: "canvas" })
}

export type DashboardChart = ReturnType<typeof initChart>
