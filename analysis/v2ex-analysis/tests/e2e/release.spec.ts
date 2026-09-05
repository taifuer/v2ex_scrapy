import { expect, test } from "@playwright/test"
import { mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { prepareRelease } from "../../scripts/release"

test("stamps dist data consistently and keeps UI release metadata outside the data layer", () => {
  const root = mkdtempSync(join(tmpdir(), "v2ex-release-test-"))
  try {
    mkdirSync(join(root, "assets"))
    writeFileSync(join(root, "assets/app-123.js"), "app")
    writeFileSync(join(root, "dynamic-overview.json"), JSON.stringify({ periods: ["2026-08"] }))
    writeFileSync(join(root, "dynamic-manifest.json"), JSON.stringify({ schema_version: 38, files: {} }))
    prepareRelease(root, "data-version", "ui-version")
    const overview = JSON.parse(readFileSync(join(root, "dynamic-overview.json"), "utf8"))
    const manifest = JSON.parse(readFileSync(join(root, "dynamic-manifest.json"), "utf8"))
    expect(overview).toEqual({ periods: ["2026-08"], _analytics_version: "data-version" })
    expect(manifest._analytics_version).toBe("data-version")
    expect(manifest.files["dynamic-overview.json"]).toBe(statSync(join(root, "dynamic-overview.json")).size)
    expect(JSON.parse(readFileSync(join(root, "assets/app-release.json"), "utf8"))).toEqual({ version: "ui-version", analytics_version: "data-version" })
    expect(readFileSync(join(root, "assets-current.txt"), "utf8")).toBe("assets/app-123.js\n")
    const before = readFileSync(join(root, "dynamic-overview.json"), "utf8")
    prepareRelease(root, "data-version", "next-ui-version")
    expect(readFileSync(join(root, "dynamic-overview.json"), "utf8")).toBe(before)
    expect(readFileSync(join(root, "assets-current.txt"), "utf8")).toBe("assets/app-123.js\n")
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("offers a deliberate refresh for stale chunks and preserves the current URL", async ({ page }) => {
  await page.route("**/assets/app-release.json*", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({ version: "next-release" }),
  }))
  await page.goto("/?tab=content&view=content-detail&term=AI&termCompare=GPT")
  await expect(page.locator("#content-term-trend canvas")).toBeVisible()
  const url = page.url()
  const prevented = await page.evaluate(() => !window.dispatchEvent(new Event("vite:preloadError", { cancelable: true })))
  expect(prevented).toBe(true)
  await expect(page.getByRole("status")).toContainText("站点已更新")
  expect(page.url()).toBe(url)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0)
  await page.getByRole("button", { name: "更新页面", exact: true }).click()
  await expect(page.locator("#content-term-trend canvas")).toBeVisible()
  expect(page.url()).toBe(url)
  await expect(page.locator(".release-notice")).toHaveCount(0)
})

test("rejects mixed analytics generations before presenting their contents", async ({ page }) => {
  await page.goto("/")
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  const result = await page.evaluate(async () => {
    const { assertAnalyticsVersion } = await import("/src/services/dataClient.ts")
    assertAnalyticsVersion({ _analytics_version: "current" }, "current")
    try {
      assertAnalyticsVersion({ _analytics_version: "different", rows: [["wrong data"]] }, "current")
      return "accepted"
    } catch (error) {
      return (error as Error).message
    }
  })
  expect(result).toContain("数据版本已更新")
  await expect(page.locator(".release-notice")).toContainText("站点已更新")
  await page.getByRole("button", { name: "关闭更新提示" }).click()
  await expect(page.locator(".release-notice")).toHaveCount(0)
})

test("does not report a network error as a new release", async ({ page }) => {
  await page.route("**/assets/app-release.json*", route => route.fulfill({ status: 503, body: "Unavailable" }))
  await page.goto("/")
  await expect(page.locator("#overview-trend canvas")).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new Event("vite:preloadError", { cancelable: true })))
  await expect(page.locator(".release-notice")).toContainText("请检查网络")
  await expect(page.locator(".release-notice")).not.toContainText("站点已更新")
})
