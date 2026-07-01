'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'

import { useAuth } from '@/contexts/AuthContext'
import { useSlot } from '@/lib/extensions/slots'
import { isStudentLockedHost } from '@/lib/utils/subdomain'

/**
 * Dedicated landing for unauthenticated visitors on a student-locked host
 * (vertretbar.net). Reached server-side: the middleware rewrites "/" here on
 * those hosts (URL stays "/"), so benger branding never flashes.
 *
 * - Authenticated users go straight to the student area (never the benger home).
 * - The actual branded landing is the extended `VertretbarLanding` slot; a
 *   neutral spinner shows until it (or auth) resolves.
 * - Reached on a non-locked host (direct nav) → bounce to the benger landing.
 */
function Spinner() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-950">
      <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-indigo-500" />
    </div>
  )
}

export default function VertretbarLandingPage() {
  const { user, isLoading } = useAuth()
  const router = useRouter()
  const VertretbarLanding = useSlot('VertretbarLanding')

  const [mounted, setMounted] = useState(false)
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setMounted(true) }, [])

  // Guard: this route only makes sense on a student-locked host.
  useEffect(() => {
    if (mounted && !isStudentLockedHost()) {
      router.replace('/')
    }
  }, [mounted, router])

  // Authenticated → straight into the student app.
  useEffect(() => {
    if (mounted && !isLoading && user) {
      router.replace('/student')
    }
  }, [mounted, isLoading, user, router])

  if (!mounted || isLoading || user) {
    return <Spinner />
  }

  if (!VertretbarLanding) {
    // Slot not registered (community build / still loading) — stay neutral.
    return <Spinner />
  }

  // eslint-disable-next-line react-hooks/static-components
  return <VertretbarLanding />
}
