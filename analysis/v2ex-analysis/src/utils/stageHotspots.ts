export type StageHotspot = {
  key: string
  start: string
  peak: string
  end: string
  peakCount: number
  peakShare: number
  baselineShare: number
  lift: number | null
  score: number
}

export type StageHotspotRow = [
  string, string, string, string, number, number, number, number | null, number,
]

function parseStageHotspot(row: StageHotspotRow): StageHotspot {
  return {
    key: row[0], start: row[1], peak: row[2], end: row[3], peakCount: row[4],
    peakShare: row[5], baselineShare: row[6], lift: row[7], score: row[8],
  }
}

export function stageHotspotsForRange(
  rows: StageHotspotRow[] | undefined,
  periods: string[],
  limit = 10,
): StageHotspot[] {
  if (!rows?.length || !periods.length) return []
  const rangeStart = periods[0]
  const rangeEnd = periods[periods.length - 1]
  const bestByKey = new Map<string, StageHotspot>()
  for (const row of rows) {
    const item = parseStageHotspot(row)
    if (item.peak < rangeStart || item.peak > rangeEnd) continue
    item.start = item.start < rangeStart ? rangeStart : item.start
    item.end = item.end > rangeEnd ? rangeEnd : item.end
    const previous = bestByKey.get(item.key)
    if (!previous || item.score > previous.score) bestByKey.set(item.key, item)
  }
  return [...bestByKey.values()]
    .sort((left, right) => right.score - left.score || right.peakCount - left.peakCount || left.key.localeCompare(right.key, "zh-CN"))
    .slice(0, limit)
}
