import { createHash } from "node:crypto"
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs"
import { join, relative, resolve } from "node:path"
import type { Plugin } from "vite"

function filesIn(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? filesIn(path) : [path]
  }).sort()
}

export function applicationVersion(root: string, analyticsVersion: string) {
  const hash = createHash("sha256").update(analyticsVersion)
  const files = [
    ...filesIn(join(root, "src")),
    join(root, "scripts/release.ts"),
    ...["index.html", "package-lock.json", "vite.config.mts", "public/favicon.svg"].map(name => join(root, name)),
  ]
  for (const path of files) {
    hash.update(relative(root, path)).update(readFileSync(path))
  }
  return hash.digest("hex").slice(0, 16)
}

export function prepareRelease(dist: string, analyticsVersion: string, appVersion: string) {
  const manifestPath = join(dist, "dynamic-manifest.json")
  const files = readdirSync(dist).filter(name => /^dynamic-.*\.json$/.test(name) && name !== "dynamic-manifest.json")
  for (const name of files) {
    const path = join(dist, name)
    const payload = JSON.parse(readFileSync(path, "utf8"))
    if (!payload || Array.isArray(payload) || typeof payload !== "object") {
      throw new Error(`Expected an analytics object: ${name}`)
    }
    payload._analytics_version = analyticsVersion
    writeFileSync(path, JSON.stringify(payload))
  }
  if (existsSync(manifestPath)) {
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"))
    manifest._analytics_version = analyticsVersion
    manifest.files = Object.fromEntries(files.sort().map(name => [name, statSync(join(dist, name)).size]))
    writeFileSync(manifestPath, JSON.stringify(manifest))
  }
  const assets = filesIn(join(dist, "assets")).map(path => relative(dist, path))
    .filter(name => name !== "assets/app-release.json")
  writeFileSync(join(dist, "assets-current.txt"), `${assets.join("\n")}\n`)
  writeFileSync(join(dist, "assets/app-release.json"), JSON.stringify({ version: appVersion, analytics_version: analyticsVersion }))
}

export function releasePlugin(analyticsVersion: string, appVersion: string): Plugin {
  let dist = ""
  return {
    name: "dashboard-release",
    apply: "build",
    configResolved(config) { dist = resolve(config.root, config.build.outDir) },
    closeBundle() { prepareRelease(dist, analyticsVersion, appVersion) },
  }
}
