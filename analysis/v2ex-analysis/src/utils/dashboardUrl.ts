export const dashboardQueryKeys = [
  "tab", "view", "overview", "community", "from", "to", "grain", "mode", "tag", "term", "tagCompare", "termCompare", "node", "member", "period", "topicPeriod",
  "topicTop", "trendTop", "nodeTop", "memberMetric", "memberTop",
  "topicList", "contentTop", "contentTrendTop", "contentMode", "postSort", "topicPage", "repPage", "postPage", "commentPage",
  "observation", "signal",
] as const

export function integerParam(params: URLSearchParams, key: string, allowed?: number[]) {
  const raw = params.get(key) || ""
  if (!/^\d+$/.test(raw)) return null
  const value = Number.parseInt(raw, 10)
  if (!Number.isInteger(value) || value < 1 || (allowed && !allowed.includes(value))) return null
  return value
}

export function safeTagParam(value: string | null) {
  const tag = (value || "").trim()
  return tag.length <= 64 && !/[\u0000-\u001f\u007f<>\\/#?&]/.test(tag) ? tag : ""
}

export function safeComparisonParams(params: URLSearchParams, key: string, exclude: string) {
  const values: string[] = []
  for (const raw of params.getAll(key)) {
    const value = safeTagParam(raw)
    if (!value || value === exclude || values.includes(value)) continue
    values.push(value)
    if (values.length === 4) break
  }
  return values
}

export function safeMemberParam(value: string | null) {
  const member = (value || "").trim()
  return /^[A-Za-z0-9_-]{1,64}$/.test(member) ? member : ""
}

export function safeNodeParam(value: string | null) {
  const node = (value || "").trim()
  return node.length <= 64 && !/[\u0000-\u001f\u007f<>\\/#?&]/.test(node) ? node : ""
}
