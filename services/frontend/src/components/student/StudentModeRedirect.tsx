'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useHydration } from '@/hooks/useHydration'
import { useResolvedUiMode } from '@/hooks/useResolvedUiMode'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

/**
 * Keeps each user on the surface that matches their resolved UI mode (Issue #35).
 *
 * - student mode → the expert landing surfaces (`/`, `/dashboard`) are pulled
 *   into the student home (`/student`).
 * - expert mode → the `/student/*` surface is a CLOSED BETA and unreachable
 *   here (it only renders on student-locked hosts like vertretbar.net). Any
 *   navigation onto a `/student` route is bounced back to `/dashboard`, so an
 *   org admin/contributor can't land on the student pages via the view toggle
 *   or a direct URL.
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

    const onStudentRoute = pathname === '/student' || pathname.startsWith('/student/')

    if (resolvedUiMode === 'student') {
      if (pathname === '/' || pathname === '/dashboard') {
        router.replace('/student')
      }
    } else if (onStudentRoute) {
      // Closed beta: expert-mode users (i.e. everyone off a student-locked host)
      // must never sit on the student surface. Bounce back to the classic home.
      router.replace('/dashboard')
    }
  }, [isHydrated, isLoading, isAuthenticated, resolvedUiMode, pathname, router])

  return null
}
