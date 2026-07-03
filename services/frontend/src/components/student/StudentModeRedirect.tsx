'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/hooks/useHydration'
import { useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

/**
 * Routes student-mode users away from the expert landing surfaces (Issue #35).
 *
 * ONLY acts on `/` and `/dashboard`: when the resolved UI mode is 'student',
 * it replaces the route with `/student`. Every other path is left alone so
 * deep links into expert pages still work (the toggle is how a student would
 * get there in the first place).
 *
 * It keys exclusively on the resolved UI mode — there is intentionally NO
 * profile-completion gate. Renders nothing.
 */
export function StudentModeRedirect() {
  const pathname = usePathname()
  const router = useRouter()
  const { user, isLoading } = useAuth()
  const isHydrated = useHydration()
  const resolvedUiMode = useResolvedUiMode()
  // Only presence matters here — a logged-out visitor has no view mode to
  // honour and must not be bounced off the public landing page.
  const isAuthenticated = !!user

  useEffect(() => {
    if (!isHydrated || isLoading) return
    if (!isAuthenticated) return
    if (resolvedUiMode !== 'student') return

    const onRedirectableRoute = pathname === '/' || pathname === '/dashboard'
    if (onRedirectableRoute) {
      router.replace('/student')
    }
  }, [isHydrated, isLoading, isAuthenticated, resolvedUiMode, pathname, router])

  return null
}
