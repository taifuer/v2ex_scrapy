import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { readFileSync } from "node:fs"

const overviewMetadata = JSON.parse(
  readFileSync("public/dynamic-overview.json", "utf8"),
).metadata as { default_end_period: string }
const latestCompleteMonth = overviewMetadata.default_end_period

function shiftMonth(period: string, offset: number) {
  const [year, month] = period.split("-").map(Number)
  const index = year * 12 + month - 1 + offset
  return `${Math.floor(index / 12)}-${String(index % 12 + 1).padStart(2, "0")}`
}

const nextIncompleteMonth = shiftMonth(latestCompleteMonth, 1)

test("loads core views without runtime or layout errors", async ({ page }) => {
  const errors: string[] = []
  page.on("console", message => {
    if (message.type() === "error") errors.push(message.text())
  })
  page.on("pageerror", error => errors.push(error.message))

  await page.goto("/", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  await expect(page.getByRole("heading", { name: "社区规模与参与", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "帖子互动反馈", exact: true })).toBeVisible()
  await expect(page.locator("#overview-participation canvas")).toBeVisible()
  await expect(page.getByRole("heading", { name: "活跃时段", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "评论", exact: true })).toHaveAttribute("aria-pressed", "true")
  const activityHeatmap = page.locator("#activity-heatmap")
  await expect(activityHeatmap).toHaveAttribute("data-metric", "comments")
  await page.getByRole("button", { name: "发帖", exact: true }).click()
  await expect(page.getByRole("button", { name: "发帖", exact: true })).toHaveAttribute("aria-pressed", "true")
  await expect(activityHeatmap).toHaveAttribute("data-metric", "topics")
  await expect(page.locator(".data-scope")).toHaveText(/数据范围：\d{4}-\d{2} 至 \d{4}-\d{2}/)
  await expect(page.locator(".data-scope")).toContainText("成员")
  await expect(page.locator(".data-scope")).toContainText("帖子")
  await expect(page.locator(".data-scope")).toContainText("评论")
  await expect(page.getByRole("tab", { name: "数据概览", exact: true })).toHaveClass(/active/)
  await expect(page.getByRole("tab", { name: "月度", exact: true })).toBeVisible()
  await expect(page.getByRole("tab", { name: "年度", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "区间对比", exact: true })).toHaveCount(0)
  await expect(page.getByText("指标口径", { exact: true })).toHaveCount(0)
  await expect(page.getByLabel("开始月份").locator("option").first()).toHaveAttribute("value", "2010-04")
  await expect(page.getByLabel("结束月份").locator("option").first()).toHaveAttribute("value", latestCompleteMonth)
  await expect(page.getByLabel("结束月份").locator(`option[value='${nextIncompleteMonth}']`)).toHaveCount(0)
  if ((page.viewportSize()?.width || 0) <= 680) {
    await page.locator(".mobile-filter-summary").click()
  }
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
  await expect(page.getByLabel("成员排名数量").locator(".active")).toHaveText("Top 20")
  await expect(page.locator("#member-evolution")).toHaveCSS("height", "712px")
  const memberEvolution = page.locator(".member-evolution-block")
  await expect(memberEvolution.getByRole("heading", { name: "发送帖子", exact: true })).toBeVisible()
  await expect(memberEvolution.getByRole("heading", { name: "发送评论", exact: true })).toBeVisible()
  await expect(memberEvolution.getByRole("heading", { name: "收到感谢", exact: true })).toBeVisible()
  await memberEvolution.getByLabel("成员排名指标").getByRole("button", { name: "评论", exact: true }).click()
  await memberEvolution.locator(".ranked-item").first().click()
  await expect(page.getByRole("heading", { name: /成员详情：/ })).toBeVisible()
  await expect(page.getByRole("tab", { name: "成员详情", exact: true })).toHaveClass(/active/)

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
  await expect(page.getByRole("heading", { name: "技术主线仍在，AI 工具、数字协作与生活经验正在重塑社区讨论", exact: true })).toBeVisible()
  await expect(page.locator(".observation-item")).toHaveCount(10)
  await expect(page.getByRole("heading", { name: "拼车、会员与订阅正在形成新的社区协作场景", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "收藏与感谢对应两套不同的内容价值", exact: true })).toBeVisible()
  await expect(page.locator(".filter-band")).toHaveCount(0)
  await expect(page.getByRole("link", { name: "官方说明", exact: true })).toHaveAttribute("href", "https://www.v2ex.com/t/1037849")
  const appleObservation = page.locator(".observation-item").filter({ hasText: "Apple 生态是十年间最稳定的社区主线之一" })
  await expect(appleObservation.getByRole("link")).toHaveText(["Apple", "iOS", "Mac", "MacBook", "macOS"])
  const aiObservation = page.locator(".observation-item").filter({ hasText: "AI 讨论从聊天产品扩展到模型与编码智能体" })
  await expect(aiObservation.getByRole("link")).toHaveText(["AI", "Codex", "Claude Code", "Agent"])
  await expect(aiObservation.getByRole("link", { name: "AI", exact: true })).toHaveAttribute("href", /view=topic-detail/)
  expect(await aiObservation.getByRole("link").evaluateAll((links) => links.slice(1).every((link) => link.getAttribute("href")?.includes("view=content-detail")))).toBe(true)
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
  await expect(topicTrendView.getByLabel("趋势话题数量").locator(".active")).toHaveText("Top 30")
  if ((page.viewportSize()?.width || 0) <= 680) {
    expect(await page.locator("#topic-trend").evaluate((chart) => chart.getBoundingClientRect().height)).toBeGreaterThan(430)
  }
  await page.locator(".ranked-columns .ranked-column").first().locator("button").first().click()
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible({ timeout: 10_000 })
  await expect(page.getByRole("heading", { name: "关联话题", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "热门话题", exact: true })).toHaveCount(0)
  await expect(page.getByLabel("选择话题")).toHaveValue("AI")
  await expect(page.getByRole("tab", { name: "话题详情", exact: true })).toHaveClass(/active/)
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

test("shows comparable seven-day discussion structure metrics", async ({ page }) => {
  await page.goto("/?tab=content&view=lifecycle", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "帖子生命周期", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "讨论结构", exact: true })).toBeVisible()
  await expect(page.getByText("平均参与用户", { exact: true })).toBeVisible()
  await expect(page.getByText("楼主参与讨论", { exact: true })).toBeVisible()
  await expect(page.locator("#discussion-structure-trend canvas")).toBeVisible()
  await expect(page.locator("article.analysis-block h2")).toHaveText([
    "讨论强度",
    "讨论结构",
    "回复速度",
  ])
})

test("loads topic detail without global topic rows or representative payload", async ({ page }) => {
  const dataRequests: string[] = []
  const dataUrls: URL[] = []
  page.on("request", request => {
    const url = new URL(request.url())
    const name = url.pathname.split("/").pop() || ""
    if (name.startsWith("dynamic-") && name.endsWith(".json")) {
      dataRequests.push(name)
      dataUrls.push(url)
    }
  })
  await page.goto("/?tab=content&view=topic-detail&tag=AI", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.locator("#topic-detail-trend canvas")).toBeVisible()
  expect(dataRequests.some(name => name.startsWith("dynamic-tag-details-"))).toBe(true)
  expect(dataRequests.some(name => name.startsWith("dynamic-topic-rows-"))).toBe(false)
  expect(dataRequests).not.toContain("dynamic-representative-posts.json")
  expect(dataUrls.every(url => /^[a-f0-9]{12}$/.test(url.searchParams.get("v") || ""))).toBe(true)
})

test("compares topic trends without changing the primary topic detail", async ({ page }) => {
  await page.goto("/?tab=content&view=topic-detail&tag=AI", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "添加对比", exact: true })).toBeVisible()

  await page.getByRole("button", { name: "添加对比", exact: true }).click()
  await expect(page.locator(".comparison-options").getByRole("option").first()).toContainText("开发")
  await page.getByRole("combobox", { name: "搜索对比话题" }).fill("AI")
  await expect(page.getByRole("option", { name: /^AI(?:\s|$)/ })).toHaveCount(0)
  await page.getByRole("combobox", { name: "搜索对比话题" }).fill("Python")
  await page.getByRole("option", { name: /^Python/ }).click()
  await expect(page.getByRole("combobox", { name: "搜索对比话题" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "移除对比 Python", exact: true })).toBeVisible()
  await expect.poll(() => new URL(page.url()).searchParams.getAll("tagCompare")).toEqual(["Python"])
  await expect.poll(async () => await page.locator("#topic-detail-trend").getAttribute("aria-label") || "").toContain("Python")
  await expect(page.locator("#topic-detail .topic-detail-scope-note")).toContainText("AI 共")
  await expect(page.locator("#topic-detail .ranked-column")).toHaveCount(3)

  const trendCanvas = page.locator("#topic-detail-trend canvas")
  const canvasBeforeLegendClick = await trendCanvas.evaluate((canvas: HTMLCanvasElement) => canvas.toDataURL())
  const trendBox = await page.locator("#topic-detail-trend").boundingBox()
  expect(trendBox).not.toBeNull()
  await page.mouse.click(trendBox!.x + 21, trendBox!.y + trendBox!.height - 14)
  await expect.poll(() => trendCanvas.evaluate((canvas: HTMLCanvasElement) => canvas.toDataURL()))
    .not.toBe(canvasBeforeLegendClick)
  await expect.poll(() => trendCanvas.evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext("2d")
    const pixels = context?.getImageData(0, 0, canvas.width, Math.floor(canvas.height * 0.78)).data || []
    let bluePixels = 0
    for (let index = 0; index < pixels.length; index += 4) {
      if (Math.abs(pixels[index] - 78) < 10 && Math.abs(pixels[index + 1] - 121) < 10 && Math.abs(pixels[index + 2] - 167) < 10) {
        bluePixels += 1
      }
    }
    return bluePixels
  })).toBeGreaterThan(10)
  await page.mouse.click(trendBox!.x + 21, trendBox!.y + trendBox!.height - 14)
  await expect.poll(() => trendCanvas.evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext("2d")
    const pixels = context?.getImageData(0, 0, canvas.width, Math.floor(canvas.height * 0.78)).data || []
    let redPixels = 0
    for (let index = 0; index < pixels.length; index += 4) {
      if (Math.abs(pixels[index] - 217) < 10 && Math.abs(pixels[index + 1] - 72) < 10 && Math.abs(pixels[index + 2] - 65) < 10) {
        redPixels += 1
      }
    }
    return redPixels
  })).toBeGreaterThan(10)

  for (const topic of ["Java", "Mac", "Linux"]) {
    await page.getByRole("button", { name: "添加对比", exact: true }).click()
    await page.getByRole("combobox", { name: "搜索对比话题" }).fill(topic)
    await page.getByRole("option", { name: new RegExp(`^${topic}\\s`) }).click()
  }
  await expect(page.getByRole("button", { name: "最多对比 4 项", exact: true })).toBeDisabled()
  expect(new URL(page.url()).searchParams.getAll("tagCompare")).toEqual(["Python", "Java", "Mac", "Linux"])

  await page.reload({ waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "话题详情：AI", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "移除对比 Python", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "移除对比 Java", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "移除对比 Mac", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "移除对比 Linux", exact: true })).toBeVisible()
})

