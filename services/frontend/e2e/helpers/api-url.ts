// The API hosts Traefik serves next to each frontend host.
const API_HOSTS: Record<string, string> = {
  'benger-test.localhost': 'api-test.localhost',
  'benger.localhost': 'api.localhost',
}

/**
 * The API's own origin, reached without the Next.js routes on the frontend
 * host. PLAYWRIGHT_API_URL wins; otherwise the API host that Traefik serves
 * next to the frontend host. Returns null when the base URL is not a known
 * local stack.
 */
export function apiBaseUrl(baseURL: string): string | null {
  const explicit = process.env.PLAYWRIGHT_API_URL
  if (explicit) return explicit.replace(/\/+$/, '')
  const url = new URL(baseURL)
  const apiHost = API_HOSTS[url.hostname]
  if (!apiHost) return null
  url.hostname = apiHost
  return url.origin
}
