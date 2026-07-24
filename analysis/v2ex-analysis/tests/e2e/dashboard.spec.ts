import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

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
  await expect(page.getByRole("button", { name: "数据概览", exact: true })).toHaveClass(/active/)
  await expect(page.getByRole("button", { name: "月度", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "年度", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "区间对比", exact: true })).toHaveCount(0)
  await expect(page.getByLabel("开始月份").locator("option").first()).toHaveAttribute("value", "2010-04")
  await expect(page.getByLabel("结束月份").locator("option").first()).toHaveAttribute("value", "2026-06")
  await expect(page.getByLabel("结束月份").locator("option[value='2026-07']")).toHaveCount(0)
  const rangeLayout = await page.locator(".filter-band").evaluate((filter) => {
    const quickRanges = filter.querySelector(".quick-range-buttons") as HTMLElement
    const buttons = [...quickRanges.querySelectorAll("button")].map((button) => button.getBoundingClientRect())
    return {
      rightGap: Math.round(filter.getBoundingClientRect().right - quickRanges.getBoundingClientRect().right),
      widths: buttons.map((button) => Math.round(button.width)),
    }
  })
  expect(rangeLayout.rightGap).toBeLessThanOrEqual(18)
  expect(new Set(rangeLayout.widths).size).toBe(1)

  await page.getByRole("button", { name: "成员", exact: true }).click()
  await expect(page.locator("#member-evolution canvas").first()).toBeVisible()
  const memberHeatmapWidth = await page.locator("#member-evolution").evaluate((chart) => ({
    chart: Math.round(chart.getBoundingClientRect().width),
    canvas: Math.round(chart.querySelector("canvas")?.getBoundingClientRect().width || 0),
  }))
  expect(memberHeatmapWidth.canvas).toBe(memberHeatmapWidth.chart)
  await expect(page.getByLabel("成员排名数量").locator(".active")).toHaveText("Top 10")
  const memberEvolution = page.locator(".member-evolution-block")
  await expect(memberEvolution.getByRole("heading", { name: "发送帖子", exact: true })).toBeVisible()
  await expect(memberEvolution.getByRole("heading", { name: "发送评论", exact: true })).toBeVisible()
  await expect(memberEvolution.getByRole("heading", { name: "收到感谢", exact: true })).toBeVisible()
  await memberEvolution.getByLabel("成员排名指标").getByRole("button", { name: "评论", exact: true }).click()
  await memberEvolution.locator(".ranked-item").first().click()
  await expect(page.getByRole("heading", { name: /成员详情：/ })).toBeVisible()
  await expect(page.getByRole("button", { name: "成员详情", exact: true })).toHaveClass(/active/)

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
  await expect(page.getByRole("heading", { name: "技术主线仍在，AI、产品实践与生活经验正在重塑社区内容", exact: true })).toBeVisible()
  await expect(page.locator(".observation-item")).toHaveCount(10)
  await expect(page.getByRole("heading", { name: "拼车、会员与订阅正在形成新的社区协作场景", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "收藏与感谢对应两套不同的内容价值", exact: true })).toBeVisible()
  await expect(page.locator(".filter-band")).toHaveCount(0)
  await expect(page.getByRole("link", { name: "官方说明", exact: true })).toHaveAttribute("href", "https://www.v2ex.com/t/1037849")
  const appleObservation = page.locator(".observation-item").filter({ hasText: "Apple 生态是十年间最稳定的社区主线之一" })
  await expect(appleObservation.getByRole("link")).toHaveText(["Apple", "iOS", "Mac", "MacBook", "macOS"])
  const aiObservation = page.locator(".observation-item").filter({ hasText: "AI 讨论从产品名扩展到工具、模型与工作语境" })
  await expect(aiObservation.getByRole("link")).toHaveText(["ChatGPT", "AI", "模型"])
  expect(await aiObservation.getByRole("link").evaluateAll((links) => links.every((link) => link.getAttribute("href")?.includes("view=topic-detail")))).toBe(true)
  const subscriptionObservation = page.locator(".observation-item").filter({ hasText: "拼车、会员与订阅正在形成新的社区协作场景" })
  await expect(subscriptionObservation.getByRole("link")).toHaveText(["拼车", "88vip", "订阅"])
  expect(await subscriptionObservation.getByRole("link").evaluateAll((links) => links.every((link) => link.getAttribute("href")?.includes("view=topic-detail")))).toBe(true)
  const thankedObservation = page.locator(".observation-item").filter({ hasText: "收藏与感谢对应两套不同的内容价值" })
  await expect(thankedObservation.locator(".observation-source")).toHaveText("2018-07-23 00:06 · 主题 #473163")
  await expect(page).toHaveURL(/tab=observations/)

  await appleObservation.getByRole("link", { name: "Apple", exact: true }).click()
  await expect(page.getByRole("heading", { name: "话题详情：Apple", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/tab=content.*tag=Apple/)
  await expect(page).toHaveURL(/view=topic-detail/)

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
  await expect(page.locator("#topic-evolution canvas").first()).toBeVisible()
  const topicHeatmapWidth = await page.locator("#topic-evolution").evaluate((chart) => ({
    chart: Math.round(chart.getBoundingClientRect().width),
    canvas: Math.round(chart.querySelector("canvas")?.getBoundingClientRect().width || 0),
  }))
  expect(topicHeatmapWidth.canvas).toBe(topicHeatmapWidth.chart)
  const topicTrendView = page.getByLabel("话题趋势分析")
  await topicTrendView.getByRole("button", { name: "Top 30", exact: true }).click()
  await expect(topicTrendView.getByLabel("趋势标签数量").locator(".active")).toHaveText("Top 30")
  if ((page.viewportSize()?.width || 0) <= 680) {
    expect(await page.locator("#topic-trend").evaluate((chart) => chart.getBoundingClientRect().height)).toBeGreaterThan(430)
  }
  await page.locator(".ranked-columns .ranked-column").first().locator("button").first().click()
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "热门话题", exact: true })).toHaveCount(0)
  await expect(page.getByLabel("选择话题")).toHaveValue("AI")
  await expect(page.getByRole("button", { name: "话题详情", exact: true })).toHaveClass(/active/)
  await expect(page.getByRole("link", { name: "话题链接", exact: true })).toHaveAttribute("href", /v2ex\.com\/tag\/AI$/)
  await expect(page.getByRole("button", { name: "返回话题演变", exact: true })).toHaveCount(0)
  const actionTops = await page.locator(".topic-detail-actions > *").evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().top)))
  if ((page.viewportSize()?.width || 0) > 680) {
    expect(Math.max(...actionTops) - Math.min(...actionTops)).toBeLessThanOrEqual(1)
  }
  await expect(page).toHaveURL(/view=topic-detail.*tag=AI|tag=AI.*view=topic-detail/)
  await page.reload({ waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.locator("#topic-detail-trend canvas")).toBeVisible()
  await expect(page.locator(".topic-representative-list .post-row").first()).toBeVisible()
  await expect(page.locator(".topic-representative-list .post-row")).toHaveCount(10)
  await expect(page.locator(".topic-representative-list .post-row").first().locator("dl > div")).toHaveCount(4)
  await expect(page.locator(".topic-detail-posts .detail-pagination > span")).toContainText(/共 [\d,]+ 帖 · 第 1/)
  await page.locator(".topic-detail-posts .detail-pagination").getByRole("button", { name: "下一页" }).click()
  await expect(page.locator(".topic-detail-posts .detail-pagination > span")).toContainText("第 2")
  await expect(page).toHaveURL(/topicPage=2/)
  await expect(page.locator(".topic-detail-scope-note")).toContainText("全历史统计")
  await expect(page.locator("#topic-detail .ranked-column")).toHaveCount(3)
  await expect(page.locator("#topic-detail .ranked-item")).toHaveCount(60)
  await expect(page.getByRole("button", { name: "代表帖子", exact: true })).toHaveCount(0)
  await expect(page.locator(".representative-note")).toContainText("promotions")
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.documentWidth).toBe(dimensions.viewport)
  expect(new Set(detailRequests).size).toBe(1)
})

