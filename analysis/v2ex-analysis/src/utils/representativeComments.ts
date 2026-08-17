import type { RepresentativeComment, RepresentativeCommentSummary } from "../types/analytics"

export type PeriodRepresentativeComments = {
  comments: RepresentativeComment[]
  summary: RepresentativeCommentSummary
}

function periodSummary(
  rankings: Record<string, any>,
  fromPeriod: string,
  toPeriod: string,
): RepresentativeCommentSummary {
  let thankedComments = 0
  let commentThanks = 0
  for (const [period, ranking] of Object.entries(rankings)) {
    if (!/^\d{4}-\d{2}$/.test(period) || period < fromPeriod || period > toPeriod) continue
    thankedComments += Number(ranking?.thanked_comments || 0)
    commentThanks += Number(ranking?.comment_thanks || 0)
  }
  return { thanked_comments: thankedComments, comment_thanks: commentThanks }
}

function rankedComments(
  ids: number[],
  payloads: Record<string, RepresentativeComment>,
  fromPeriod: string,
  toPeriod: string,
  limit?: number,
) {
  const comments = [...new Set(ids)]
    .map(id => payloads[String(id)])
    .filter((comment: RepresentativeComment | undefined): comment is RepresentativeComment => Boolean(
      comment && comment.topic_period >= fromPeriod && comment.topic_period <= toPeriod,
    ))
    .sort((left, right) => right.thank_count - left.thank_count || right.id - left.id)
  return limit ? comments.slice(0, limit) : comments
}

export function commentsForPeriod(
  payload: any,
  entity: string,
  period: string,
  fromPeriod = period.length === 4 ? `${period}-01` : period,
  toPeriod = period.length === 4 ? `${period}-12` : period,
): PeriodRepresentativeComments {
  const rankings = payload?.comment_rankings?.[entity] || {}
  const ranking = rankings[period]
  const effectiveFrom = period.length === 4 ? `${period}-01` : period
  const effectiveTo = period.length === 4 ? `${period}-12` : period
  const boundedFrom = effectiveFrom > fromPeriod ? effectiveFrom : fromPeriod
  const boundedTo = effectiveTo < toPeriod ? effectiveTo : toPeriod

  return {
    comments: rankedComments(
      ranking?.ids || [],
      payload?.comment_payloads || {},
      boundedFrom,
      boundedTo,
    ),
    summary: periodSummary(rankings, boundedFrom, boundedTo),
  }
}

export function commentsForRange(
  payload: any,
  entity: string,
  fromPeriod: string,
  toPeriod: string,
  limit?: number,
): PeriodRepresentativeComments {
  const rankings = payload?.comment_rankings?.[entity] || {}
  const startYear = Number(fromPeriod.slice(0, 4))
  const endYear = Number(toPeriod.slice(0, 4))
  const ids: number[] = []
  for (let year = startYear; year <= endYear; year += 1) {
    ids.push(...(rankings[String(year)]?.ids || []))
  }
  return {
    comments: rankedComments(ids, payload?.comment_payloads || {}, fromPeriod, toPeriod, limit),
    summary: periodSummary(rankings, fromPeriod, toPeriod),
  }
}
