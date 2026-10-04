import { test, expect } from "@playwright/test"

test("renders synthetic aggregates and restores detail URL state", async ({ page }) => {
  const manifest = await (await page.request.get("/dynamic-manifest.json")).json()
  expect(manifest.dataset_kind).toBe("synthetic")
  const errors: string[] = []
  page.on("pageerror", error => errors.push(error.message))
  for (const [path, selector] of [
    ["/", "#overview-trend canvas"],
    ["/?tab=content&view=topics", "#topic-evolution canvas"],
    ["/?tab=content&view=content-evolution", "#content-hotspot-heatmap canvas"],
    ["/?tab=content&view=node-detail&node=qna", "#node-detail-trend canvas"],
    ["/?tab=community", "#member-roles canvas"],
    ["/?tab=engagement", "#engagement-volume canvas"],
  ]) {
    await page.goto(path)
    await expect(page.locator(selector).first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.goto("/?tab=content&view=content-detail&term=AI&grain=month&from=2024-01&to=2024-12&contentPeriod=2024-06")
  await expect(page.locator("#content-term-trend canvas")).toBeVisible()
  await expect(page.locator(".content-representative-list .post-row")).not.toHaveCount(0)
  await expect(page.locator(".entity-representative-comments .comment-ranking-row")).not.toHaveCount(0)
  await page.reload()
  await expect(page.locator("#content-term-trend")).toHaveAttribute("data-selected-period", "2024-06")
  expect(errors).toEqual([])
})
