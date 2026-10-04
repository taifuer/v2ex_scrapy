import { expect, test, type Page } from "@playwright/test"

const detailPath = "/?tab=content&view=node-detail&node=qna&from=2021-01&to=2025-12"
const button = (page: Page) => page.getByRole("button", { name: "返回顶部", exact: true })

async function openDetail(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await page.goto(detailPath)
  await expect(page.locator("#node-detail-trend canvas")).toBeVisible()
}

test("shows only after one viewport and returns without resetting URL state", async ({ page }) => {
  await openDetail(page)
  const url = page.url()
  await expect(button(page)).toBeHidden()
  await expect(page.getByRole("button", { name: "分享当前视图（复制链接）", exact: true })).toHaveCount(0)
  await expect(page.getByRole("button", { name: "复制当前视图链接", exact: true })).toHaveCount(0)
  await expect(page.locator(".copy-link-dialog")).toHaveCount(0)
  await page.evaluate(() => scrollTo(0, innerHeight - 10))
  await expect(button(page)).toBeHidden()
  await page.evaluate(() => scrollTo(0, innerHeight + 10))
  await expect(button(page)).toBeVisible()
  await expect.poll(() => button(page).evaluate(element => {
    const bounds = element.getBoundingClientRect()
    return { width: bounds.width, height: bounds.height, bottom: innerHeight - bounds.bottom }
  })).toEqual({ width: page.viewportSize()!.width <= 680 ? 44 : 40, height: page.viewportSize()!.width <= 680 ? 44 : 40, bottom: 48 })
  await button(page).click()
  await expect.poll(() => page.evaluate(() => scrollY)).toBe(0)
  await expect(button(page)).toBeHidden()
  await expect(page.locator("#dashboard-main")).toBeFocused()
  expect(page.url()).toBe(url)
})

test("stays compact and above the final view without blocking mobile pagination", async ({ page }) => {
  for (const width of [320, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 844 })
    await openDetail(page)
    const pagination = page.locator(".ranking-pagination").last()
    await expect(pagination).toBeVisible()
    await page.locator(".dashboard-footer").scrollIntoViewIfNeeded()
    await expect(button(page)).toBeVisible()
    await expect.poll(() => page.evaluate(() => {
      const control = document.querySelector(".back-to-top-button")!.getBoundingClientRect()
      const panel = document.querySelector("#node-detail")!.getBoundingClientRect()
      const footer = document.querySelector(".dashboard-footer")!.getBoundingClientRect()
      const pagination = Array.from(document.querySelectorAll(".ranking-pagination")).at(-1)!
      return {
        anchored: control.bottom <= panel.bottom - 23,
        size: control.width,
        gap: Math.round(footer.top - panel.bottom),
        overflow: document.documentElement.scrollWidth > innerWidth,
        controlsClear: Array.from(pagination.querySelectorAll("button")).every(element => {
          const bounds = element.getBoundingClientRect()
          return bounds.right <= control.left || bounds.bottom <= control.top || bounds.top >= control.bottom
        }),
      }
    })).toEqual({ anchored: true, size: width <= 680 ? 44 : 40, gap: width <= 680 ? 16 : 24, overflow: false, controlsClear: true })
    await pagination.locator("button").last().click()
    await expect(pagination).toContainText("第 2 / 10 页")
  }
})

test("updates visibility after content shrinks without a window resize", async ({ page }) => {
  await openDetail(page)
  await page.evaluate(() => scrollTo(0, innerHeight + 50))
  await expect(button(page)).toBeVisible()
  await page.locator(".dashboard-shell > .view-section").evaluate(element => {
    element.style.height = "120px"
    element.style.overflow = "hidden"
  })
  await expect(button(page)).toBeHidden()
})

test("keeps the page-end gap compact across views", async ({ page }, testInfo) => {
  for (const [path, ready] of [
    ["/", "#activity-heatmap canvas"],
    ["/?overview=month&period=2025-03", ".monthly-comments .comment-ranking-row"],
    ["/?tab=content&view=topics", "#topic-evolution canvas"],
    ["/?tab=content&view=content-evolution", "#content-hotspot-heatmap canvas"],
    ["/?tab=community", "#member-roles canvas"],
    ["/?tab=engagement", "#engagement-volume canvas"],
    ["/?tab=about", ".about-document"],
  ]) {
    await page.goto(path)
    await expect(page.locator(ready).first()).toBeVisible()
    await page.locator(".dashboard-footer").scrollIntoViewIfNeeded()
    await expect.poll(() => page.evaluate(() => {
      const content = document.querySelector(".dashboard-shell > .view-section")!
      const last = content.lastElementChild!.getBoundingClientRect()
      const footer = document.querySelector(".dashboard-footer")!.getBoundingClientRect()
      return Math.round(footer.top - last.bottom)
    }), { message: path }).toBe(testInfo.project.name === "mobile" ? 16 : 24)
  }
})

test("hides for search and native fullscreen", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "Sticky header and native fullscreen are covered on desktop")
  await openDetail(page)
  await page.evaluate(() => scrollTo(0, innerHeight + 50))
  await expect(button(page)).toBeVisible()
  await page.locator(".header-search-button").click()
  await expect(page.locator(".global-search-dialog")).toBeVisible()
  await expect(button(page)).toBeHidden()
  await page.keyboard.press("Escape")
  await expect(page.locator(".global-search-dialog")).toBeHidden()
  await page.evaluate(() => scrollTo(0, innerHeight + 50))
  await expect(button(page)).toBeVisible()
  await page.evaluate(() => document.documentElement.requestFullscreen())
  await expect(button(page)).toBeHidden()
  await page.evaluate(() => document.exitFullscreen())
  await page.evaluate(() => scrollTo(0, innerHeight + 50))
  await expect(button(page)).toBeVisible()
})