test("restores a limited member profile from URL and browser history", async ({ page }) => {
  await page.goto("/?tab=community&member=Livid", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "成员详情：Livid", exact: true })).toBeVisible()
  await expect(page.locator("#member-profile-trend canvas")).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要发帖节点", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要评论节点", exact: true })).toBeVisible()
  await expect(page.getByLabel("选择成员")).toHaveValue("Livid")
  await page.getByLabel("选择成员").fill("loving29cn")
  await expect(page.getByRole("option", { name: /loving29cn/i })).toBeVisible()
  await page.getByRole("option", { name: /loving29cn/i }).click()
  await expect(page.getByRole("heading", { name: "成员详情：loving29cn", exact: true })).toBeVisible()
  await page.getByLabel("选择成员").fill("Livid")
  await page.getByRole("option", { name: /^Livid/ }).click()
  await expect(page.locator("#member-profile > header p")).toContainText("仅显示部分活跃成员")
  await expect(page.getByRole("button", { name: "返回成员演变", exact: true })).toHaveCount(0)
  await expect(page.locator(".member-profile-posts > a")).toHaveCount(10)
  await expect(page.locator(".member-profile-posts > header")).toHaveCSS("border-bottom-style", "solid")
  await page.locator(".member-profile-posts").getByRole("button", { name: "显示全部 20 条" }).click()
  await expect(page.locator(".member-profile-posts > a")).toHaveCount(20)
  await expect(page.locator(".member-profile-comments .comment-ranking-row")).toHaveCount(10)
  await expect(page.locator(".member-profile-comments > header")).toHaveCSS("border-bottom-width", "1px")
  await expect(page.locator(".member-comment-list")).toHaveCSS("border-top-width", "0px")
  await expect(page.locator(".member-profile-scope-note")).toContainText("至少获得 1 次感谢")
  await page.locator(".member-profile-comments").getByRole("button", { name: "显示全部 20 条" }).click()
  await expect(page.locator(".member-profile-comments .comment-ranking-row")).toHaveCount(20)

  await page.getByRole("button", { name: "互动", exact: true }).click()
  await expect(page).toHaveURL(/tab=engagement/)
  await page.goBack()
  await expect(page.getByRole("heading", { name: "成员详情：Livid", exact: true })).toBeVisible()
  await expect(page).toHaveURL(/tab=community.*member=Livid|member=Livid.*tab=community/)

  await page.goto("/?tab=community&from=2016-07&to=2026-06&member=loving29cn", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "成员详情：loving29cn", exact: true })).toBeVisible()
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

