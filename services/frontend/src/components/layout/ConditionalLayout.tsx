'use client'

import { ProtectedRoute } from '@/components/auth/ProtectedRoute'
import { Layout } from '@/components/layout/Layout'
import { MinimalLayout } from '@/components/layout/MinimalLayout'
import { type Section } from '@/components/layout/SectionProvider'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'

interface ConditionalLayoutProps {
  children: React.ReactNode
  allSections: Record<string, Array<Section>>
}

export function ConditionalLayout({
  children,
  allSections,
}: ConditionalLayoutProps) {
  const pathname = usePathname()
  const { isLoading, user } = useAuth()
  const { t } = useI18n()
  const [showLoadingDelay, setShowLoadingDelay] = useState(false)

  // Only show loading spinner after a delay to avoid flash for fast loads
  useEffect(() => {
    let timer: NodeJS.Timeout
    if (isLoading) {
       
      timer = setTimeout(() => setShowLoadingDelay(true), 200) // 200ms delay
    } else {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: sync loading state
      setShowLoadingDelay(false)
    }
    return () => clearTimeout(timer)
  }, [isLoading])

  // Pages that should NOT use the app layout (sidebar/navbar)
  const standalonePages = [
    '/', // Landing page
    '/login', // Login page
    '/register', // Registration page
    '/reset-password', // Password reset (includes token routes)
    '/verify-email', // Email verification (includes token routes)
    '/accept-invitation', // Organization invitation (includes token routes)
  ]

  // Pages that need minimal layout (with SectionProvider but no sidebar)
  const minimalLayoutPages: string[] = [
    // Removed /about/imprint and /about/data-protection to use full layout
  ]

  // Legal pages that should use minimal layout for unauthenticated users
  const legalPages = ['/about/imprint', '/about/data-protection']

  // Check if the current path is a standalone page
  // For pages with dynamic routes (like /verify-email/[token]), check if path starts with the base
  const isStandalonePage = standalonePages.some((page) => {
    if (page === '/') {
      return pathname === '/'
    }
    // For other pages, check if the pathname starts with the page path
    return pathname?.startsWith(page) || false
  })

  const isMinimalLayoutPage = minimalLayoutPages.includes(pathname || '/')

  // Check if current page is a legal page
  const isLegalPage = legalPages.some((page) => pathname === page)

  // Legal pages should use minimal layout for unauthenticated users
  const shouldUseMinimalLayoutForLegal = isLegalPage && !user

  // If auth is loading and we're not on a standalone page, show the auth loading state
  // without any layout constraints to ensure proper centering
  // Only show after delay to avoid flash for fast loads
  if (isLoading && showLoadingDelay && !isStandalonePage) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('common.checkingAuth')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <ProtectedRoute>
      {/* For basic standalone pages, render children directly without any layout */}
      {isStandalonePage ? (
        <div className="w-full">{children}</div>
      ) : isMinimalLayoutPage || shouldUseMinimalLayoutForLegal ? (
        /* For MDX standalone pages and unauthenticated legal pages, use minimal layout with SectionProvider */
        <MinimalLayout sections={allSections[pathname || '/'] ?? []}>
          {children}
        </MinimalLayout>
      ) : (
        /* For all other pages and authenticated legal pages, use the full app layout with sidebar/navbar */
        <div className="w-full">
          <Layout allSections={allSections}>{children}</Layout>
        </div>
      )}
    </ProtectedRoute>
  )
}
