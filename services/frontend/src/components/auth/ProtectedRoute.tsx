'use client'

import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { authRedirect } from '@/utils/authRedirect'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect } from 'react'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, isLoading } = useAuth()
  const { t } = useI18n()
  const router = useRouter()
  const pathname = usePathname()

  const isPublicRoute = authRedirect.isPublicRoute(pathname || '/')

  useEffect(() => {
    // Don't redirect if still loading or on a public route
    if (isLoading || isPublicRoute) {
      return
    }

    // If user is not authenticated and trying to access a protected route
    // Only redirect when auth state is stable (not loading)
    if (!user && !isLoading) {
      authRedirect.toLogin(router)
    }
  }, [user, isLoading, isPublicRoute, router, pathname])

  // For public routes, always render children (don't wait for auth to load)
  if (isPublicRoute) {
    return <>{children}</>
  }

  // Loading state is handled by ConditionalLayout for better positioning
  // Return null to prevent any layout interference during loading
  if (isLoading) {
    return null
  }

  // For protected routes, only render if user is authenticated
  if (user) {
    return <>{children}</>
  }

  // If not authenticated and trying to access protected route, show loading
  // (redirect will happen in useEffect)
  return (
    <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
        <p className="text-zinc-600 dark:text-zinc-400">{t('common.redirecting')}</p>
      </div>
    </div>
  )
}