test("defaults monthly data to the latest complete month without loading charts", async ({ page }) => {
  const chartRequests: string[] = []
  const activityRequests: string[] = []
  page.on("request", request => {
    if (request.url().includes("chartRuntime") || request.url().includes("echarts")) chartRequests.push(request.url())
    if (request.url().includes("dynamic-overview-activity.json")) activityRequests.push(request.url())
  })

  await page.goto("/?overview=month", { waitUntil: "networkidle" })
  await expect(page.getByLabel("选择月份")).toHaveValue("2026-06")
  await expect(page.getByLabel("选择月份").locator("option").first()).toHaveAttribute("value", "2026-06")
  expect(chartRequests).toEqual([])
  expect(activityRequests).toEqual([])
})

test("shows exact annual profiles and defaults to a sufficiently complete current year", async ({ page }) => {
  const dataRequests: string[] = []
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (name.startsWith("dynamic-") && name.endsWith(".json")) dataRequests.push(name)
  })
  await page.goto("/?overview=year", { waitUntil: "networkidle" })
  const annualView = page.getByLabel("年度", { exact: true })
  await expect(page.getByLabel("选择年份")).toHaveValue("2026")
  await expect(annualView.getByRole("heading", { name: /2026 年数据.*截至 6 月/ })).toBeVisible()
  await expect(annualView.locator(".monthly-metrics .metric")).toHaveCount(8)
  await expect(annualView.locator(".ranked-columns")).toHaveCSS("background-color", "rgb(255, 255, 255)")
  await expect(annualView.locator(".monthly-posts .content-list-row")).toHaveCount(10)
  await expect.poll(() => dataRequests).toContain("dynamic-annual-ranking-2026.json")
  expect(dataRequests).not.toContain("dynamic-overview-activity.json")
  expect(dataRequests).not.toContain("dynamic-annual-ranking-2025.json")

  await page.getByLabel("选择年份").selectOption("2025")
  await expect(annualView.getByRole("heading", { name: "2025 年数据", exact: true })).toBeVisible()
  await expect.poll(() => dataRequests).toContain("dynamic-annual-ranking-2025.json")
  await expect(page).toHaveURL(/overview=year.*period=2025|period=2025.*overview=year/)
})

