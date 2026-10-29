'use client'

import { AuthGuard } from '@/components/auth/AuthGuard'
import { LLMLeaderboardTable } from '@/components/leaderboards/LLMLeaderboardTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import { Suspense, useState } from 'react'

type LeaderboardTab = 'human' | 'co-creation' | 'llm'

function LeaderboardsContent() {
  const { t } = useI18n()

  const AnnotatorLeaderboardTab = useSlot('AnnotatorLeaderboardTab')
  const CoCreationLeaderboardTab = useSlot('CoCreationLeaderboardTab')

  // Default to 'human' to match the old monolith. Falls back to 'llm' in
  // community edition where the human/co-creation slots aren't registered.
  const [activeTab, setActiveTab] = useState<LeaderboardTab>(
    AnnotatorLeaderboardTab ? 'human' : 'llm',
  )

  const tabClass = (tab: LeaderboardTab) =>
    `rounded-full px-3 h-7 text-sm font-medium whitespace-nowrap transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 ${
      activeTab === tab
        ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
        : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
    }`

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-10">
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
        <h1 className="mb-6 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('leaderboards.title') || 'Leaderboards'}
        </h1>

        <div className="mb-6 flex items-center justify-between gap-4">
          <nav className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
            {AnnotatorLeaderboardTab && (
              <button
                onClick={() => setActiveTab('human')}
                className={tabClass('human')}
              >
                {t('leaderboards.humanAnnotators') || 'Human Annotators'}
              </button>
            )}
            {CoCreationLeaderboardTab && (
              <button
                onClick={() => setActiveTab('co-creation')}
                className={tabClass('co-creation')}
              >
                {t('leaderboards.coCreation') || 'Co-Creation'}
              </button>
            )}
            <button
              onClick={() => setActiveTab('llm')}
              className={tabClass('llm')}
            >
              {t('leaderboards.llms') || 'LLMs'}
            </button>
          </nav>
          {/* Schedule hint: leaderboards refresh twice daily on the worker's
              beat (10:00 + 22:00 UTC = 12:00 + 00:00 CEST). Static copy
              keeps the contract visible without forcing the page to query
              `computed_at` on every tab. */}
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {t('leaderboards.refreshHint') ||
              'Updated daily at 00:00 and 12:00 (CEST)'}
          </span>
        </div>

        {activeTab === 'human' && AnnotatorLeaderboardTab ? (
          // eslint-disable-next-line react-hooks/static-components
          <AnnotatorLeaderboardTab />
        ) : activeTab === 'co-creation' && CoCreationLeaderboardTab ? (
          // eslint-disable-next-line react-hooks/static-components
          <CoCreationLeaderboardTab />
        ) : (
          <LLMLeaderboardTable />
        )}
      </div>
    </ResponsiveContainer>
  )
}

function LoadingSkeleton() {
  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-10">
      <div className="mb-4">
        <div className="h-6 w-48 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700" />
      </div>
      <div className="mb-6 h-10 w-64 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700" />
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
