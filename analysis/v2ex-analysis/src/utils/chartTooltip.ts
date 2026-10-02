type TooltipRow = { name: string; value: string; detail?: string; marker?: string }

export function escapeHtml(value: unknown) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character] || character)
}

export function chartTooltip(title: unknown, rows: TooltipRow[], columns = 2, viewportWidth = window.innerWidth) {
  const compact = viewportWidth <= 680 || columns === 1
  const width = Math.max(160, Math.min(viewportWidth - 56, compact ? 250 : 380))
  const values = rows.map(row => `<span style="display:flex;align-items:center;gap:8px;min-width:0">`
    + `${row.marker || ""}<span style="flex:1;min-width:0;white-space:normal;overflow-wrap:anywhere">${escapeHtml(row.name)}</span>`
    + `<strong style="text-align:right">${escapeHtml(row.value)}${row.detail ? ` <small style="color:#667085;font-weight:400">${escapeHtml(row.detail)}</small>` : ""}</strong></span>`).join("")
  return `<div class="chart-tooltip" style="width:${width}px;max-height:${compact ? "min(320px,50vh)" : "65vh"};overflow:auto"><strong>${escapeHtml(title)}</strong>`
    + `<div style="display:grid;grid-template-columns:${compact ? "1fr" : "repeat(2,minmax(0,1fr))"};gap:6px 16px;margin-top:8px">${values}</div></div>`
}
