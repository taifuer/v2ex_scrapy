import type { DashboardChart } from "../chartRuntime"

export function rankHeatmapGrid(element: HTMLElement) {
  const inset = window.innerWidth <= 680 || element.clientWidth <= 420 ? 10 : 24
  return { top: 36, left: inset, right: inset, bottom: 48 }
}

export function clearLegendHoverAfterSelection(chart: DashboardChart) {
  chart.off("legendselectchanged")
  chart.on("legendselectchanged", () => {
    requestAnimationFrame(() => chart.dispatchAction({ type: "downplay" }))
  })
}

export function wrappedLegendLayout(element: HTMLElement, names: string[], itemHeight = 3) {
  const compact = window.innerWidth <= 680 || element.clientWidth <= 420
  const horizontalInset = compact ? 4 : 12
  const itemGap = compact ? 6 : 12
  const lineHeight = compact ? 18 : 20
  const availableWidth = Math.max(220, element.clientWidth - horizontalInset * 2)
  let rowWidth = 0
  let rows = 1
  for (const name of names) {
    const textWidth = Array.from(name).reduce(
      (width, character) => width + (character.charCodeAt(0) <= 0xff ? 6.5 : 11),
      0,
    )
    const itemWidth = Math.min(availableWidth, 30 + textWidth)
    if (rowWidth > 0 && rowWidth + itemGap + itemWidth > availableWidth) {
      rows += 1
      rowWidth = itemWidth
    } else {
      rowWidth += (rowWidth > 0 ? itemGap : 0) + itemWidth
    }
  }
  const legendHeight = rows * lineHeight + Math.max(0, rows - 1) * itemGap
  const baseHeight = element.classList.contains("compact-chart")
    ? 300
    : compact
      ? 430
      : element.classList.contains("tall") ? 520 : 400
  element.style.height = `${Math.max(baseHeight, 290 + legendHeight)}px`
  return {
    option: {
      type: "plain",
      bottom: 4,
      left: horizontalInset,
      width: availableWidth,
      itemWidth: 18,
      itemHeight,
      itemGap,
      textStyle: { color: "#475467", fontSize: compact ? 11 : 12, lineHeight },
    },
    gridBottom: legendHeight + (compact ? 44 : 50),
  }
}

export function responsiveChartSides(element: HTMLElement, dualAxis = false) {
  if (window.innerWidth <= 680 || element.clientWidth <= 420) {
    return { left: 52, right: dualAxis ? 52 : 10 }
  }
  return { left: 72, right: dualAxis ? 72 : 24 }
}
