import { headers } from 'next/headers'

import { isStudentLockedHost } from '@/lib/utils/subdomain'

import BengerLandingClient from './BengerLandingClient'
import VertretbarLandingPage from './vertretbar/page'

// Resolve the external host server-side (x-forwarded-host behind Traefik/k8s,
// falling back to host). Lets us decide benger-vs-Vertretbar BEFORE render.
async function resolveHost(): Promise<string> {
  const h = await headers()
  return h.get('x-forwarded-host') || h.get('host') || ''
}

// (Tab title is set host-aware in the root layout's generateMetadata.)

/**
 * Root landing. The host is resolved SERVER-SIDE so the correct tree renders on
 * the first paint — no benger-branding flash on vertretbar.net.
 * - Student-locked host (vertretbar.net) → the Vertretbar landing gate (a neutral
 *   spinner SSR, then the branded VertretbarLanding after mount).
 * - Otherwise → the benger marketing landing.
 * (The old middleware "/"→"/vertretbar" rewrite never built into the image; this
 * makes the routing robust without depending on it.)
 */
export default async function Page() {
  if (isStudentLockedHost(await resolveHost())) {
    return <VertretbarLandingPage />
  }
  return <BengerLandingClient />
}
