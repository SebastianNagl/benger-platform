'use client'
// BenGER Frontend v3.0.1 - Force rebuild for latest changes

import { HeroSection } from '@/components/landing/HeroSection'
import { InformationSection } from '@/components/landing/InformationSection'
import { LicenseCitationSection } from '@/components/landing/LicenseCitationSection'
import { NewsSection } from '@/components/landing/NewsSection'
import { PeopleSection } from '@/components/landing/PeopleSection'
import { Layout } from '@/components/layout/Layout'
import {
  useSectionStore,
  type Section,
} from '@/components/layout/SectionProvider'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import { isStudentLockedHost } from '@/lib/utils/subdomain'
import { authRedirect } from '@/utils/authRedirect'
import { useRouter } from 'next/navigation'
import { useEffect, useMemo, useState } from 'react'

// The landing sections, in page order. They appear in the visitor sidebar as
// anchors below "Home", the same way a long page's sections appear in the
// signed-in sidebar.
const LANDING_SECTIONS = [
  { id: 'information', key: 'landing.nav.information' },
  { id: 'news', key: 'landing.nav.news' },
  { id: 'people', key: 'landing.nav.people' },
  { id: 'license', key: 'landing.nav.license' },
] as const

/**
 * Hands the section elements to the shell's section store so the sidebar
 * highlights the sections in view (pages built from MDX do this through
 * their headings). Re-runs when the section list changes, e.g. on a language
 * switch, because the store then replaces its entries.
 */
function LandingSectionTracker({ sections }: { sections: Section[] }) {
  const registerHeading = useSectionStore((s) => s.registerHeading)
  useEffect(() => {
    for (const { id } of sections) {
      const element = document.getElementById(id)
      // The fixed header (3.5rem) covers the top of the viewport.
      if (element)
        registerHeading({ id, ref: { current: element }, offsetRem: 3.5 })
    }
  }, [sections, registerHeading])
  return null
}

// The benger marketing landing. Rendered by app/page.tsx on non-student-locked
// hosts (the host is decided server-side there). The client-side isStudentLockedHost
// branch below is a dev/safety fallback — on vertretbar.net the server component
// renders the Vertretbar landing directly, so this never runs there in prod.

export default function BengerLandingClient() {
  const { user, isLoading } = useAuth()
  const { t } = useI18n()
  const router = useRouter()
  const VertretbarLanding = useSlot('VertretbarLanding')
  const [isLocked, setIsLocked] = useState(false)
  const landingSections = useMemo(
    () => LANDING_SECTIONS.map(({ id, key }) => ({ id, title: t(key) })),
    [t],
  )

  // SSR has no auth context — always render the landing layout server-side and
  // wait for the client to mount before branching on isLoading / user. Without
  // this, hydration sees the server's "not authenticated" tree but the client
  // already knows the user is logged in (cookie present), causing a mismatch.
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional: mount flag for hydration-safe auth UI
    setMounted(true)
    setIsLocked(isStudentLockedHost())
  }, [])

  // Redirect authenticated users to dashboard
  // Only redirect when auth state is stable (not loading)
  useEffect(() => {
    if (mounted && !isLoading && user) {
      authRedirect.toDashboard(router)
    }
  }, [mounted, user, isLoading, router])

  // Prevent flash while redirecting
  if (mounted && !isLoading && user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400"></div>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('common.redirectingToDashboard')}
          </p>
        </div>
      </div>
    )
  }

  // Show loading state while auth is being checked (client-only)
  if (mounted && isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400"></div>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('common.loading')}
          </p>
        </div>
      </div>
    )
  }

  // Student-locked host (vertretbar.net), unauthenticated → the branded
  // Vertretbar landing instead of the benger one (dev fallback for the
  // server-side host branch in app/page.tsx). Authenticated users were already
  // sent to /student above via authRedirect.toDashboard.
  if (mounted && isLocked && !user && VertretbarLanding) {
    // eslint-disable-next-line react-hooks/static-components
    return <VertretbarLanding />
  }

  // The visitor version of the signed-in app shell: same header and
  // sidebar, the sidebar collapsed and holding only public entries.
  return (
    <Layout variant="public" allSections={{ '/': landingSections }}>
      <LandingSectionTracker sections={landingSections} />
      <HeroSection />
      <InformationSection />
      <NewsSection />
      <PeopleSection />
      <LicenseCitationSection />
    </Layout>
  )
}
