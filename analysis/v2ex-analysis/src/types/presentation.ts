export type PresentationMetric = { value: string; label: string; detail?: string }

export type PresentationPost = {
  id: number
  title: string
  node: string
  date: string
  clicks: number | null
  favorites: number | null
  thanks: number | null
  replies: number | null
  url: string
  badge: string
  selection: string
  note: string
  excerpt?: string
}

export type PresentationSlide = {
  id: string
  type: "cover" | "facts" | "chart" | "timeline" | "posts" | "conclusion" | "explore"
  chapter: string
  eyebrow: string
  title: string
  summary: string
  note?: string
  chart?: string
  metrics?: PresentationMetric[]
  posts?: PresentationPost[]
  comments?: { id: number; topic_id: number; username: string; date: string; text: string; thanks: number; url: string; note: string }[]
  definitions?: { title: string; text: string }[]
  milestones?: { period: string; title: string; items: { label: string; count: number }[]; text?: string }[]
  takeaways?: { number: string; title: string; text: string }[]
}