test("loads content evolution shards without term details", async ({ page }) => {
  const requests: string[] = []
  await page.route("**/dynamic-content-hotspots-2016.json*", async route => {
    await new Promise(resolve => setTimeout(resolve, 500))
    await route.continue()
  })
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (name.startsWith("dynamic-content-")) requests.push(name)
  })

  await page.goto("/?tab=content&view=content-hotspots", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "内容演变", exact: true })).toBeVisible()
  await expect(page.getByRole("tab", { name: "内容演变", exact: true })).toHaveAttribute("aria-selected", "true")
  await expect(page.locator("#content-hotspot-heatmap canvas").first()).toBeVisible()
  const contentTrendChart = page.locator("#content-hotspot-trend")
  await expect(contentTrendChart.locator("canvas").first()).toBeVisible()
  await expect(contentTrendChart).toHaveAttribute("data-latest-period", latestCompleteMonth)
  await expect(page.getByLabel("内容排名数量").locator(".active")).toHaveText("Top 20")
  await expect(page.getByLabel("趋势内容数量").locator(".active")).toHaveText("Top 10")
  await expect(page.getByRole("heading", { name: "热点内容", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "上升内容", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "下降内容", exact: true })).toBeVisible()
  await expect(page.locator("#content-evolution-panel .ranked-column")).toHaveCount(3)
  await expect(page.locator("#content-evolution-panel .ranked-column").first().locator(".ranked-item")).toHaveCount(20)
  await expect(page.getByRole("heading", { name: /内容详情：/ })).toHaveCount(0)
  await expect.poll(() => new URL(page.url()).searchParams.get("view")).toBe("content-evolution")
  expect(requests).toContain("dynamic-content-hotspots-index.json")
  expect(requests.filter(name => /^dynamic-content-hotspots-\d{4}\.json$/.test(name)).length).toBeLessThanOrEqual(6)
  expect(requests.filter(name => name.startsWith("dynamic-content-term-details-"))).toHaveLength(0)

  const chart = page.locator("#content-hotspot-heatmap")
  const chartInstance = await chart.getAttribute("_echarts_instance_")
  const requestCountBeforeGrainChange = requests.length
  if ((page.viewportSize()?.width || 0) <= 680) {
    await page.locator(".mobile-filter-summary").click()
  }
  await page.getByRole("button", { name: "年", exact: true }).click()
  await expect.poll(async () => {
    const label = await chart.getAttribute("aria-label") || ""
    return /20\d{2}的数据/.test(label) && !/20\d{2}-\d{2}的数据/.test(label)
  }).toBe(true)
  expect(requests.length).toBe(requestCountBeforeGrainChange)
  await page.getByRole("button", { name: "月", exact: true }).click()
  await expect.poll(async () => /20\d{2}-\d{2}的数据/.test(await chart.getAttribute("aria-label") || "")).toBe(true)

  await page.getByRole("button", { name: "近3年", exact: true }).click()
  await expect(page.getByLabel("开始月份")).toHaveValue(shiftMonth(latestCompleteMonth, -35))
  if ((page.viewportSize()?.width || 0) <= 680) {
    await page.locator(".mobile-filter-summary").click()
  }
  await page.getByRole("button", { name: "近10年", exact: true }).click()
  await expect(chart.locator("canvas").first()).toBeVisible()
  await expect(chart).toHaveAttribute("_echarts_instance_", chartInstance || "")
  await expect(page.getByLabel("开始月份")).toHaveValue(shiftMonth(latestCompleteMonth, -119))
  if ((page.viewportSize()?.width || 0) <= 680) {
    await page.locator(".mobile-filter-summary").click()
  }
  await page.getByRole("button", { name: "近5年", exact: true }).click()
  await expect(page.getByLabel("开始月份")).toHaveValue(shiftMonth(latestCompleteMonth, -59))

  await page.getByLabel("内容排名数量").getByRole("button", { name: "Top 30", exact: true }).click()
  await expect(page).toHaveURL(/contentTop=30/)
  await expect(page.locator("#content-hotspot-heatmap")).toHaveCSS("height", "1012px")
  await page.getByLabel("趋势内容数量").getByRole("button", { name: "Top 30", exact: true }).click()
  await expect(page).toHaveURL(/contentTrendTop=30/)
  await expect(page.getByLabel("趋势内容数量").locator(".active")).toHaveText("Top 30")
  expect(requests.filter(name => name.startsWith("dynamic-content-term-details-"))).toHaveLength(0)
  const evolutionDimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
  }))
  expect(evolutionDimensions.documentWidth).toBe(evolutionDimensions.viewport)

  const firstHotContent = page.locator("#content-evolution-panel .ranked-column").first().locator(".ranked-item").first()
  const selectedTerm = (await firstHotContent.locator("strong").textContent())?.trim() || ""
  await firstHotContent.click()
  await expect(page.getByRole("tab", { name: "内容详情", exact: true })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { name: `内容详情：${selectedTerm}`, exact: true })).toBeVisible()
  await expect.poll(() => new URL(page.url()).searchParams.get("term")).toBe(selectedTerm)
})

