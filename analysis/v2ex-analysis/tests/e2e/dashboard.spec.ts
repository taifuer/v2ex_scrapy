import { expect, test } from "@playwright/test"

test("loads core views without runtime or layout errors", async ({ page }) => {
  const errors: string[] = []
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text())
  })
  page.on("pageerror", error => errors.push(error.message))

  await page.goto("/", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  await expect(page.locator(".data-scope")).toContainText("（进行中）")
  await expect(page.locator(".data-scope")).toContainText("默认分析截至")

  await page.getByRole("button", { name: "成员", exact: true }).click()
  await expect(page.locator("#member-evolution canvas")).toBeVisible()
  await expect(page.getByLabel("成员排名数量").locator(".active")).toHaveText("Top 10")

  await page.getByRole("button", { name: "互动", exact: true }).click()
  await expect(page.getByRole("heading", { name: "热门帖", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "热门评论", exact: true })).toBeVisible()

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.documentWidth).toBe(dimensions.viewport)
  expect(errors).toEqual([])
})

test("loads tag-specific posts and topic detail shard", async ({ page }) => {
  const detailRequests: string[] = []
  page.on("request", request => {
    if (request.url().includes("dynamic-tag-details-")) detailRequests.push(request.url())
  })

  await page.goto("/", { waitUntil: "domcontentloaded" })
  await page.getByRole("button", { name: "帖子", exact: true }).click()
  await page.getByRole("button", { name: "代表帖子", exact: true }).click()
  await expect(page.locator(".post-row").first()).toBeVisible()
  await page.getByLabel("标签").selectOption("AI")
  await expect(page.locator(".post-pagination > span")).toContainText(/共 [\d,]+ 帖/)
  await expect(page.locator(".section-toolbar p")).toContainText("每年独立 Top 5")

  await page.getByRole("button", { name: "话题演变", exact: true }).click()
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.locator(".topic-detail-columns section")).toHaveCount(3)
  expect(await page.locator(".topic-detail-posts > a").count()).toBeGreaterThan(0)
  expect(new Set(detailRequests).size).toBe(1)
})
