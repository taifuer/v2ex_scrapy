import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import type { PresentationSlide } from "../../src/types/presentation"

const presentation = JSON.parse(readFileSync("public/dynamic-observations.json", "utf8")).presentation
const slides: PresentationSlide[] = presentation.slides || []
const entry = "/?tab=observations&observation=presentation"

test("keeps every presentation page readable and all charts inside the page", async ({ page }) => {
  test.setTimeout(100_000)
  expect(slides).toHaveLength(20)
  const errors: string[] = []
  page.on("pageerror", error => errors.push(error.message))
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()) })
  await page.goto(entry)
  const stage = page.locator(".deck-stage")
  for (const [index, slide] of slides.entries()) {
    await expect(stage).toHaveAttribute("data-slide", slide.id)
    await expect(page.locator(".deck-counter")).toHaveText(`${index + 1} / 20`)
    if (slide.chart) {
      await expect(stage.locator("canvas")).toHaveCount(1)
      await expect.poll(async () => stage.locator("canvas").evaluate((canvas: HTMLCanvasElement) => {
        const pixels = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data
        let colored = 0
        for (let offset = 0; offset < pixels.length; offset += 16) {
          if (pixels[offset + 3] > 40 && Math.max(pixels[offset], pixels[offset + 1], pixels[offset + 2]) - Math.min(pixels[offset], pixels[offset + 1], pixels[offset + 2]) > 35) colored += 1
        }
        return colored
      }), { message: `nonblank chart: ${slide.id}` }).toBeGreaterThan(50)
    } else await expect(stage.locator("canvas")).toHaveCount(0)

    const layout = await stage.evaluate(element => {
      const box = element.getBoundingClientRect()
      const chart = element.querySelector<HTMLElement>("[data-deck-chart]")?.getBoundingClientRect()
      const note = element.querySelector<HTMLElement>(".deck-note")?.getBoundingClientRect()
      const blocks = [...element.querySelectorAll<HTMLElement>("h2, h3, p, dt, dd, blockquote, .deck-timeline li")]
      return {
        overflows: document.documentElement.scrollWidth > document.documentElement.clientWidth || element.scrollWidth > element.clientWidth + 1,
        clippedBlocks: blocks.filter(block => block.clientWidth && block.scrollWidth > block.clientWidth + 1).map(block => block.textContent),
        noteFits: !note || note.bottom <= box.bottom,
        chartFits: !chart || (chart.left >= box.left && chart.right <= box.right && chart.bottom <= (note?.top || box.bottom)),
        chartHeight: chart?.height,
        minFont: Math.min(...blocks.map(block => Number.parseFloat(getComputedStyle(block).fontSize))),
      }
    })
    expect(layout, slide.id).toMatchObject({ overflows: false, clippedBlocks: [], noteFits: true, chartFits: true })
    expect(layout.minFont, slide.id).toBeGreaterThanOrEqual(12)
    if (slide.chart) expect(layout.chartHeight, slide.id).toBeGreaterThanOrEqual(380)
    if (index < slides.length - 1) await page.getByRole("button", { name: "下一页", exact: true }).click()
  }
  expect(errors).toEqual([])
})

test("restores slide URLs, normalizes unknown pages, and navigates through the directory", async ({ page }) => {
  await page.goto(`${entry}&slide=career`)
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "career")
  await page.reload()
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "career")
  await page.getByRole("button", { name: "演示目录", exact: true }).click()
  const directory = page.getByRole("navigation", { name: "演示章节", exact: true })
  await expect(directory.getByRole("button")).toHaveCount(20)
  await directory.getByRole("button").filter({ hasText: slides.find(slide => slide.id === "housing")!.title }).click()
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "housing")
  await expect(page).toHaveURL(/slide=housing/)
  await expect(directory).toHaveCount(0)
  await expect(page.getByRole("button", { name: "演示目录", exact: true })).toBeFocused()
  await page.keyboard.press("ArrowRight")
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "subscriptions")
  await page.goto(`${entry}&slide=unknown-page`)
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "cover")
  await expect(page).not.toHaveURL(/slide=/)
})

test("keeps navigation and search usable in fullscreen", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Mobile uses a scrolling page")
  await page.goto(`${entry}&slide=overview`)
  await expect(page.locator(".deck-stage canvas")).toBeVisible()
  await page.getByRole("button", { name: "全屏演示", exact: true }).click()
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.classList.contains("deck-view"))).toBe(true)
  await expect(page.getByRole("button", { name: "下一页", exact: true })).toBeInViewport()
  await page.getByRole("button", { name: "下一页", exact: true }).click()
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "members")
  await page.keyboard.press("End")
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "explore")
  await page.getByRole("button", { name: "打开全站搜索", exact: true }).click()
  await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true)
  await expect(page.getByRole("dialog", { name: "搜索看板", exact: true })).toBeVisible()
  await page.getByRole("button", { name: "关闭全局搜索", exact: true }).click()
  await expect(page.getByRole("button", { name: "打开全站搜索", exact: true })).toBeFocused()
  await expect(page.locator(".deck-stage").getByRole("button")).toHaveCount(1)
})
