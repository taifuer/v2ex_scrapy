import { createHash } from "node:crypto"
import { execFileSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { fileURLToPath, URL } from "node:url"
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

function analyticsVersion() {
  try {
    const manifest = readFileSync(fileURLToPath(new URL("./public/dynamic-manifest.json", import.meta.url)))
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

export default defineConfig({
  plugins: [vue()],
  define: {
    __ANALYTICS_VERSION__: JSON.stringify(analyticsVersion()),
    __APP_VERSION__: JSON.stringify(repositoryVersion()),
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
})