test("loads content detail without evolution year shards", async ({ page }) => {
  const requests: string[] = []
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (name.startsWith("dynamic-content-")) requests.push(name)
  })

  await page.goto("/?tab=content&view=content-detail&term=AI", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "内容详情", exact: true })).toBeVisible()
  await expect(page.getByRole("tab", { name: "内容详情", exact: true })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { name: "内容详情：AI", exact: true })).toBeVisible()
  const trendChart = page.locator("#content-term-trend")
  await expect(trendChart.locator("canvas").first()).toBeVisible()
  await expect(page.getByLabel("选择内容热词")).toHaveValue("AI")
  await page.getByLabel("选择内容热词").click()
  await expect(page.locator(".search-select-menu").getByRole("option").first()).toContainText("工程师")
  await page.keyboard.press("Escape")
  await expect(page.getByRole("heading", { name: "关联内容", exact: true })).toBeVisible()
  await expect(page.getByLabel("内容关联维度").locator(".active")).toHaveText("关联内容")
  await page.getByRole("button", { name: "关联话题", exact: true }).click()
  await expect(page.getByRole("heading", { name: "关联话题", exact: true })).toBeVisible()
  await page.getByRole("button", { name: "关联内容", exact: true }).click()
  await expect(page.getByRole("heading", { name: "活跃用户", exact: true })).toBeVisible()
  expect(requests).toContain("dynamic-content-hotspots-index.json")
  expect(requests.filter(name => /^dynamic-content-hotspots-\d{4}\.json$/.test(name))).toHaveLength(0)
  expect(new Set(requests.filter(name => name.startsWith("dynamic-content-term-details-"))).size).toBe(1)

  if ((page.viewportSize()?.width || 0) <= 680) await page.locator(".mobile-filter-summary").click()
  await page.getByRole("button", { name: "年", exact: true }).click()
  await expect.poll(async () => {
    const label = await trendChart.getAttribute("aria-label") || ""
    return /20\d{2}的数据/.test(label) && !/20\d{2}-\d{2}的数据/.test(label)
  }).toBe(true)
  await page.getByRole("button", { name: "月", exact: true }).click()
  await page.getByRole("button", { name: "近3年", exact: true }).click()
  await expect.poll(async () => await trendChart.getAttribute("aria-label") || "").toContain(shiftMonth(latestCompleteMonth, -35))
  expect(requests.filter(name => /^dynamic-content-hotspots-\d{4}\.json$/.test(name))).toHaveLength(0)

  await expect.poll(() => new URL(page.url()).searchParams.get("term")).toBe("AI")
  await page.getByRole("button", { name: "添加对比", exact: true }).click()
  await expect(page.locator(".comparison-options").getByRole("option").first()).toContainText("工程师")
  await page.getByRole("combobox", { name: "搜索对比热词" }).fill("ChatGPT")
  await page.getByRole("option", { name: /^ChatGPT/ }).click()
  await expect(page.getByRole("combobox", { name: "搜索对比热词" })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "移除对比 ChatGPT", exact: true })).toBeVisible()
  await expect.poll(() => new URL(page.url()).searchParams.getAll("termCompare")).toEqual(["ChatGPT"])
  await expect.poll(async () => await trendChart.getAttribute("aria-label") || "").toContain("ChatGPT")
  await expect(page.getByRole("heading", { name: "内容详情：AI", exact: true })).toBeVisible()
  await expect(page.locator(".content-term-detail .ranked-column")).toHaveCount(3)
  const firstRelatedItem = page.locator(".content-term-detail .ranked-column").first().locator(".ranked-item").first()
  const relatedTerm = (await firstRelatedItem.locator("strong").textContent())?.trim() || ""
  expect(relatedTerm).not.toBe("")
  await firstRelatedItem.click()
  await expect(page.getByRole("heading", { name: `内容详情：${relatedTerm}`, exact: true })).toBeVisible()
  await expect.poll(() => new URL(page.url()).searchParams.get("term")).toBe(relatedTerm)
  expect(requests.filter(name => /^dynamic-content-hotspots-\d{4}\.json$/.test(name))).toHaveLength(0)
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    documentWidth: document.documentElement.scrollWidth,
  }))
  expect(dimensions.documentWidth).toBe(dimensions.viewport)
})

