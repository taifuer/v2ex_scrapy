import { expect, test } from "@playwright/test"
import { createChartRegistry } from "../../src/utils/chartRegistry"
import type { DashboardChart } from "../../src/chartRuntime"
import { chartTooltip } from "../../src/utils/chartTooltip"

test("fits trend tooltips on narrow screens and escapes data labels", () => {
  const rows = [{ name: '<img src=x onerror="alert(1)">', value: "12", detail: "1.20%" }]
  const mobile = chartTooltip("2026-09", rows, 2, 320)
  expect(mobile).toContain("grid-template-columns:1fr")
  expect(mobile).toContain("width:250px")
  expect(mobile).toContain("min(320px,50vh)")
  expect(mobile).toContain("&lt;img")
  expect(mobile).not.toContain("<img")
  expect(chartTooltip("2026-09", rows, 2, 1440)).toContain("repeat(2,minmax(0,1fr))")
})

test("reuses connected charts and releases replaced or detached DOM", () => {
  const elements = new Map<string, HTMLElement>()
  const created: Array<{ disposed: boolean; resizes: number }> = []
  const registry = createChartRegistry(element => {
    const state = { disposed: false, resizes: 0 }
    created.push(state)
    return {
      getDom: () => state.disposed ? undefined : element,
      isDisposed: () => state.disposed,
      dispose: () => { state.disposed = true },
      resize: () => { state.resizes++ },
    } as unknown as DashboardChart
  }, id => elements.get(id) || null)
  const first = { isConnected: true } as HTMLElement
  elements.set("trend", first)
  const original = registry.get("trend")
  expect(registry.get("trend")).toBe(original)
  expect(created).toHaveLength(1)
  expect(registry.get("missing")).toBeNull()
  elements.set("trend", { isConnected: true } as HTMLElement)
  expect(registry.get("trend")).not.toBe(original)
  expect(created[0].disposed).toBe(true)
  registry.resize()
  expect(created[1].resizes).toBe(1)
  Object.assign(elements.get("trend")!, { isConnected: false })
  registry.prune()
  expect(created[1].disposed).toBe(true)
  registry.resize()
  registry.dispose()
  elements.set("trend", { isConnected: true } as HTMLElement)
  registry.get("trend")
  registry.dispose()
  expect(created[2].disposed).toBe(true)
})

test("keeps keyboard selection visible in detail search menus", async ({ page }) => {
  await page.goto("/?tab=content&view=content-detail&term=AI")
  const input = page.getByRole("combobox", { name: "选择标题关键词", exact: true })
  await input.click()
  for (let index = 0; index < 25; index++) await input.press("ArrowDown")
  const menu = page.getByRole("listbox")
  await expect.poll(() => menu.evaluate(element => {
    const selected = element.querySelector(".active")!.getBoundingClientRect()
    const bounds = element.getBoundingClientRect()
    return selected.top >= bounds.top - 1 && selected.bottom <= bounds.bottom + 1
  })).toBe(true)
  const selected = await menu.locator(".active strong").textContent()
  await input.press("Enter")
  await expect(menu).toHaveCount(0)
  await expect(input).toHaveValue(selected!)
  await expect(page.locator("#content-term-detail h2")).toHaveText(`标题关键词详情：${selected}`)
})

test("renders the keyword trend before a slow comment shard finishes", async ({ page }) => {
  let release!: () => void
  let commentsRequested = false
  const held = new Promise<void>(resolve => { release = resolve })
  await page.route("**/dynamic-content-period-comments-*.json*", async route => {
    commentsRequested = true
    await held
    await route.continue()
  })
  try {
    await page.goto("/?tab=content&view=content-detail&term=AI", { waitUntil: "domcontentloaded" })
    await expect(page.locator("#content-term-trend canvas").first()).toBeVisible()
    await expect.poll(() => commentsRequested).toBe(true)
    await expect(page.locator(".entity-representative-comments .loading-spinner")).toBeVisible()
    await expect(page.locator(".content-representative-list .post-row")).toHaveCount(10)
  } finally {
    release()
  }
  await expect(page.locator(".entity-representative-comments .comment-ranking-row")).toHaveCount(10)
})

test("keeps the Top 30 tooltip within the viewport", async ({ page }, testInfo) => {
  if (testInfo.project.name === "mobile") await page.setViewportSize({ width: 320, height: 844 })
  await page.goto("/?tab=content&view=topics")
  const panel = page.locator("#topic-trend-panel")
  await panel.scrollIntoViewIfNeeded()
  await panel.getByRole("button", { name: "Top 30", exact: true }).click()
  await expect(panel.locator("canvas").first()).toBeVisible()
  await page.evaluate(async () => {
    const runtime = await import("/src/chartRuntime.ts")
    const chart = runtime.initChart(document.getElementById("topic-trend")!)
    chart.dispatchAction({ type: "showTip", seriesIndex: 0, dataIndex: 10 })
  })
  const tooltip = page.locator(".chart-tooltip")
  await expect(tooltip).toBeVisible()
  const bounds = await tooltip.evaluate(element => {
    const rect = element.getBoundingClientRect()
    return { left: rect.left, right: rect.right, width: window.innerWidth, height: rect.height, screen: window.innerHeight }
  })
  expect(bounds.left).toBeGreaterThanOrEqual(0)
  expect(bounds.right).toBeLessThanOrEqual(bounds.width)
  expect(bounds.height).toBeLessThan(bounds.screen * .7)
  if (testInfo.project.name === "mobile") {
    expect(bounds.height).toBeLessThanOrEqual(320)
    const first = await tooltip.evaluate(element => element.scrollTop)
    await tooltip.evaluate(element => { element.scrollTop = element.scrollHeight })
    await expect.poll(() => tooltip.evaluate(element => element.scrollTop)).toBeGreaterThan(first)
    await tooltip.evaluate(element => { element.scrollTop = 0 })
  }
  await panel.locator(".analysis-block").screenshot({ path: testInfo.outputPath("trend-tooltip.png") })
})
