'use client'

import { AuthGuard } from '@/components/auth/AuthGuard'
import { LLMLeaderboardTable } from '@/components/leaderboards/LLMLeaderboardTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { Suspense } from 'react'

function LeaderboardsContent() {
  const { t } = useI18n()

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      <div className="mb-4">
        <Breadcrumb
          items={[
            {
              label: t('navigation.dashboard') || 'Dashboard',
              href: '/dashboard',
            },
            {
              label: t('navigation.leaderboards') || 'Leaderboards',
              href: '/leaderboards',
            },
          ]}
        />
      </div>

      <div>
        <h1 className="mb-6 text-3xl font-bold text-zinc-900 dark:text-white">
          {t('leaderboards.title') || 'Leaderboards'}
        </h1>

        <LLMLeaderboardTable />
      </div>
    </ResponsiveContainer>
  )
}

function LoadingSkeleton() {
  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      <div className="mb-4">
        <div className="h-6 w-48 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700" />
      </div>
      <div className="h-10 w-64 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700 mb-6" />
      <div className="h-12 w-full animate-pulse rounded bg-zinc-200 dark:bg-zinc-700" />
    </ResponsiveContainer>
  )
}

export default function LeaderboardsPage() {
  return (
    <AuthGuard>
      <Suspense fallback={<LoadingSkeleton />}>
        <LeaderboardsContent />
      </Suspense>
    </AuthGuard>
  )
}
