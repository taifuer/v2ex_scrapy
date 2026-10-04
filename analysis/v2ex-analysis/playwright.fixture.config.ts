import { defineConfig, devices } from "@playwright/test"

if (!process.env.V2EX_DASHBOARD_PUBLIC_DIR) throw new Error("Set V2EX_DASHBOARD_PUBLIC_DIR to the generated synthetic public directory")
const port = Number(process.env.PLAYWRIGHT_PORT || 5194)
const baseURL = `http://127.0.0.1:${port}`
export default defineConfig({
  testDir: "./tests/fixture",
  workers: 1,
  timeout: 30_000,
  use: { baseURL },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
  webServer: {
    command: `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
})
