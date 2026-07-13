import { expect, test } from "@playwright/test"

test("loads core views without runtime or layout errors", async ({ page }) => {
  const errors: string[] = []
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text())
  })
  page.on("pageerror", error => errors.push(error.message))

  await page.goto("/", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  await expect(page.locator(".data-scope")).toHaveText(/数据范围：\d{4}-\d{2} 至 \d{4}-\d{2}/)
  await expect(page.locator(".data-scope")).toContainText("位成员")
  await expect(page.locator(".data-scope")).toContainText("个帖子")
  await expect(page.locator(".data-scope")).toContainText("条评论")

  await page.getByRole("button", { name: "成员", exact: true }).click()
  await expect(page.locator("#member-evolution canvas")).toBeVisible()
  await expect(page.getByLabel("成员排名数量").locator(".active")).toHaveText("Top 10")

  await page.getByRole("button", { name: "互动", exact: true }).click()
  await expect(page.getByRole("heading", { name: "热门帖", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "热门评论", exact: true })).toBeVisible()
  await expect(page.getByLabel("热门帖排序指标").locator(".active")).toHaveText("收藏")
  await expect(page.locator(".interaction-ranking").nth(0).locator(".ranking-pagination > span")).toHaveText("Top 200 · 第 1 / 20 页")
  await expect(page.locator(".interaction-ranking").nth(1).locator(".ranking-pagination > span")).toHaveText("Top 500 · 第 1 / 50 页")
  await page.getByRole("navigation", { name: "热门评论分页" }).getByRole("button", { name: "50", exact: true }).click()
  await expect(page.locator(".interaction-ranking").nth(1).locator(".ranking-pagination > span")).toHaveText("Top 500 · 第 50 / 50 页")
  await expect(page.locator(".interaction-ranking").getByText("榜单范围")).toHaveCount(0)

  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.documentWidth).toBe(dimensions.viewport)
  expect(errors).toEqual([])
})

test("filters representative posts and loads topic detail shard", async ({ page }) => {
  const detailRequests: string[] = []
  page.on("request", request => {
    if (request.url().includes("dynamic-tag-details-")) detailRequests.push(request.url())
  })

  await page.goto("/", { waitUntil: "domcontentloaded" })
  await page.getByRole("button", { name: "帖子", exact: true }).click()
  await page.locator(".topic-evolution-analysis section").first().locator("button").first().click()
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.locator("#topic-detail-trend canvas")).toBeVisible()
  await expect(page.locator(".topic-detail-posts > a").first()).toBeVisible()
  await expect(page.locator(".topic-detail-scope-note")).toContainText("全历史统计")
  await expect(page.getByRole("heading", { name: "活跃用户（全历史）", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "代表帖子", exact: true })).not.toHaveClass(/active/)

  await page.getByRole("button", { name: "查看代表帖子", exact: true }).click()
  await expect(page.getByRole("button", { name: "代表帖子", exact: true })).toHaveClass(/active/)

  await expect(page.locator(".post-row").first()).toBeVisible()
  await page.getByLabel("标签").selectOption("AI")
  await expect(page.locator(".post-pagination > span")).toContainText(/共 [\d,]+ 帖/)
  await expect(page.locator(".section-toolbar p")).toContainText("全站 Top 30")
  await expect(page.locator(".representative-note")).toContainText("promotions")

  await page.getByRole("button", { name: "话题演变", exact: true }).click()
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.locator(".topic-detail-columns section")).toHaveCount(3)
  expect(await page.locator(".topic-detail-posts > a").count()).toBeGreaterThan(0)
  expect(new Set(detailRequests).size).toBe(1)
})
