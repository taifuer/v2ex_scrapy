import { expect, test } from "@playwright/test"

test("renders event markers on a direct first visit without loading the presentation", async ({ page }) => {
  const requested: string[] = []
  page.on("request", request => requested.push(request.url()))
  await page.goto("/?from=2022-01&to=2025-12")
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  const marker = await page.evaluate(async () => {
    const { chartFor } = await import("/src/chartRuntime.ts")
    const chart = chartFor(document.getElementById("overview-trend")!)
    return chart?.getZr().storage.getDisplayList().some((item: any) => String(item.style?.text || "").includes("邀请码启用"))
  })
  expect(marker).toBe(true)
  expect(requested.some(url => url.includes("presentationCharts"))).toBe(false)
})
