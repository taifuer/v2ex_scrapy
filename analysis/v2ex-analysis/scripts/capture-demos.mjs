import { mkdir } from "node:fs/promises"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright"

const scriptDir = dirname(fileURLToPath(import.meta.url))
const dashboardDir = resolve(scriptDir, "..")
const repositoryDir = resolve(dashboardDir, "../..")
const demoDir = resolve(repositoryDir, "demo")
const publicDir = resolve(dashboardDir, "public")
const baseUrl = (process.env.DASHBOARD_URL || "http://127.0.0.1:5173").replace(/\/$/, "")

const pageCaptures = [
  { output: "dashboard-demo.png", path: "/", waitFor: "#overview-trend canvas" },
  { output: "dashboard-topics.png", path: "/?tab=content&view=topics", waitFor: "#topic-evolution canvas" },
  { output: "dashboard-observations.png", path: "/?tab=observations", waitFor: ".observation-grid" },
  { output: "dashboard-presentation.png", path: "/?tab=observations&observation=presentation&slide=finance", waitFor: ".deck-stage canvas", region: ".deck-view" },
  { output: "dashboard-monthly.png", path: "/?overview=month", waitFor: ".monthly-data-view" },
  { output: "dashboard-annual.png", path: "/?overview=year", waitFor: ".monthly-data-view" },
  { output: "dashboard-content-hotspots.png", path: "/?tab=content&view=content-evolution", waitFor: "#content-hotspot-heatmap canvas" },
  { output: "dashboard-nodes.png", path: "/?tab=content&view=nodes", waitFor: "#node-structure canvas" },
  { output: "dashboard-node-detail.png", path: "/?tab=content&view=node-detail&node=qna", waitFor: "#node-detail-trend canvas" },
  { output: "dashboard-members.png", path: "/?tab=community", waitFor: "#member-evolution canvas" },
  { output: "dashboard-engagement.png", path: "/?tab=engagement", waitFor: "#engagement-volume canvas" },
]

async function preparePage(browser, viewport, path, waitFor) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 1 })
  const errors = []
  page.on("pageerror", error => errors.push(error.message))
  await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded", timeout: 120_000 })
  await page.locator(waitFor).first().waitFor({ state: "visible", timeout: 120_000 })
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(250)
  for (const section of await page.locator("[data-visible]").all()) {
    await section.scrollIntoViewIfNeeded()
    await page.waitForFunction(element => element.dataset.visible === "true", await section.elementHandle())
    await page.waitForFunction(() => !document.querySelector(".loading-spinner"), undefined, { timeout: 120_000 })
    await page.waitForTimeout(350)
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  if (errors.length) throw new Error(`${path}: ${errors.join("; ")}`)
  return page
}

await mkdir(demoDir, { recursive: true })
const browser = await chromium.launch({ headless: true })

try {
  const socialPage = await preparePage(browser, { width: 1200, height: 630 }, "/", "#overview-trend canvas")
  await socialPage.screenshot({ path: resolve(publicDir, "social-preview.png"), animations: "disabled" })
  await socialPage.close()

  for (const capture of pageCaptures) {
    const page = await preparePage(browser, { width: 1600, height: 1000 }, capture.path, capture.waitFor)
    if (capture.region) {
      await page.waitForTimeout(350)
      await page.locator(capture.region).screenshot({ path: resolve(demoDir, capture.output), animations: "disabled" })
    } else {
      await page.screenshot({ path: resolve(demoDir, capture.output), fullPage: true, animations: "disabled" })
    }
    await page.close()
    process.stdout.write(`Captured ${capture.output}\n`)
  }

  const searchPage = await preparePage(browser, { width: 1600, height: 1000 }, "/", "#overview-trend canvas")
  await searchPage.locator(".header-search-button").click()
  await searchPage.locator(".global-search-dialog").waitFor({ state: "visible" })
  await searchPage.screenshot({ path: resolve(demoDir, "dashboard-search.png"), animations: "disabled" })
  await searchPage.close()
  process.stdout.write("Captured dashboard-search.png\n")
} finally {
  await browser.close()
}
