export type AggregateItemDisplayRule = {
  minimum_count?: number
  minimum_share?: number
  absolute_count?: number
}

const defaultRule: Required<AggregateItemDisplayRule> = {
  minimum_count: 3,
  minimum_share: 0.01,
  absolute_count: 100,
}

export function aggregateItemDisplayMinimum(
  groupCount: number,
  rule: AggregateItemDisplayRule = defaultRule,
) {
  const minimumCount = Math.max(1, Number(rule.minimum_count ?? defaultRule.minimum_count))
  const minimumShare = Math.max(0, Number(rule.minimum_share ?? defaultRule.minimum_share))
  const absoluteCount = Math.max(minimumCount, Number(rule.absolute_count ?? defaultRule.absolute_count))
  const proportionalCount = Math.max(minimumCount, Math.ceil(Math.max(0, groupCount) * minimumShare))
  return Math.min(proportionalCount, absoluteCount)
}
