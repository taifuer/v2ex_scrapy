import { createHash } from "node:crypto"
import { execFileSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { fileURLToPath, URL } from "node:url"
import { resolve } from "node:path"
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { applicationVersion, releasePlugin } from "./scripts/release"

const publicDir = process.env.V2EX_DASHBOARD_PUBLIC_DIR
  ? resolve(process.env.V2EX_DASHBOARD_PUBLIC_DIR)
  : fileURLToPath(new URL("./public", import.meta.url))

function analyticsVersion() {
  try {
    const manifest = readFileSync(resolve(publicDir, "dynamic-manifest.json"))
    return createHash("sha256").update(manifest).digest("hex").slice(0, 12)
  } catch {
    return "development"
  }
}

function repositoryVersion() {
  try {
    const root = fileURLToPath(new URL("../../", import.meta.url))
    const commit = execFileSync("git", ["rev-parse", "--short=12", "HEAD"], {
      cwd: root,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim()
    const dirty = execFileSync("git", ["status", "--short", "--untracked-files=no"], {
      cwd: root,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim()
    return `${commit}${dirty ? "+dirty" : ""}`
  } catch {
    return "unknown"
  }
}

const dataVersion = analyticsVersion()
const appVersion = applicationVersion(fileURLToPath(new URL(".", import.meta.url)), dataVersion)

export default defineConfig({
  publicDir,
  plugins: [vue(), releasePlugin(dataVersion, appVersion)],
  define: {
    __ANALYTICS_VERSION__: JSON.stringify(dataVersion),
    __BUILD_VERSION__: JSON.stringify(appVersion),
    __APP_VERSION__: JSON.stringify(repositoryVersion()),
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
})
