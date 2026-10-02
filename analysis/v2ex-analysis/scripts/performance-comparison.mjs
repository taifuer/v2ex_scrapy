const CONDITION_KEYS = ["gzip", "coldBrowserCache", "viewport", "cpuSlowdown", "latencyMs", "downloadMbps"]

export function median(values) {
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

export function comparePerformance(current, baseline) {
  for (const key of CONDITION_KEYS) {
    if (current.conditions[key] !== baseline.conditions[key]) throw new Error(`Incomparable performance condition: ${key}`)
  }
  if (!current.dataVersion || current.dataVersion !== baseline.dataVersion) throw new Error("Performance comparison requires the same analysis data")
  const names = new Set(current.results.map(row => row.name))
  const baselineNames = new Set(baseline.results.map(row => row.name))
  if (names.size !== baselineNames.size || [...baselineNames].some(name => !names.has(name))) {
    throw new Error("Performance comparison requires the same page cases")
  }
  return [...names].map(name => {
    const currentRuns = current.results.filter(row => row.name === name).map(row => row.readyMs)
    const baselineRuns = baseline.results.filter(row => row.name === name).map(row => row.readyMs)
    if (currentRuns.length < 3 || baselineRuns.length < 3 || [...currentRuns, ...baselineRuns].some(value => !Number.isFinite(value) || value <= 0)) {
      throw new Error(`${name}: at least three valid measurements are required`)
    }
    const beforeMs = median(baselineRuns)
    const afterMs = median(currentRuns)
    const deltaMs = Math.round(afterMs - beforeMs)
    const limitMs = Math.max(500, beforeMs * 0.2)
    return { name, beforeMs, afterMs, deltaMs, limitMs, regression: deltaMs > limitMs }
  })
}
