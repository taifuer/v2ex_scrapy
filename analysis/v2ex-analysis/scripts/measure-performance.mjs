import { createServer } from "node:http"
import { readFile, mkdir, writeFile } from "node:fs/promises"
import { resolve, dirname, extname, sep } from "node:path"
import { fileURLToPath } from "node:url"
import { gzipSync } from "node:zlib"
import { createHash } from "node:crypto"
import { chromium } from "playwright"
import { comparePerformance } from "./performance-comparison.mjs"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const dist = resolve(root, "dist")
const output = resolve(process.env.PERFORMANCE_OUTPUT || `${root}/test-results/performance.json`)
const baselinePath = process.env.PERFORMANCE_BASELINE
const baseline = baselinePath ? JSON.parse(await readFile(resolve(baselinePath), "utf8")) : null
const dataVersion = createHash("sha256").update(await readFile(resolve(dist, "dynamic-manifest.json"))).digest("hex")
const runs = Number(process.env.PERFORMANCE_RUNS || 3)
if (!Number.isInteger(runs) || runs < 1) throw new Error("PERFORMANCE_RUNS must be a positive integer")
const cases = [
  { name: "overview", path: "/", selector: "#overview-trend canvas" },
  { name: "topics", path: "/?tab=content&view=topics", selector: "#topic-evolution canvas" },
  { name: "keywords", path: "/?tab=content&view=content-evolution", selector: "#content-hotspot-heatmap canvas" },
  { name: "keyword-detail", path: "/?tab=content&view=content-detail&term=AI", selector: "#content-term-trend canvas" },
  { name: "month", path: "/?overview=month", selector: ".monthly-data-view .monthly-metrics" },
]
const files = new Map()
const mime = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2" }
// Serve only the production build, with compression but no browser cache.
const server = createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname)
    const filename = resolve(dist, `.${pathname === "/" ? "/index.html" : pathname}`)
    if (!filename.startsWith(dist + sep)) throw new Error("Invalid path")
    if (!files.has(filename)) files.set(filename, gzipSync(await readFile(filename)))
    response.writeHead(200, { "Content-Type": mime[extname(filename)] || "application/octet-stream", "Content-Encoding": "gzip", "Cache-Control": "no-store" })
    response.end(files.get(filename))
  } catch {
    response.writeHead(404)
    response.end()
  }
})
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve))
const baseURL = `http://127.0.0.1:${server.address().port}`
let browser
const results = []

async function ready(page, selector) {
  await page.locator(selector).first().waitFor({ state: "visible", timeout: 90_000 })
  if (selector.includes("canvas")) {
    await page.waitForFunction(selector => [...document.querySelectorAll(selector)].some(canvas => {
      if (!canvas?.width || !canvas.height) return false
      const pixels = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data
      let colored = 0
      for (let index = 0; index < pixels.length; index += 16) {
        if (pixels[index + 3] > 40 && Math.max(pixels[index], pixels[index + 1], pixels[index + 2]) - Math.min(pixels[index], pixels[index + 1], pixels[index + 2]) > 35) colored++
        if (colored > 30) return true
      }
      return false
    }), selector, { timeout: 90_000 })
  }
}

