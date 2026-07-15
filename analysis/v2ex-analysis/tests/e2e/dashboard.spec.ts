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
  const memberEvolution = page.locator(".member-evolution-block")
  await expect(memberEvolution.getByRole("heading", { name: "发送帖子最多", exact: true })).toBeVisible()
  await expect(memberEvolution.getByRole("heading", { name: "发送评论最多", exact: true })).toBeVisible()
  await expect(memberEvolution.getByRole("heading", { name: "收到感谢最多", exact: true })).toBeVisible()
  await memberEvolution.locator(".member-rank-row").first().click()
  await expect(page.getByRole("heading", { name: /成员参与画像：/ })).toBeVisible()

  await page.getByRole("button", { name: "互动", exact: true }).click()
  await expect(page.getByRole("heading", { name: "热门帖子", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "热门评论", exact: true })).toBeVisible()
  await expect(page.getByLabel("热门帖子排序指标").locator(".active")).toHaveText("收藏")
  await expect(page.locator(".interaction-ranking").nth(0).locator(".ranking-pagination > span")).toHaveText("Top 200 · 第 1 / 20 页")
  await expect(page.locator(".interaction-ranking").nth(1).locator(".ranking-pagination > span")).toHaveText("Top 500 · 第 1 / 50 页")
  await page.getByRole("navigation", { name: "热门评论分页" }).getByRole("button", { name: "50", exact: true }).click()
  await expect(page.locator(".interaction-ranking").nth(1).locator(".ranking-pagination > span")).toHaveText("Top 500 · 第 50 / 50 页")
  await expect(page.locator(".interaction-ranking").getByText("榜单范围")).toHaveCount(0)
  await expect(page.locator(".dashboard-footer-inner")).toContainText(`© ${new Date().getFullYear()}`)

  await page.getByRole("button", { name: "观察", exact: true }).click()
  await expect(page.getByRole("heading", { name: "十年社区进入存量阶段，话题与内容偏好出现清晰迁移", exact: true })).toBeVisible()
  await expect(page.locator(".observation-item")).toHaveCount(10)
  await expect(page.locator(".filter-band")).toHaveCount(0)
  await expect(page.getByRole("link", { name: "官方说明", exact: true })).toHaveAttribute("href", "https://www.v2ex.com/t/1037849")
  const appleObservation = page.locator(".observation-item").filter({ hasText: "Apple 生态是十年间最稳定的社区主线之一" })
  await expect(appleObservation.getByRole("link")).toHaveText(["Apple", "iOS", "Mac", "MacBook", "macOS"])
  const aiObservation = page.locator(".observation-item").filter({ hasText: "ChatGPT、AI 与“模型”构成三轮话题浪潮" })
  expect(await aiObservation.getByRole("link").evaluateAll((links) => links.every((link) => link.getAttribute("href")?.endsWith("#topic-detail")))).toBe(true)
  const languageObservation = page.locator(".observation-item").filter({ hasText: "Java 与 Python 的标签热度已持续离开高位" })
  await expect(languageObservation.getByRole("link")).toHaveText(["Java", "Python"])
  expect(await languageObservation.getByRole("link").evaluateAll((links) => links.every((link) => link.getAttribute("href")?.endsWith("#topic-detail")))).toBe(true)
  const thankedObservation = page.locator(".observation-item").filter({ hasText: "感谢榜首来自一次公共事件调查" })
  await expect(thankedObservation.locator(".observation-source")).toHaveText("2018-07-23 00:06 · 主题 #473163")
  await expect(page).toHaveURL(/tab=observations/)

  await appleObservation.getByRole("link", { name: "Apple", exact: true }).click()
  await expect(page.getByRole("heading", { name: "话题详情：Apple", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/tab=content.*tag=Apple/)
  await expect(page).not.toHaveURL(/#topic-detail/)
  const topicDetailTop = await page.locator("#topic-detail").evaluate((element) => element.getBoundingClientRect().top)
  expect(Math.abs(topicDetailTop)).toBeLessThanOrEqual(24)

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
  await expect(page.getByRole("link", { name: "话题链接", exact: true })).toHaveAttribute("href", /v2ex\.com\/tag\/AI$/)
  await expect(page.getByRole("button", { name: "关闭", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/tab=content.*tag=AI|tag=AI.*tab=content/)
  await page.reload({ waitUntil: "domcontentloaded" })
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

test("restores a limited member profile from URL and browser history", async ({ page }) => {
  await page.goto("/?tab=community&member=Livid", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "成员参与画像：Livid", exact: true })).toBeVisible()
  await expect(page.locator("#member-profile-trend canvas")).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要发帖节点", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要评论节点", exact: true })).toBeVisible()

  await page.getByRole("button", { name: "互动", exact: true }).click()
  await expect(page).toHaveURL(/tab=engagement/)
  await page.goBack()
  await expect(page.getByRole("heading", { name: "成员参与画像：Livid", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/tab=community.*member=Livid|member=Livid.*tab=community/)

  await page.goto("/?tab=community&from=2016-07&to=2026-06&member=loving29cn", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "成员参与画像：loving29cn", exact: true })).toBeVisible()
  await expect(page.locator(".member-profile-metrics .metric").nth(0).locator("strong")).toHaveText("25")
  await expect(page.locator(".member-profile-metrics .metric").nth(1).locator("strong")).toHaveText("63")
  const linePixels = await page.locator("#member-profile-trend canvas").evaluate((canvas: HTMLCanvasElement) => {
    const pixels = canvas.getContext("2d")?.getImageData(0, 0, canvas.width, canvas.height).data || []
    let blue = 0
    let red = 0
    for (let index = 0; index < pixels.length; index += 4) {
      if (Math.abs(pixels[index] - 37) < 8 && Math.abs(pixels[index + 1] - 99) < 8 && Math.abs(pixels[index + 2] - 235) < 8) blue += 1
      if (Math.abs(pixels[index] - 217) < 8 && Math.abs(pixels[index + 1] - 72) < 8 && Math.abs(pixels[index + 2] - 65) < 8) red += 1
    }
    return { blue, red }
  })
  expect(linePixels.blue).toBeGreaterThan(10)
  expect(linePixels.red).toBeGreaterThan(10)
})