test("restores a limited member profile from URL and browser history", async ({ page }) => {
  const dataRequests: string[] = []
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (name.startsWith("dynamic-") && name.endsWith(".json")) dataRequests.push(name)
  })
  await page.goto("/?tab=community&member=Livid", { waitUntil: "domcontentloaded" })
  await expect(page.getByRole("heading", { name: "成员详情：Livid", exact: true })).toBeVisible()
  expect(dataRequests).not.toContain("dynamic-community.json")
  await expect(page.locator("#member-profile-trend canvas")).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要参与节点", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要发帖话题", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "主要标题内容", exact: true })).toBeVisible()
  await expect(page.locator("#member-profile .ranked-subcolumn")).toHaveCount(2)
  await expect(page.locator("#member-profile .ranked-subcolumn").first().locator(".ranked-item")).toHaveCount(10)
  await expect(page.locator("#member-profile .ranked-group-labels")).toContainText("发帖")
  await expect(page.locator("#member-profile .ranked-group-labels")).toContainText("评论")
  await expect(page.locator("#member-profile .ranked-column-subtitle")).toHaveText(["按发帖数", "按标题数"])
  await expect(page.locator("#member-profile .ranked-column").nth(2).locator(".ranked-item").first()).toBeVisible()
  if ((page.viewportSize()?.width || 0) > 1050) {
    const rankingGeometry = await page.locator("#member-profile .ranked-column").evaluateAll(columns => columns.map(column => {
      const items = [...column.querySelectorAll<HTMLElement>(".ranked-item")]
      return { top: items[0]?.getBoundingClientRect().top || 0, bottom: items[items.length - 1]?.getBoundingClientRect().bottom || 0 }
    }))
    expect(Math.max(...rankingGeometry.map(item => item.top)) - Math.min(...rankingGeometry.map(item => item.top))).toBeLessThan(1)
    expect(Math.max(...rankingGeometry.map(item => item.bottom)) - Math.min(...rankingGeometry.map(item => item.bottom))).toBeLessThan(1)
  }
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

  const memberContentItem = page.locator("#member-profile .ranked-column").nth(2).locator(".ranked-item").first()
  const memberContentTerm = (await memberContentItem.locator("strong").textContent())?.trim() || ""
  await memberContentItem.click()
  await expect(page.getByRole("heading", { name: `内容详情：${memberContentTerm}`, exact: true })).toBeVisible()
  await expect.poll(() => new URL(page.url()).searchParams.get("term")).toBe(memberContentTerm)
  await page.goBack()
  await expect(page.getByRole("heading", { name: "成员详情：Livid", exact: true })).toBeVisible()

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
  await expect(page.getByLabel("选择月份")).toHaveValue(latestCompleteMonth)
  await expect(page.getByLabel("选择月份").locator("option").first()).toHaveAttribute("value", latestCompleteMonth)
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
  await expect(annualView.getByRole("heading", { name: new RegExp(`${latestCompleteMonth.slice(0, 4)} 年数据.*截至 ${Number(latestCompleteMonth.slice(5))} 月`) })).toBeVisible()
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

