'use client'

import { AuthPageFrame } from '@/components/layout/AuthPageFrame'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'

/**
 * The LMS launch steps before a session exists (consent, account choice,
 * link confirmation, launch errors) share the login page's frame: the
 * host's wordmark and the language and theme controls. They are standalone
 * pages (ConditionalLayout.standalonePages). The teacher picker (/lti/link)
 * and the activity overview (/lti/activity) run inside the app layout and
 * pass through unchanged.
 */
const PRE_SESSION_PREFIXES = [
  '/lti/consent',
  '/lti/link-account',
  '/lti/link-confirm',
  '/lti/error',
]

export default function LtiLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? ''
  const preSession = PRE_SESSION_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
  if (!preSession) return <>{children}</>
  return (
    <AuthPageFrame showBackLink={false} contentTestId="lti-page-content">
      {children}
    </AuthPageFrame>
  )
}
