'use client'

import { useAuth } from '@/components/auth/SimpleAuth'
import { logger } from '@/lib/utils/logger'
import { useToast } from '@/components/shared/SimpleToast'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

export function SimpleAuthFailureHandler() {
  const { user, isLoading, logout } = useAuth()
  const { addToast } = useToast()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    const handleAuthFailure = async () => {
      // Don't trigger on public pages or during initial loading
      const publicPages = ['/', '/login', '/register', '/reset-password']
      const isPublicPage = publicPages.includes(pathname || '/')

      // Don't show session expired if:
      // 1. We're on a public page (expected to not be authenticated)
      // 2. Auth is still loading (initial auth check)
      // 3. User was never authenticated in this session
      if (isPublicPage || isLoading || !user) {
        logger.debug(
          'Auth failure on public page or during loading - skipping session expired message'
        )
        return
      }

      logger.debug('Session expired - showing toast and logging out user')

      try {
        // Show toast notification
        addToast('Your session has expired. Please log in again.', 'warning')
      } catch (error) {
        // Continue even if toast fails
        console.warn('Failed to show session expired toast:', error)
      }

      // Perform logout which will clear state and redirect
      try {
        await logout()
      } catch (error) {
        // If logout fails, at least redirect to home
        try {
          router.push('/')
        } catch (routerError) {
          console.warn('Failed to redirect after logout failure:', routerError)
        }
      }
    }

    // For now, we'll just set up the handler (no API client mock)
    logger.debug('SimpleAuthFailureHandler ready')
  }, [addToast, logout, router, pathname, user, isLoading])

  return null
}
