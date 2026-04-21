'use client'

import { AuthGuard } from '@/components/auth/AuthGuard'
import { LLMLeaderboardTable } from '@/components/leaderboards/LLMLeaderboardTable'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useI18n } from '@/contexts/I18nContext'
import { useSlot } from '@/lib/extensions/slots'
import {
  CpuChipIcon,
  UserGroupIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react'
import { Suspense } from 'react'

function LeaderboardsContent() {
  const { t } = useI18n()

  const AnnotatorLeaderboardTab = useSlot('AnnotatorLeaderboardTab')
  const CoCreationLeaderboardTab = useSlot('CoCreationLeaderboardTab')

  const hasTabs = AnnotatorLeaderboardTab || CoCreationLeaderboardTab

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

        {hasTabs ? (
          <TabGroup>
            <div className="border-b border-zinc-200 dark:border-zinc-700">
              <TabList className="-mb-px flex space-x-8">
                <Tab
                  className={({ selected }) =>
                    `flex items-center gap-2 border-b-2 py-3 text-sm font-medium transition ${
                      selected
                        ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                        : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                    }`
                  }
                >
                  <CpuChipIcon className="h-5 w-5" />
                  {t('leaderboards.llms') || 'LLMs'}
                </Tab>
                {AnnotatorLeaderboardTab && (
                  <Tab
                    className={({ selected }) =>
                      `flex items-center gap-2 border-b-2 py-3 text-sm font-medium transition ${
                        selected
                          ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                          : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                      }`
                    }
                  >
                    <UserGroupIcon className="h-5 w-5" />
                    {t('leaderboards.humanAnnotators') || 'Human Annotators'}
                  </Tab>
                )}
                {CoCreationLeaderboardTab && (
                  <Tab
                    className={({ selected }) =>
                      `flex items-center gap-2 border-b-2 py-3 text-sm font-medium transition ${
                        selected
                          ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                          : 'border-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'
                      }`
                    }
                  >
                    <SparklesIcon className="h-5 w-5" />
                    {t('leaderboards.coCreation') || 'Co-Creation'}
                  </Tab>
                )}
              </TabList>
            </div>
            <TabPanels className="mt-6">
              <TabPanel>
                <LLMLeaderboardTable />
              </TabPanel>
              {AnnotatorLeaderboardTab && (
                <TabPanel>
                  <AnnotatorLeaderboardTab />
                </TabPanel>
              )}
              {CoCreationLeaderboardTab && (
                <TabPanel>
                  <CoCreationLeaderboardTab />
                </TabPanel>
              )}
            </TabPanels>
          </TabGroup>
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
