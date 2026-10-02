import { expect, test } from "@playwright/test"

test("keeps narrow-screen section links on one scrollable row", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 740 })
  await page.goto("/?tab=content&view=content-evolution")
  const nav = page.getByRole("navigation", { name: "当前页面区域" })
  await expect(nav).toBeVisible()
  const positions = await nav.locator("a").evaluateAll(links => links.map(link => ({
    top: link.getBoundingClientRect().top, height: link.getBoundingClientRect().height,
  })))
  expect(new Set(positions.map(item => Math.round(item.top))).size).toBe(1)
  expect(positions.every(item => item.height >= 40)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await nav.locator("a").last().click()
  await expect(nav.locator("a").last()).toHaveAttribute("aria-current", "location")
})

test("starts the chart runtime while keyword details are still loading", async ({ page }) => {
  let release!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  let runtimeRequested = false
  page.on("request", request => {
    if (request.url().includes("/src/chartRuntime.ts")) runtimeRequested = true
  })
  await page.route("**/dynamic-content-term-details-*.json*", async route => {
    await held
    await route.continue()
  })
  try {
    await page.goto("/?tab=content&view=content-detail&term=AI", { waitUntil: "domcontentloaded" })
    await expect(page.locator("#content-term-detail .loading-spinner")).toBeVisible()
    await expect.poll(() => runtimeRequested).toBe(true)
  } finally {
    release()
  }
  await expect(page.locator("#content-term-trend canvas").first()).toBeVisible()
})

for (const [name, path, pattern, panel] of [
  ["keyword", "/?tab=content&view=content-detail&term=AI", "dynamic-content-period-comments-", ".entity-representative-comments"],
  ["topic", "/?tab=content&view=topic-detail&tag=AI", "dynamic-tag-period-comments-", ".entity-representative-comments"],
  ["node", "/?tab=content&view=node-detail&node=qna", "dynamic-node-period-comments-", ".entity-representative-comments"],
  ["member", "/?tab=community&community=member-detail&member=Livid", "dynamic-member-comments-", ".member-profile-comments"],
]) {
  test(`retries ${name} comments in place without treating failures as empty data`, async ({ page }) => {
    let unavailable = true
    const errors: string[] = []
    page.on("pageerror", error => errors.push(error.message))
    await page.route(`**/${pattern}*.json*`, route => unavailable
      ? route.fulfill({ status: 503, body: "unavailable" })
      : route.continue())
    await page.goto(path, { waitUntil: "domcontentloaded" })
    const section = page.locator(panel)
    await expect(section.locator(".inline-load-error")).toBeVisible()
    await expect(section.getByText(/暂无/)).toHaveCount(0)
    const url = page.url()
    unavailable = false
    await section.getByRole("button", { name: "重试", exact: true }).click()
    await expect(section.locator(".inline-load-error")).toHaveCount(0)
    await expect(section.locator(".comment-ranking-row").first()).toBeVisible()
    expect(page.url()).toBe(url)
    expect(errors).toEqual([])
  })
}
