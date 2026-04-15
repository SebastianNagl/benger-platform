'use client'
// BenGER Frontend v3.0.1 - Force rebuild for latest changes

import { HeroSection } from '@/components/landing/HeroSection'
import { InformationSection } from '@/components/landing/InformationSection'
import { LicenseCitationSection } from '@/components/landing/LicenseCitationSection'
import { LandingLayout } from '@/components/landing/LandingLayout'
import { NewsSection } from '@/components/landing/NewsSection'
import { PeopleSection } from '@/components/landing/PeopleSection'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { authRedirect } from '@/utils/authRedirect'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

// Metadata is exported from the root layout.tsx to avoid client component conflicts

export default function LandingPage() {
  const { user, isLoading } = useAuth()
  const { t } = useI18n()
  const router = useRouter()

  // Redirect authenticated users to dashboard
  // Only redirect when auth state is stable (not loading)
  useEffect(() => {
    if (!isLoading && user) {
      authRedirect.toDashboard(router)
    }
  }, [user, isLoading, router])

  // Prevent flash while redirecting
  if (!isLoading && user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="text-zinc-600 dark:text-zinc-400">
            {t('common.redirectingToDashboard')}
          </p>
        </div>
      </div>
    )
  }

  // Show loading state while auth is being checked
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-white dark:bg-zinc-900">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="text-zinc-600 dark:text-zinc-400">{t('common.loading')}</p>
        </div>
      </div>
    )
  }

  return (
    <LandingLayout>
      <HeroSection />
      <InformationSection />
      <NewsSection />
      <PeopleSection />
      <LicenseCitationSection />
    </LandingLayout>
  )
}
