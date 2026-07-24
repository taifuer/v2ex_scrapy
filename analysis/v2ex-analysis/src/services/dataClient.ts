const responseCache = new Map<string, Promise<unknown>>()

type JsonRequestOptions = {
  timeout?: number
  retries?: number
  signal?: AbortSignal
  cache?: boolean
}

function sleep(delay: number) {
  return new Promise((resolve) => window.setTimeout(resolve, delay))
}

async function requestJson<T>(path: string, options: JsonRequestOptions): Promise<T> {
  const attempts = Math.max(1, (options.retries ?? 1) + 1)
  let lastError: unknown

  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), options.timeout ?? 15000)
    const abort = () => controller.abort()
    options.signal?.addEventListener("abort", abort, { once: true })
    try {
      const response = await fetch(path, { signal: controller.signal })
      if (!response.ok) throw new Error(`加载 ${path} 失败：${response.status}`)
      return await response.json() as T
    } catch (error) {
      lastError = error
      if (options.signal?.aborted || attempt >= attempts - 1) throw error
      await sleep(250 * (attempt + 1))
    } finally {
      window.clearTimeout(timeout)
      options.signal?.removeEventListener("abort", abort)
    }
  }
  throw lastError
}

export function getJson<T = any>(path: string, options: JsonRequestOptions = {}): Promise<T> {
  if (options.cache === false || options.signal) return requestJson<T>(path, options)
  const cached = responseCache.get(path)
  if (cached) return cached as Promise<T>
  const request = requestJson<T>(path, options).catch((error) => {
    responseCache.delete(path)
    throw error
  })
  responseCache.set(path, request)
  return request
}

export function clearJsonCache(path?: string) {
  if (path) responseCache.delete(path)
  else responseCache.clear()
}
