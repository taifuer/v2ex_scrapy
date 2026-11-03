import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import { formatNumber } from "../../src/utils/format"

const scores = JSON.parse(readFileSync("public/dynamic-engagement.json", "utf8")).top_posts.score as Array<{
  id: number
  value: number
}>

test("supports composite engagement ranking with pagination and URL state", async ({ page }) => {
  await page.goto("/?tab=engagement")
  const controls = page.getByLabel("热门帖子排序指标")
  const posts = page.locator("#engagement-posts")
  const pagination = page.getByRole("navigation", { name: "热门帖子分页" })
  await expect(controls.locator(".active")).toHaveText("收藏")
  await expect(controls.getByRole("button")).toHaveText(["综合", "收藏", "感谢", "投票", "点击"])
  await pagination.getByRole("button", { name: "3", exact: true }).click()
  await controls.getByRole("button", { name: "综合", exact: true }).click()
  await expect(posts.locator(".ranking-pagination > span")).toHaveText("Top 200 · 第 1 / 20 页")
  await expect.poll(() => new URL(page.url()).searchParams.get("postSort")).toBe("score")
  await expect(posts.locator(".content-list-row").first()).toHaveAttribute("href", `https://www.v2ex.com/t/${scores[0].id}`)
  await expect(posts.locator(".content-list-value").first()).toHaveText(`${formatNumber(scores[0].value, 1)} 分`)
  await expect(posts.locator(".method-note")).toContainText("综合得分")
  await pagination.getByRole("button", { name: "20", exact: true }).click()
  await page.reload()
  await expect(controls.locator(".active")).toHaveText("综合")
  await expect(posts.locator(".ranking-pagination > span")).toHaveText("Top 200 · 第 20 / 20 页")
  await expect(posts.locator(".content-list-row").first()).toHaveAttribute("href", `https://www.v2ex.com/t/${scores[190].id}`)
  await controls.getByRole("button", { name: "收藏", exact: true }).click()
  await expect(posts.locator(".ranking-pagination > span")).toHaveText("Top 200 · 第 1 / 20 页")
  await expect(posts.locator(".method-note")).toHaveCount(0)
  await expect.poll(() => new URL(page.url()).searchParams.get("postSort")).toBeNull()
})

test("keeps composite engagement controls readable on narrow screens", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await page.goto("/?tab=engagement&postSort=score&postPage=2")
  const controls = page.getByLabel("热门帖子排序指标")
  await expect(controls.locator(".active")).toHaveText("综合")
  await expect(page.locator("#engagement-posts .ranking-pagination > span")).toHaveText("Top 200 · 第 2 / 20 页")
  const positions = await controls.getByRole("button").evaluateAll(buttons => buttons.map(button => {
    const rect = button.getBoundingClientRect()
    return { left: rect.left, right: rect.right, top: rect.top, width: rect.width }
  }))
  expect(new Set(positions.map(item => Math.round(item.top))).size).toBe(1)
  expect(positions.every(item => item.width >= 40 && item.left >= 0 && item.right <= 320)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