test("loads global entity indexes only when search opens", async ({ page }) => {
  const indexRequests: string[] = []
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (["dynamic-tag-detail-index.json", "dynamic-content-hotspots-index.json", "dynamic-node-detail-index.json", "dynamic-member-profile-index.json"].includes(name)) {
      indexRequests.push(name)
    }
  })

  await page.goto("/", { waitUntil: "networkidle" })
  expect(indexRequests).toEqual([])
  await page.getByRole("button", { name: "全局搜索", exact: true }).click()
  await page.getByRole("searchbox", { name: "搜索看板数据" }).fill("loving29cn")
  await expect.poll(() => new Set(indexRequests).size).toBe(4)
  await expect(page.locator(".global-search-results > button")).toHaveCount(1)
  await page.locator(".global-search-results > button").click()
  await expect(page.getByRole("heading", { name: "成员详情：loving29cn", exact: true })).toBeVisible({ timeout: 10_000 })
  await expect(page).toHaveURL(/tab=community.*community=member-detail.*member=loving29cn/)
})

test("rejects incomplete URL ranges while preserving single-month analysis", async ({ page }) => {
  await page.goto(`/?from=${shiftMonth(latestCompleteMonth, -60)}&to=${nextIncompleteMonth}`, { waitUntil: "domcontentloaded" })
  await expect(page.getByLabel("开始月份")).toHaveValue(shiftMonth(latestCompleteMonth, -59))
  await expect(page.getByLabel("结束月份")).toHaveValue(latestCompleteMonth)
  await expect(page).not.toHaveURL(new RegExp(`to=${nextIncompleteMonth}`))

  await page.goto(`/?from=${latestCompleteMonth}&to=${latestCompleteMonth}`, { waitUntil: "domcontentloaded" })
  await expect(page.getByLabel("开始月份")).toHaveValue(latestCompleteMonth)
  await expect(page.getByLabel("结束月份")).toHaveValue(latestCompleteMonth)
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

  await page.goto("/?tab=content&mode=share", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#topic-evolution canvas").first()).toBeVisible()
  await expect(page).not.toHaveURL(/mode=share/)
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
  await expect(monthlyView.getByText("热门内容", { exact: true })).toBeVisible()
  await expect(monthlyView.getByText("热门节点", { exact: true })).toBeVisible()
  await expect(monthlyView.getByText("活跃用户", { exact: true })).toHaveCount(0)
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
  await expect(page.getByLabel("选择月份").locator("option").first()).toHaveAttribute("value", latestCompleteMonth)
  await expect(page.getByLabel("选择月份").locator(`option[value='${nextIncompleteMonth}']`)).toHaveCount(0)
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

test("opens a period content ranking in the content detail section", async ({ page }) => {
  await page.goto(`/?overview=month&period=${latestCompleteMonth}`, { waitUntil: "domcontentloaded" })
  const monthlyView = page.getByLabel("月度", { exact: true })
  const contentItem = monthlyView.locator(".ranked-column").nth(1).locator("button").first()
  const term = (await contentItem.locator("strong").textContent())?.trim() || ""
  await contentItem.click()

  await expect(page.getByRole("tab", { name: "内容详情", exact: true })).toHaveAttribute("aria-selected", "true")
  const detailHeading = page.getByRole("heading", { name: `内容详情：${term}`, exact: true })
  await expect(detailHeading).toBeVisible()
  await expect(page).toHaveURL(/tab=content.*view=content-detail.*term=|term=.*view=content-detail/)
})

test("opens monthly and annual node rankings in the node detail section", async ({ page }) => {
  const cases = [
    { url: `/?overview=month&period=${latestCompleteMonth}`, label: "月度" },
    { url: `/?overview=year&period=${latestCompleteMonth.slice(0, 4)}`, label: "年度" },
  ]

  for (const item of cases) {
    await page.goto(item.url, { waitUntil: "domcontentloaded" })
    const periodView = page.getByLabel(item.label, { exact: true })
    const nodeItem = periodView.locator(".ranked-column").nth(2).getByRole("button").first()
    const label = (await nodeItem.locator("strong").textContent())?.trim() || ""
    await expect(nodeItem).toHaveJSProperty("tagName", "BUTTON")
    await nodeItem.click()

    await expect(page.getByRole("tab", { name: "节点详情", exact: true })).toHaveAttribute("aria-selected", "true")
    await expect(page.getByRole("heading", { name: /节点详情：/ })).toContainText(label)
    await expect(page).toHaveURL(/tab=content.*view=node-detail.*node=|node=.*view=node-detail/)
  }

  await page.goto("/?overview=month&period=2010-11", { waitUntil: "domcontentloaded" })
  const historicalColumn = page.getByLabel("月度", { exact: true }).locator(".ranked-column").nth(2)
  const expandHistoricalNodes = historicalColumn.getByRole("button", { name: /展开全部/ })
  if ((page.viewportSize()?.width || 0) <= 680) {
    await expect(expandHistoricalNodes).toBeVisible()
    await expandHistoricalNodes.click()
  }
  const historicalNode = historicalColumn.getByRole("button").filter({ hasText: "aden" })
  await expect(historicalNode).toBeVisible()
  await historicalNode.click()
  await expect(page.getByRole("heading", { name: "节点详情：aden", exact: true })).toBeVisible()
  await expect(page.locator("#node-detail .node-detail-metrics")).toBeVisible()
})

test("keeps members outside the limited profile set inside the dashboard", async ({ page }) => {
  let popupOpened = false
  page.on("popup", () => { popupOpened = true })
  await page.goto("/?tab=content&view=topic-detail&tag=MBP", { waitUntil: "domcontentloaded" })
  const member = page.locator("#topic-detail .ranked-column").nth(2)
    .getByRole("button").filter({ hasText: "shrug" })
  await expect(member).toBeVisible()
  await member.click()

  await expect(page.getByRole("heading", { name: "成员详情：shrug", exact: true })).toBeVisible()
  await expect(page.locator("#member-profile > .empty-state")).toContainText("暂未纳入有限画像范围")
  await expect(page.getByRole("link", { name: "V2EX 主页", exact: true })).toHaveAttribute("href", "https://www.v2ex.com/member/shrug")
  expect(popupOpened).toBe(false)
})

test("loads a searchable node detail shard and supports internal drill-down", async ({ page }) => {
  const detailRequests: string[] = []
  const dataRequests: string[] = []
  page.on("request", request => {
    const name = new URL(request.url()).pathname.split("/").pop() || ""
    if (/dynamic-node-details-[0-9a-f]{2}\.json/.test(name)) detailRequests.push(request.url())
    if (name.startsWith("dynamic-") && name.endsWith(".json")) dataRequests.push(name)
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
  expect(dataRequests).not.toContain("dynamic-nodes.json")
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

test("allows touch scrolling in detail search results", async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Touch scrolling is covered by the mobile project")

  const client = await context.newCDPSession(page)
  const details = [
    { url: "/?tab=content&view=topic-detail&tag=AI", label: "选择话题", heading: "话题详情：AI" },
    { url: "/?tab=content&view=node-detail&node=programmer", label: "选择节点", heading: /节点详情：程序员/ },
    { url: "/?tab=community&community=member-detail&member=Livid", label: "选择成员", heading: "成员详情：Livid" },
  ]

  for (const detail of details) {
    await page.goto(detail.url, { waitUntil: "domcontentloaded" })
    await expect(page.getByRole("heading", { name: detail.heading, exact: true })).toBeVisible()
    await page.getByLabel(detail.label).click()

    const menu = page.getByRole("listbox")
    await expect(menu).toBeVisible()
    const dimensions = await menu.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      scrollTop: element.scrollTop,
    }))
    expect(dimensions.scrollHeight).toBeGreaterThan(dimensions.clientHeight)

    const box = await menu.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.y).toBeGreaterThanOrEqual(0)
    expect(box!.y + box!.height).toBeLessThanOrEqual(page.viewportSize()!.height)
    const x = Math.round(box!.x + box!.width / 2)
    const startY = Math.round(box!.y + box!.height - 30)
    const endY = Math.round(box!.y + 35)
    await client.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y: startY }] })
    for (let step = 1; step <= 5; step += 1) {
      const y = Math.round(startY + (endY - startY) * step / 5)
      await client.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y }] })
    }
    await client.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })

    await expect.poll(() => menu.evaluate((element) => element.scrollTop)).toBeGreaterThan(dimensions.scrollTop)
  }
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

