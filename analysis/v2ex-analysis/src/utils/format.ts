const dashboardDateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
})

export function formatNumber(value: number | undefined, digits = 0) {
  return Number(value || 0).toLocaleString("zh-CN", {
    maximumFractionDigits: digits,
  })
}

export function formatKnownNumber(value: number | undefined, digits = 0) {
  if (value === undefined || !Number.isFinite(value) || value < 0) return "未知"
  return formatNumber(value, digits)
}

export function formatDateTime(timestamp: number | undefined) {
  if (!timestamp) return "时间未知"
  const parts = dashboardDateTimeFormatter.formatToParts(
    new Date(timestamp * 1000),
  )
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find(item => item.type === type)?.value || ""
  return `${value("year")}-${value("month")}-${value("day")} ${value("hour")}:${value("minute")}`
}

export function formatCommentContent(content: string | undefined) {
  const normalized = (content || "").trim()
  if (!normalized) return "评论原文未收录"
  const parts = normalized.split(/\s+/)
  if (parts.every(part => part === "[图片]" || part === "[视频]")) {
    const mediaTypes = new Set(parts)
    if (mediaTypes.size === 1) {
      return `${parts[0].slice(1, -1)}评论，点击查看原帖`
    }
    return "媒体评论，点击查看原帖"
  }
  return normalized
}
