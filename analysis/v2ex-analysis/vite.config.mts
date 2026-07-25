import { createHash } from "node:crypto"
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

export default defineConfig({
  plugins: [vue()],
  define: {
    __ANALYTICS_VERSION__: JSON.stringify(analyticsVersion()),
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
})
