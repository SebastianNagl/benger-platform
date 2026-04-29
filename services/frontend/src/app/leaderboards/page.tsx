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
    AnnotatorLeaderboardTab ? 'human' : 'llm'
  )

  const tabClass = (tab: LeaderboardTab) =>
    `border-b-2 py-3 text-sm font-medium transition ${
      activeTab === tab
        ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
        : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
    }`

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

        <div className="mb-6 border-b border-zinc-200 dark:border-zinc-700">
          <nav className="-mb-px flex space-x-8">
            {AnnotatorLeaderboardTab && (
              <button onClick={() => setActiveTab('human')} className={tabClass('human')}>
                {t('leaderboards.humanAnnotators') || 'Human Annotators'}
              </button>
            )}
            {CoCreationLeaderboardTab && (
              <button onClick={() => setActiveTab('co-creation')} className={tabClass('co-creation')}>
                {t('leaderboards.coCreation') || 'Co-Creation'}
              </button>
            )}
            <button onClick={() => setActiveTab('llm')} className={tabClass('llm')}>
              {t('leaderboards.llms') || 'LLMs'}
            </button>
          </nav>
        </div>

        {activeTab === 'human' && AnnotatorLeaderboardTab ? (
          <AnnotatorLeaderboardTab />
        ) : activeTab === 'co-creation' && CoCreationLeaderboardTab ? (
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