test("rejects incomplete URL ranges while preserving single-month analysis", async ({ page }) => {
  await page.goto("/?from=2021-07&to=2026-07", { waitUntil: "domcontentloaded" })
  await expect(page.getByLabel("开始月份")).toHaveValue("2021-07")
  await expect(page.getByLabel("结束月份")).toHaveValue("2026-06")
  await expect(page).not.toHaveURL(/to=2026-07/)

  await page.goto("/?from=2026-06&to=2026-06", { waitUntil: "domcontentloaded" })
  await expect(page.getByLabel("开始月份")).toHaveValue("2026-06")
  await expect(page.getByLabel("结束月份")).toHaveValue("2026-06")
})

test("normalizes malicious and unknown URL state", async ({ page }) => {
  await page.goto("/?tab=content&tag=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E&topicTop=20junk", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: /话题详情：/ })).toHaveCount(0)
  await expect(page).not.toHaveURL(/tag=|topicTop=/)

  await page.goto("/?tab=community&member=javascript%3Aalert(1)", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: /成员详情：/ })).toHaveCount(0)
  await expect(page).not.toHaveURL(/member=/)

  await page.goto("/?tab=content&view=node-detail&node=javascript%3Aalert(1)", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: /节点详情：/ })).toBeVisible()
  await expect(page).not.toHaveURL(/javascript%3A|javascript:/i)

  await page.goto("/?tab=content&tag=definitely-not-a-real-dashboard-tag", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: /话题详情：/ })).toHaveCount(0)
  await expect(page).not.toHaveURL(/tag=/)

  await page.goto("/?tab=content&view=posts&tag=AI", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page).not.toHaveURL(/view=posts/)
})

test("restores and navigates the monthly data view", async ({ page }) => {
  const dataRequests: string[] = []
  const moduleRequests: string[] = []
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (name.startsWith("dynamic-") && name.endsWith(".json")) dataRequests.push(name)
    if (request.url().includes("chartRuntime") || request.url().includes("echarts")) moduleRequests.push(request.url())
  })
  await page.goto("/?overview=month&period=2026-02", { waitUntil: "domcontentloaded" })
  const monthlyView = page.getByLabel("月度", { exact: true })
  await expect(monthlyView.getByRole("heading", { name: "2026 年 2 月数据", exact: true })).toBeVisible()
  await expect(page.locator(".filter-band")).toHaveCount(0)
  await expect(monthlyView.locator(".monthly-metrics .metric")).toHaveCount(8)
  await expect(monthlyView.getByText("热门话题", { exact: true })).toBeVisible()
  await expect(monthlyView.getByText("热门节点", { exact: true })).toBeVisible()
  await expect(monthlyView.getByText("活跃用户", { exact: true })).toBeVisible()
  await expect(monthlyView.locator(".ranked-item")).toHaveCount(60)
  await expect(monthlyView.locator(".ranked-columns")).toHaveCSS("background-color", "rgb(255, 255, 255)")
  await expect(monthlyView.locator(".monthly-posts .content-list-row")).toHaveCount(10)
  await expect(monthlyView.locator(".monthly-post-pagination > span")).toHaveText("Top 100 · 第 1 / 10 页")
  await monthlyView.getByLabel("月度代表帖子排序指标").getByRole("button", { name: "收藏", exact: true }).click()
  await expect(monthlyView.locator(".monthly-posts .content-list-row").first().locator("em")).toContainText("收藏")
  await monthlyView.getByRole("navigation", { name: "月度代表帖子分页" }).getByRole("button", { name: "2", exact: true }).click()
  await expect(monthlyView.locator(".monthly-post-pagination > span")).toHaveText("Top 100 · 第 2 / 10 页")
  await expect(monthlyView.getByRole("heading", { name: "代表评论", exact: true })).toBeVisible()
  await expect(monthlyView.locator(".monthly-comments > a")).toHaveCount(10)
  await expect(monthlyView.locator(".monthly-comment-pagination > span")).toHaveText("Top 100 · 第 1 / 10 页")
  await monthlyView.getByRole("navigation", { name: "月度代表评论分页" }).getByRole("button", { name: "2", exact: true }).click()
  await expect(monthlyView.locator(".monthly-comment-pagination > span")).toHaveText("Top 100 · 第 2 / 10 页")
  await expect(page.getByLabel("选择月份")).toHaveValue("2026-02")
  await expect(page.getByLabel("选择月份").locator("option").first()).toHaveAttribute("value", "2026-06")
  await expect(page.getByLabel("选择月份").locator("option[value='2026-07']")).toHaveCount(0)
  expect(dataRequests).toContain("dynamic-monthly-ranking-2026-02.json")
  expect(dataRequests).not.toContain("dynamic-monthly-ranking-2026-03.json")
  expect(dataRequests).not.toContain("dynamic-topics.json")
  expect(dataRequests).not.toContain("dynamic-nodes.json")
  expect(dataRequests).not.toContain("dynamic-community.json")
  expect(moduleRequests).toEqual([])

  await page.getByRole("button", { name: "下个月", exact: true }).click()
  await expect(monthlyView.getByRole("heading", { name: "2026 年 3 月数据", exact: true })).toBeVisible()
  await expect.poll(() => dataRequests).toContain("dynamic-monthly-ranking-2026-03.json")
  await expect(page).toHaveURL(/overview=month.*period=2026-03|period=2026-03.*overview=month/)

  await page.getByLabel("选择月份").selectOption("2024-05")
  await expect(monthlyView.getByRole("heading", { name: "2024 年 5 月数据", exact: true })).toBeVisible()
  await expect(monthlyView.getByText("当月事件", { exact: true })).toBeVisible()

  const topic = (await monthlyView.locator(".ranked-column").first().locator("button strong").first().textContent()) || ""
  await monthlyView.locator(".ranked-column").first().locator("button").first().click()
  await expect(page.getByRole("heading", { name: `话题详情：${topic}`, exact: true })).toBeVisible()
  await expect(page).toHaveURL(/tab=content.*tag=|tag=.*tab=content/)
})

