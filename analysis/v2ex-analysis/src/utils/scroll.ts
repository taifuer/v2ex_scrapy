export function scrollToSection(id: string) {
  const element = document.getElementById(id)
  if (!element) return
  const behavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"
  element.scrollIntoView({ behavior, block: "start" })
}
