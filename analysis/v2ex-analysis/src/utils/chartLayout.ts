import type { DashboardChart } from "../chartRuntime"

export function clearLegendHoverAfterSelection(chart: DashboardChart) {
  chart.off("legendselectchanged")
  chart.on("legendselectchanged", () => {
    requestAnimationFrame(() => chart.dispatchAction({ type: "downplay" }))
  })
}

export function wrappedLegendLayout(element: HTMLElement, names: string[], itemHeight = 3) {
  const availableWidth = Math.max(240, element.clientWidth - 24)
  let rowWidth = 0
  let rows = 1
  for (const name of names) {
    const textWidth = Array.from(name).reduce(
      (width, character) => width + (character.charCodeAt(0) <= 0xff ? 6.5 : 11),
      0,
    )
    const itemWidth = Math.min(availableWidth, 52 + textWidth)
    if (rowWidth > 0 && rowWidth + itemWidth > availableWidth) {
      rows += 1
      rowWidth = itemWidth
    } else {
      rowWidth += itemWidth
    }
  }
  const legendHeight = rows * 20
  const baseHeight = element.classList.contains("compact-chart")
    ? 300
    : window.innerWidth <= 680
      ? 430
      : element.classList.contains("tall") ? 520 : 400
  element.style.height = `${Math.max(baseHeight, 300 + legendHeight)}px`
  return {
    option: {
      type: "plain",
      bottom: 4,
      left: 12,
      width: availableWidth,
      itemWidth: 18,
      itemHeight,
      itemGap: 14,
      textStyle: { color: "#475467", fontSize: 12, lineHeight: 20 },
    },
    gridBottom: legendHeight + 50,
  }
}