test("loads a searchable node detail shard and supports internal drill-down", async ({ page }) => {
  const detailRequests: string[] = []
  page.on("request", request => {
    if (/dynamic-node-details-[0-9a-f]\.json/.test(request.url())) detailRequests.push(request.url())
  })
  await page.goto("/?tab=content&view=node-detail&node=programmer", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: /节点详情：程序员/ })).toBeVisible()
  await expect(page.locator("#node-detail-trend canvas")).toBeVisible()
  await expect(page.locator("#node-detail .ranked-column")).toHaveCount(2)
  await expect(page.locator(".node-detail-posts .post-row")).toHaveCount(10)
  const nodePostPagination = page.getByRole("navigation", { name: "节点代表帖子分页" })
  await expect(page.locator(".node-detail-posts .ranking-pagination > span")).toHaveText("共 100 帖 · 第 1 / 10 页")
  const firstPostHref = await page.locator(".node-detail-posts .post-row .post-main > a").first().getAttribute("href")
  await nodePostPagination.getByRole("button", { name: "2", exact: true }).click()
  await expect(page.locator(".node-detail-posts .ranking-pagination > span")).toHaveText("共 100 帖 · 第 2 / 10 页")
  await expect(page.locator(".node-detail-posts .post-row")).toHaveCount(10)
  expect(await page.locator(".node-detail-posts .post-row .post-main > a").first().getAttribute("href")).not.toBe(firstPostHref)
  expect(new Set(detailRequests).size).toBe(1)
  const accessibility = await new AxeBuilder({ page }).analyze()
  expect(accessibility.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""))).toEqual([])

  await page.getByLabel("选择节点").fill("问与答")
  await page.getByRole("option", { name: /问与答/ }).click()
  await expect(page.getByRole("heading", { name: /节点详情：问与答/ })).toBeVisible()
  await expect(page.locator(".node-detail-posts .ranking-pagination > span")).toHaveText("共 100 帖 · 第 1 / 10 页")
  await expect(page).toHaveURL(/view=node-detail.*node=qna|node=qna.*view=node-detail/)

  const firstTag = page.locator("#node-detail .ranked-column").first().getByRole("button").first()
  const tag = (await firstTag.locator("strong").textContent()) || ""
  await firstTag.click()
  await expect(page.getByRole("heading", { name: `话题详情：${tag}`, exact: true })).toBeVisible()
})

test("has no serious accessibility violations in the core dashboard", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact || ""))).toEqual([])
})

test("keeps responsive header and filter visuals stable", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  await expect(page.locator(".dashboard-header")).toHaveScreenshot("dashboard-header.png", { animations: "disabled" })
  await expect(page.locator(".filter-band")).toHaveScreenshot("dashboard-filter.png", { animations: "disabled" })
})
