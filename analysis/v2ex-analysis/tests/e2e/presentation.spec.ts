import { expect, test } from "@playwright/test"
import { readFileSync } from "node:fs"
import type { PresentationSlide } from "../../src/types/presentation"

const presentation = JSON.parse(readFileSync("public/dynamic-observations.json", "utf8")).presentation
const slides: PresentationSlide[] = presentation.slides || []
const entry = "/?tab=observations&observation=presentation"

function chartCount(slide: PresentationSlide, expanded: boolean) {
  return (slide.chart ? 1 : 0) + (slide.panels?.length || 0) + (expanded ? (slide.takeaways || []).filter(item => item.chart).length : 0)
}

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
    const expanded = await page.locator(".deck-body").evaluate(element => element.clientHeight >= 650 && window.innerWidth >= 1100)
    const count = chartCount(slide, expanded)
    await expect(stage.locator("canvas")).toHaveCount(count)
    for (let chartIndex = 0; chartIndex < count; chartIndex += 1) {
      await expect.poll(async () => stage.locator("canvas").nth(chartIndex).evaluate((canvas: HTMLCanvasElement) => {
        const pixels = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data
        let colored = 0
        for (let offset = 0; offset < pixels.length; offset += 16) {
          if (pixels[offset + 3] > 40 && Math.max(pixels[offset], pixels[offset + 1], pixels[offset + 2]) - Math.min(pixels[offset], pixels[offset + 1], pixels[offset + 2]) > 35) colored += 1
        }
        return colored
      }), { message: `nonblank chart: ${slide.id}` }).toBeGreaterThan(50)
    }

    const layout = await stage.evaluate(element => {
      const box = element.getBoundingClientRect()
      const chart = element.querySelector<HTMLElement>("[data-deck-chart]")?.getBoundingClientRect()
      const note = element.querySelector<HTMLElement>(".deck-note")?.getBoundingClientRect()
      const body = element.querySelector<HTMLElement>(".deck-body")!
      const blocks = [...element.querySelectorAll<HTMLElement>("h2, h3, p, dt, dd, blockquote, .deck-timeline li")]
      return {
        overflows: document.documentElement.scrollWidth > document.documentElement.clientWidth || element.scrollWidth > element.clientWidth + 1,
        clippedBlocks: blocks.filter(block => block.clientWidth && block.scrollWidth > block.clientWidth + 1).map(block => block.textContent),
        noteFits: !note || note.bottom <= box.bottom,
        chartFits: !chart || (chart.left >= box.left && chart.right <= box.right && (window.innerWidth <= 900 || chart.bottom <= (note?.top || box.bottom))),
        stageFits: box.height <= window.innerHeight,
        bodyFits: window.innerWidth <= 900 || body.scrollHeight <= body.clientHeight + 2,
        chartHeight: chart?.height,
        minFont: Math.min(...blocks.map(block => Number.parseFloat(getComputedStyle(block).fontSize))),
      }
    })
    expect(layout, slide.id).toMatchObject({ overflows: false, clippedBlocks: [], noteFits: true, chartFits: true, stageFits: true, bodyFits: true })
    expect(layout.minFont, slide.id).toBeGreaterThanOrEqual(12)
    if (slide.chart) expect(layout.chartHeight, slide.id).toBeGreaterThanOrEqual(240)
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

test("presents all four interaction distributions with readable independent plots", async ({ page }) => {
  await page.goto(`${entry}&slide=scope`)
  await expect(page.locator("#deck-title")).toHaveText("数据概览")
  const panels = page.locator(".deck-distributions section")
  await expect(panels.locator("h3")).toHaveText(["帖子浏览", "帖子收藏", "帖子感谢", "评论感谢"])
  await expect(panels.locator("canvas")).toHaveCount(4)
  const sizes = await panels.evaluateAll(elements => elements.map(element => {
    const header = element.querySelector("header")!.getBoundingClientRect()
    const chart = element.querySelector("[data-deck-chart]")!.getBoundingClientRect()
    return { top: header.top, left: header.left, height: chart.height, headerFits: header.bottom <= chart.top + 1 }
  }))
  expect(sizes.every(item => item.headerFits && item.height >= 140)).toBe(true)
  if (page.viewportSize()!.width > 900) {
    expect(sizes[0].top).toBe(sizes[1].top)
    expect(sizes[2].top).toBe(sizes[3].top)
    expect(sizes[0].left).toBe(sizes[2].left)
  } else expect(sizes.every((item, index) => !index || item.top > sizes[index - 1].top)).toBe(true)
})

