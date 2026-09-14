/**
 * Serve the test stack under an organization subdomain.
 *
 * The app derives its organization context from the host name alone: an
 * organization is active when the page runs on `<slug>.<base domain>`, with
 * the base domains listed in `src/lib/utils/subdomain.ts` (`benger.localhost`
 * for local stacks). The ephemeral test stack is reachable only as
 * `benger-test.localhost`, which is not a base domain, so no page there ever
 * runs inside an organization. Switching organizations in the UI does not
 * help either: it navigates to `<slug>.benger-test.localhost`, which the test
 * stack's Traefik does not route.
 *
 * `startOrgHost` closes that gap without changing the stack. It listens on a
 * free loopback port and forwards every request to the test stack with only
 * the Host header rewritten, so the browser talks to
 * `http://<slug>.benger.localhost:<port>` while the unmodified stack answers.
 * Chromium resolves every `*.localhost` name to loopback on its own, so no
 * hosts file is needed. Session cookies are host-only on the org host: log in
 * through the returned origin, not through the bare test host.
 */
import * as http from 'node:http'
import type { AddressInfo } from 'node:net'

export interface OrgHost {
  /** For example `http://tum.benger.localhost:53121`. Use it as `baseURL`. */
  origin: string
  close: () => Promise<void>
}

export async function startOrgHost(
  slug: string,
  upstreamBaseUrl: string,
): Promise<OrgHost> {
  const upstream = new URL(upstreamBaseUrl)
  if (upstream.protocol !== 'http:') {
    throw new Error(
      `startOrgHost forwards plain HTTP only, got ${upstream.origin}`,
    )
  }
  // A `*.localhost` name is loopback by definition. Connecting to 127.0.0.1
  // avoids depending on how the local resolver orders ::1 and 127.0.0.1.
  const connectHost =
    upstream.hostname === 'localhost' ||
    upstream.hostname.endsWith('.localhost')
      ? '127.0.0.1'
      : upstream.hostname
  const upstreamPort = Number(upstream.port) || 80
  let origin = ''

  const server = http.createServer((req, res) => {
    const forward = http.request(
      {
        host: connectHost,
        port: upstreamPort,
        method: req.method,
        path: req.url,
        headers: { ...req.headers, host: upstream.host },
      },
      (upstreamRes) => {
        const headers = { ...upstreamRes.headers }
        // An absolute redirect back to the bare test host would silently
        // drop the organization context. Keep it on the org host.
        if (
          typeof headers.location === 'string' &&
          headers.location.startsWith(upstream.origin)
        ) {
          headers.location =
            origin + headers.location.slice(upstream.origin.length)
        }
        res.writeHead(upstreamRes.statusCode ?? 502, headers)
        upstreamRes.pipe(res)
      },
    )
    forward.on('error', (err) => {
      if (!res.headersSent) {
        res.writeHead(502, { 'content-type': 'text/plain' })
      }
      res.end(`org host proxy: ${err.message}`)
    })
    req.pipe(forward)
  })

  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => resolve())
  })
  const { port } = server.address() as AddressInfo
  origin = `http://${slug}.benger.localhost:${port}`

  return {
    origin,
    close: () =>
      new Promise<void>((resolve) => {
        // The notification stream never ends on its own, so a plain close()
        // would wait for it forever.
        server.closeAllConnections()
        server.close(() => resolve())
      }),
  }
}