test("keeps grouped post navigation compact on mobile", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Compact grouped navigation is covered by the mobile project")
  await page.goto("/?tab=content", { waitUntil: "domcontentloaded" })
  const navigation = page.locator(".grouped-subtab-list")
  await expect(navigation).toBeVisible()
  const spacing = await navigation.evaluate((element) => {
    const navigationStyle = getComputedStyle(element)
    const groupStyles = [...element.querySelectorAll<HTMLElement>(".subtab-group")].map(group => getComputedStyle(group))
    return {
      gap: parseFloat(navigationStyle.columnGap),
      maxPadding: Math.max(...groupStyles.map(style => Math.max(
        parseFloat(style.paddingLeft),
        parseFloat(style.paddingRight),
      ))),
    }
  })
  expect(spacing.gap).toBe(0)
  expect(spacing.maxPadding).toBeLessThanOrEqual(8)
})

test("keeps the narrow header on one line without horizontal overflow", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 })
  await page.goto("/", { waitUntil: "domcontentloaded" })
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  await expect(page.locator(".data-scope-narrow")).toBeVisible()
  await expect(page.locator(".data-scope-compact")).toBeHidden()
  const layout = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    scopeHeight: document.querySelector<HTMLElement>(".data-scope-narrow")?.getBoundingClientRect().height || 0,
  }))
  expect(layout.documentWidth).toBe(layout.viewportWidth)
  expect(layout.scopeHeight).toBeLessThan(18)
})