test("keeps population order and evidence alongside a readable chart", async ({ page }) => {
  expect(presentation.charts.overview.series.map((item: { name: string }) => item.name)).toEqual(["新增成员", "帖子", "评论"])
  await page.goto(`${entry}&slide=finance`)
  const stage = page.locator(".deck-stage")
  await expect(stage.locator("canvas")).toBeVisible()
  const layout = await stage.evaluate(element => {
    const chart = element.querySelector("[data-deck-chart]")!.getBoundingClientRect()
    const cases = element.querySelector(".deck-chart-cases")!.getBoundingClientRect()
    const style = getComputedStyle(element)
    const usableWidth = element.clientWidth - Number.parseFloat(style.paddingLeft) - Number.parseFloat(style.paddingRight)
    return { ratio: chart.width / usableWidth, casesBelow: cases.top >= chart.bottom, casesBeside: cases.left > chart.right }
  })
  if (page.viewportSize()!.width > 900) {
    expect(layout.ratio).toBeGreaterThan(.60)
    expect(layout.casesBeside).toBe(true)
  } else expect(layout.casesBelow).toBe(true)
  await page.goto(`${entry}&slide=explore`)
  await expect(stage).toHaveAttribute("data-slide", "explore")
  await expect(stage.locator(".deck-takeaways li")).toHaveCount(3)
  await expect(stage.getByRole("button", { name: "打开全站搜索" })).toBeVisible()
})

for (const viewport of [{ width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
  test(`fits all slides without clipping at ${viewport.width}x${viewport.height}, including fullscreen`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name === "mobile", "Desktop screen-fit matrix")
    test.setTimeout(100_000)
    await page.setViewportSize(viewport)
    await page.goto(entry)
    for (const fullscreen of [false, true]) {
      if (fullscreen) {
        await page.getByRole("button", { name: "全屏演示", exact: true }).click()
        await expect.poll(() => page.evaluate(() => !!document.fullscreenElement)).toBe(true)
        await page.keyboard.press("Home")
      }
      for (const [index, slide] of slides.entries()) {
        const stage = page.locator(".deck-stage")
        await expect(stage).toHaveAttribute("data-slide", slide.id)
        const expanded = await page.locator(".deck-body").evaluate(element => element.clientHeight >= 650 && window.innerWidth >= 1100)
        await expect(stage.locator("canvas")).toHaveCount(chartCount(slide, expanded))
        await expect.poll(() => stage.evaluate(element => {
          const body = element.querySelector<HTMLElement>(".deck-body")!
          const note = element.querySelector<HTMLElement>(".deck-note")!
          const box = element.getBoundingClientRect()
          const blocks = [...body.querySelectorAll<HTMLElement>("h3, p, blockquote, dl, .deck-case footer, .deck-search")]
          return {
            screen: box.bottom <= window.innerHeight + 1,
            body: body.scrollHeight <= body.clientHeight + 2,
            text: blocks.every(block => block.getBoundingClientRect().bottom <= note.getBoundingClientRect().top + 1),
            width: document.documentElement.scrollWidth <= window.innerWidth,
          }
        }), { message: `${slide.id}, fullscreen=${fullscreen}` }).toEqual({ screen: true, body: true, text: true, width: true })
        if (index < slides.length - 1) await page.getByRole("button", { name: "下一页", exact: true }).click()
      }
    }
  })
}

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

test("keeps mobile navigation visible while reading and resets the next page", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "mobile", "Mobile inner scrolling")
  await page.goto(`${entry}&slide=finance`)
  const body = page.locator(".deck-body")
  await expect(page.locator(".deck-chart-cases")).toHaveCount(1)
  await body.evaluate(element => { element.scrollTop = element.scrollHeight })
  await expect.poll(() => body.evaluate(element => element.scrollTop)).toBeGreaterThan(0)
  await expect(page.getByRole("button", { name: "下一页", exact: true })).toBeInViewport()
  await page.getByRole("button", { name: "下一页", exact: true }).click()
  await expect(page.locator(".deck-stage")).toHaveAttribute("data-slide", "housing")
  await expect.poll(() => body.evaluate(element => element.scrollTop)).toBe(0)
})

test("keeps the page frame inside a short landscape viewport", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "mobile", "Explicit landscape viewport")
  await page.setViewportSize({ width: 844, height: 390 })
  await page.goto(`${entry}&slide=finance`)
  await expect(page.locator(".deck-stage canvas")).toBeVisible()
  await expect.poll(() => page.locator(".deck-view").evaluate(element => element.getBoundingClientRect().bottom)).toBeLessThanOrEqual(390)
  const stage = page.locator(".deck-stage")
  await stage.evaluate(element => { element.scrollTop = element.scrollHeight })
  await expect(stage.locator(".deck-note")).toBeInViewport()
  await expect(page.getByRole("button", { name: "下一页", exact: true })).toBeInViewport()
})
