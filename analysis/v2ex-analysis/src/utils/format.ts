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

export function formatDateTime(timestamp: number | undefined) {
  if (!timestamp) return "时间未知"
  const parts = dashboardDateTimeFormatter.formatToParts(
    new Date(timestamp * 1000),
  )
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find(item => item.type === type)?.value || ""
  return `${value("year")}-${value("month")}-${value("day")} ${value("hour")}:${value("minute")}`
}
