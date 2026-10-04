import { expect, test } from "@playwright/test"
import { trendTable } from "../../src/utils/trendTable"

test("keeps missing values distinct from zero in the trend table", () => {
  expect(trendTable(undefined)).toEqual({ columns: [], rows: [] })
  expect(trendTable({ xAxis: [{ data: ["2024-01", "2024-02"] }], series: [
    { type: "line", name: "AI", data: [0, { value: 2 }] },
    { type: "line", name: "Python", data: [null, 3] },
  ] })).toEqual({ columns: ["AI", "Python"], rows: [
    { period: "2024-02", values: [2, 3] }, { period: "2024-01", values: [0, null] },
  ] })
})

test("fills an open table when the chart runtime arrives late", async ({ page }) => {
  const errors: string[] = []
  page.on("pageerror", error => errors.push(error.message))
  let release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route("**/src/chartRuntime.ts*", async route => {
    await pending
    await route.continue()
  })
  await page.goto("/?tab=content&view=topic-detail&tag=AI&from=2024-01&to=2025-12", { waitUntil: "domcontentloaded" })
  try {
    await page.locator(".trend-data summary").click()
    await expect(page.locator("#topic-detail-trend canvas")).toHaveCount(0)
  } finally {
    release()
  }
  await expect(page.locator(".trend-data tbody tr")).toHaveCount(24)
  expect(errors).toEqual([])
})

for (const [view, key, label] of [
  ["topic-detail", "tag", "搜索对比话题"],
  ["content-detail", "term", "搜索对比关键词"],
]) {
  test(`refreshes the open table with comparisons and grain in ${view}`, async ({ page }) => {
    await page.goto(`/?tab=content&view=${view}&${key}=AI&from=2024-01&to=2025-12`)
    const table = page.locator(".trend-data")
    await table.locator("summary").click()
    await expect(table.locator("tbody tr")).toHaveCount(24)
    await page.getByRole("button", { name: "添加对比", exact: true }).click()
    await page.getByRole("combobox", { name: label }).fill("Python")
    await page.getByRole("option", { name: /^Python(?:\s|$)/ }).click()
    await expect(table.locator("thead th")).toHaveText(["时间", "AI", "Python"])
    const mobileFilters = page.locator(".mobile-filter-summary")
    if (await mobileFilters.isVisible()) await mobileFilters.click()
    await page.getByRole("button", { name: "年", exact: true }).click()
    await expect(table.locator("tbody tr")).toHaveCount(2)
    await page.getByRole("button", { name: "移除对比 Python", exact: true }).click()
    await expect(table.locator("thead th")).toHaveText(["时间", "AI"])
  })
}

for (const [view, entity, parameter, periodKey] of [
  ["topic-detail", "AI", "tag", "topicPeriod"],
  ["content-detail", "AI", "term", "contentPeriod"],
  ["node-detail", "qna", "node", "nodePeriod"],
]) {
  test(`offers keyboard period selection in ${view}`, async ({ page }) => {
    await page.goto(`/?tab=content&view=${view}&${parameter}=${entity}&from=2024-01&to=2025-12&grain=month`)
    const disclosure = page.locator(".trend-data")
    await expect(disclosure).toBeVisible()
    await expect(disclosure.locator("table")).toHaveCount(0)
    await disclosure.locator("summary").focus()
    await page.keyboard.press("Enter")
    await expect(disclosure.locator("tbody tr")).toHaveCount(24)
    const period = disclosure.getByRole("button", { name: "2025-12 代表帖子", exact: true })
    await period.focus()
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(new RegExp(`${periodKey}=2025-12`))
    await expect(period).toHaveAttribute("aria-pressed", "true")
    await page.keyboard.press("Enter")
    await expect(page).not.toHaveURL(new RegExp(`${periodKey}=`))
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
