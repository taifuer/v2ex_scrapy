import { ref } from "vue"

export const releaseUpdated = ref(false)
export const resourceLoadFailed = ref(false)
let releaseCheck: Promise<boolean> | undefined

export function markReleaseUpdated() {
  releaseUpdated.value = true
}

export function checkForNewRelease(): Promise<boolean> {
  if (releaseUpdated.value) return Promise.resolve(true)
  if (releaseCheck) return releaseCheck
  releaseCheck = (async () => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 4000)
    try {
      const response = await fetch(`/assets/app-release.json?t=${Date.now()}`, { cache: "no-store", signal: controller.signal })
      if (!response.ok) return false
      const release = await response.json()
      if (typeof release.version === "string" && release.version !== __BUILD_VERSION__) markReleaseUpdated()
      return releaseUpdated.value
    } catch {
      return false
    } finally {
      window.clearTimeout(timeout)
      releaseCheck = undefined
    }
  })()
  return releaseCheck
}

export function installReleaseRecovery() {
  window.addEventListener("vite:preloadError", event => {
    event.preventDefault()
    void checkForNewRelease().then(updated => {
      if (!updated) resourceLoadFailed.value = true
    })
  })
}