try {
  browser = await chromium.launch({ headless: true })
  for (const sample of cases) {
    for (let run = 0; run < runs; run++) {
      const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true })
      const page = await context.newPage()
      const errors = []
      page.on("pageerror", error => errors.push(error.message))
      const cdp = await context.newCDPSession(page)
      await cdp.send("Network.enable")
      await cdp.send("Network.setCacheDisabled", { cacheDisabled: true })
      await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: 1_600_000 / 8, uploadThroughput: 750_000 / 8 })
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 })
      await page.addInitScript(() => {
        window.__measurement = { longTasks: 0, longTaskMs: 0, maxLayoutShiftWindow: 0 }
        let windowStart = 0, previous = 0, score = 0
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) {
            window.__measurement.longTasks++
            window.__measurement.longTaskMs += entry.duration
          }
        }).observe({ type: "longtask", buffered: true })
        new PerformanceObserver(list => {
          for (const entry of list.getEntries()) {
            if (entry.hadRecentInput) continue
            if (entry.startTime - previous > 1000 || entry.startTime - windowStart > 5000) {
              windowStart = entry.startTime
              score = 0
            }
            previous = entry.startTime
            score += entry.value
            window.__measurement.maxLayoutShiftWindow = Math.max(window.__measurement.maxLayoutShiftWindow, score)
          }
        }).observe({ type: "layout-shift", buffered: true })
      })
      await page.goto(baseURL + sample.path, { waitUntil: "domcontentloaded" })
      await ready(page, sample.selector)
      const result = await page.evaluate(() => {
        const resources = performance.getEntriesByType("resource")
        const navigation = performance.getEntriesByType("navigation")[0]
        return {
          readyMs: Math.round(performance.now()),
          domContentLoadedMs: Math.round(navigation.domContentLoadedEventEnd),
          transferredBytes: navigation.transferSize + resources.reduce((total, item) => total + item.transferSize, 0),
          requests: resources.length + 1,
          ...window.__measurement,
        }
      })
      if (errors.length) throw new Error(`${sample.name}: ${errors.join("; ")}`)
      results.push({ name: sample.name, run: run + 1, ...result })
      console.log(`${sample.name} #${run + 1}: ${result.readyMs} ms, ${(result.transferredBytes / 1024).toFixed(1)} KiB`)
      await context.close()
    }
  }

  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  const page = await context.newPage()
  const cdp = await context.newCDPSession(page)
  await cdp.send("Performance.enable")
  const index = JSON.parse(await readFile(resolve(dist, "dynamic-content-hotspots-index.json"), "utf8"))
  const terms = Object.entries(index.terms).sort((a, b) => b[1].total - a[1].total).slice(0, 30).map(([term]) => term)
  const memory = []
  await page.goto(baseURL + "/?tab=content&view=content-detail&term=AI")
  await ready(page, "#content-term-trend canvas")
  for (let round = 0; round < 2; round++) {
    for (const [position, term] of terms.entries()) {
      const input = page.getByRole("combobox", { name: "选择标题关键词", exact: true })
      await input.click()
      await input.fill(term)
      await page.getByRole("option").filter({ has: page.locator("strong", { hasText: new RegExp(`^${term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`) }) }).click()
      await page.waitForFunction(term => document.querySelector("#content-term-detail h2")?.textContent === `标题关键词详情：${term}`, term)
      await ready(page, "#content-term-trend canvas")
      if ((position + 1) % 10 === 0) {
        await cdp.send("HeapProfiler.collectGarbage")
        const metrics = await cdp.send("Performance.getMetrics")
        memory.push({ selections: round * terms.length + position + 1, heapMiB: Number((metrics.metrics.find(metric => metric.name === "JSHeapUsedSize").value / 1024 ** 2).toFixed(2)) })
      }
    }
  }
  await context.close()
  await mkdir(dirname(output), { recursive: true })
  const report = { measuredAt: new Date().toISOString(), conditions: { build: "dist", gzip: true, coldBrowserCache: true, viewport: "390x844", cpuSlowdown: 4, latencyMs: 150, downloadMbps: 1.6, runs }, notes: "Local controlled measurements, not live-site timings or field INP. Ready time includes nonblank canvas verification. Memory walk is unthrottled; round two revisits the same 30 terms after GC.", results, memory }
  report.dataVersion = dataVersion
  if (baseline) report.comparison = comparePerformance(report, baseline)
  await writeFile(output, JSON.stringify(report, null, 2) + "\n")
  console.log(`Report: ${output}`)
  console.log(JSON.stringify(memory))
  if (report.comparison) {
    console.table(report.comparison)
    if (report.comparison.some(item => item.regression)) process.exitCode = 1
  }
} finally {
  await browser?.close()
  await new Promise(resolve => server.close(resolve))
}
