import { gzipSync } from "node:zlib"
import { readdirSync, readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const assetsDir = resolve(root, "dist/assets")
const publicDir = resolve(root, "public")
const kib = 1024

function gzipSize(path) {
  return gzipSync(readFileSync(path), { level: 6 }).length
}

function matchingSizes(directory, pattern) {
  return readdirSync(directory)
    .filter(name => pattern.test(name))
    .map(name => ({ name, size: gzipSize(resolve(directory, name)) }))
}

function requireBudget(label, rows, limit) {
  if (!rows.length) throw new Error(`${label}: no matching files`)
  const largest = rows.reduce((left, right) => left.size >= right.size ? left : right)
  if (largest.size > limit) {
    throw new Error(`${label}: ${largest.name} is ${(largest.size / kib).toFixed(1)} KiB gzip; limit is ${(limit / kib).toFixed(0)} KiB`)
  }
  console.log(`${label}: ${(largest.size / kib).toFixed(1)} / ${(limit / kib).toFixed(0)} KiB gzip (${largest.name})`)
}

const scripts = matchingSizes(assetsDir, /\.js$/)
const scriptTotal = scripts.reduce((total, item) => total + item.size, 0)
if (scriptTotal > 320 * kib) {
  throw new Error(`all JavaScript chunks total ${(scriptTotal / kib).toFixed(1)} KiB gzip; limit is 320 KiB`)
}

requireBudget("main application", scripts.filter(item => /^index-.*\.js$/.test(item.name)), 85 * kib)
requireBudget("ECharts runtime", scripts.filter(item => /^chartRuntime-.*\.js$/.test(item.name)), 225 * kib)
requireBudget("stylesheet", matchingSizes(assetsDir, /\.css$/), 15 * kib)
requireBudget("analytics JSON shard", matchingSizes(publicDir, /^dynamic-.*\.json$/), 480 * kib)
console.log(`all JavaScript chunks: ${(scriptTotal / kib).toFixed(1)} / 320 KiB gzip`)
