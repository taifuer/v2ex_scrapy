import type { PaginationItem } from "../types/analytics"

export function paginationItems(current: number, total: number): PaginationItem[] {
  if (total <= 9) return Array.from({ length: total }, (_, index) => index + 1)
  let start = Math.max(2, current - 2)
  let end = Math.min(total - 1, current + 2)
  if (current <= 4) end = 6
  if (current >= total - 3) start = total - 5
  const items: PaginationItem[] = [1]
  if (start > 2) items.push("gap-start")
  for (let page = start; page <= end; page += 1) items.push(page)
  if (end < total - 1) items.push("gap-end")
  items.push(total)
  return items
}
