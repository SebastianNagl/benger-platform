'use client'

import { Alert } from '@/components/shared/Alert'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { usePermissions } from '@/hooks/usePermissions'
import { projectsAPI } from '@/lib/api/projects'
import { intlTag } from '@/lib/i18n/locales'
import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect } from 'react'

// Compact a stat-tile count into a fixed-width form so 6+ digit values don't
// overflow the card. 100000 -> "100k", 1234567 -> "1234k".
const formatStatCount = (n: number): string =>
  n >= 100000 ? `${Math.floor(n / 1000)}k` : String(n)

// "Aktuelle Projekte" shows the newest projects by creation date.
const RECENT_PROJECTS_COUNT = 5

// GET /api/dashboard/stats answers in one of two views. Teachers and admins
// (ORG_ADMIN or CONTRIBUTOR somewhere, superadmins) get the overview of the
// projects of their organizations; everyone else gets their own counters only,
// so a student never sees the totals of other courses or other people's
// answers. The API decides the view and says which one it sent (`scope`).
type OverviewStats = {
  scope?: 'overview' // absent in answers of an API before the personal view
  project_count: number
  task_count: number
  annotation_count: number
  projects_with_generations: number
  projects_with_evaluations: number
}

type PersonalStats = {
  scope: 'personal'
  open_exams: number
  open_tasks: number
  submitted_answers: number
  released_results: number
}

type DashboardStats = OverviewStats | PersonalStats

type StatTileBase = {
  key: string
  label: string
  icon: string // the tile's SVG path
  // Shown only when the count is above zero (once loaded).
  hideWhenZero?: boolean
}

type StatTile<T> = StatTileBase & { key: Exclude<keyof T, 'scope'> & string }

const ICON_FOLDER =
  'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z'
const ICON_CLIPBOARD =
  'M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01'
const ICON_PENCIL =
  'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z'
const ICON_SPARKLES =
  'M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z'
const ICON_CHART =
  'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z'
const ICON_DOCUMENT =
  'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z'
const ICON_CHECK_BADGE =
  'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z'

// The overview tiles, in display order.
const OVERVIEW_TILES: StatTile<OverviewStats>[] = [
  {
    key: 'project_count',
    label: 'dashboard.stats.projects',
    icon: ICON_FOLDER,
  },
  { key: 'task_count', label: 'dashboard.stats.issues', icon: ICON_CLIPBOARD },
  {
    key: 'annotation_count',
    label: 'dashboard.stats.annotations',
    icon: ICON_PENCIL,
  },
  {
    key: 'projects_with_generations',
    label: 'dashboard.stats.generations',
    icon: ICON_SPARKLES,
  },
  {
    key: 'projects_with_evaluations',
    label: 'dashboard.stats.evaluations',
    icon: ICON_CHART,
  },
]

// The personal tiles, in display order. Released results appear once there
// is one.
const PERSONAL_TILES: StatTile<PersonalStats>[] = [
  {
    key: 'open_exams',
    label: 'dashboard.stats.openExams',
    icon: ICON_DOCUMENT,
  },
  {
    key: 'open_tasks',
    label: 'dashboard.stats.openTasks',
    icon: ICON_CLIPBOARD,
  },
  {
    key: 'submitted_answers',
    label: 'dashboard.stats.submittedAnswers',
    icon: ICON_PENCIL,
  },
  {
    key: 'released_results',
    label: 'dashboard.stats.releasedResults',
    icon: ICON_CHECK_BADGE,
    hideWhenZero: true,
  },
]

// Literal class names (Tailwind only emits classes it finds in the source).
const TILE_GRID_COLUMNS: Record<number, string> = {
  3: 'md:grid-cols-3',
  4: 'md:grid-cols-2 lg:grid-cols-4',
  5: 'md:grid-cols-3 lg:grid-cols-5',
}

export default function DashboardPage() {
  const { t, locale } = useI18n()
  const { user, organizations } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const errorParam = searchParams?.get('error') ?? null

  // All authenticated users can access projects (including private projects)
  const canAccessProjects = !!user
  // Import, generation and evaluation need ORG_ADMIN or CONTRIBUTOR in at
  // least one organization (the same gate that greys out those entries in
  // the sidebar), so annotators and students do not get actions that lead
  // to pages they cannot use. Creating a project stays open to everyone: a
  // private project is always allowed.
  const permissions = usePermissions()
  const canManageProjectData = permissions.canAccessProjectData()

  // Show error from redirect and clear the query param to prevent showing on refresh
  useEffect(() => {
    if (errorParam) {
      // Clear the error param from URL without full page reload
      router.replace('/dashboard', { scroll: false })
    }
  }, [errorParam, router])

  // React Query caches these for 60 s (the global default), so navigating
  // dashboard → projects → dashboard renders the second visit from memory.
  // The recent projects are still refetched in the background on every
  // visit, so a project created, deleted or archived elsewhere shows up.
  //
  // The recent projects are fetched straight from the API into this query,
  // not through the shared project store: the store's fetchProjects inherits
  // the projects page's search, archive and visibility filters, and the
  // projects page overwrites the store's list with its filtered result. The
  // list endpoint returns newest first, so page 1 holds the newest active
  // projects in the default visibility.
  const projectsQuery = useQuery({
    queryKey: ['dashboard', 'recentProjects', RECENT_PROJECTS_COUNT],
    queryFn: () =>
      projectsAPI.list(1, RECENT_PROJECTS_COUNT, undefined, false, false),
    refetchOnMount: 'always',
  })

  const statsQuery = useQuery({
    // Keyed by user: the view (and the numbers) belong to who is signed in.
    queryKey: ['dashboard', 'stats', user?.id],
    queryFn: async () => {
      const { default: api } = await import('@/lib/api')
      return api.getDashboardStats() as Promise<DashboardStats>
    },
    retry: false,
  })

  // No zero fallback: when the stats request fails the tiles say the
  // numbers are unavailable instead of showing 0 as if it were a real count.
  const dashboardStats: DashboardStats | undefined = statsQuery.data

  // The tiles follow the view the API sent. While loading, or when the
  // request failed, they follow the view the user's roles lead to (the rule
  // the API applies), so the placeholders match the numbers to come.
  const personalView = dashboardStats
    ? dashboardStats.scope === 'personal'
    : !canManageProjectData
  const statTiles: StatTileBase[] = personalView
    ? PERSONAL_TILES
    : OVERVIEW_TILES
  // A count missing from the answer reads as unavailable, never as 0.
  const statValue = (tile: StatTileBase): number | undefined => {
    const value = (dashboardStats as Record<string, unknown> | undefined)?.[
      tile.key
    ]
    return typeof value === 'number' ? value : undefined
  }
  const visibleTiles = statTiles.filter(
    (tile) => !(tile.hideWhenZero && statValue(tile) === 0),
  )

  // Sort a copy: the order must not depend on the response order, and the
  // query data must not be mutated in place.
  const recentProjects = [...(projectsQuery.data?.items ?? [])]
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    .slice(0, RECENT_PROJECTS_COUNT)

  return (
    <ResponsiveContainer size="xl" className="pt-8 pb-10">
      {/* Breadcrumb */}
      <div className="mb-4">
        <Breadcrumb
          items={[{ label: t('navigation.dashboard'), href: '/dashboard' }]}
        />
      </div>

      <div className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('dashboard.title')}
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          {t(
            personalView ? 'dashboard.subtitlePersonal' : 'dashboard.subtitle',
          )}
        </p>
      </div>

      {/* Organization assignment warning */}
      {organizations && organizations.length === 0 && (
        <Alert variant="warning" className="mb-8">
          <div>
            <h3 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
              {t('dashboard.organizationWarning.title')}
            </h3>
            <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300">
              {t('dashboard.organizationWarning.message')}
            </p>
          </div>
        </Alert>
      )}

      {/* Stats Cards */}
      {statsQuery.isError && (
        <Alert variant="error" className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-zinc-900 dark:text-zinc-100">
              {t('dashboard.statsUnavailable')}
            </p>
            <Button
              variant="outline"
              className="text-sm"
              onClick={() => statsQuery.refetch()}
              disabled={statsQuery.isFetching}
            >
              {t('dashboard.retry')}
            </Button>
          </div>
        </Alert>
      )}
      <div
        className={`mb-8 grid grid-cols-1 gap-6 sm:grid-cols-2 ${TILE_GRID_COLUMNS[visibleTiles.length]}`}
        aria-busy={statsQuery.isLoading}
        data-testid="dashboard-stats"
        data-scope={personalView ? 'personal' : 'overview'}
      >
        {statsQuery.isLoading && (
          <p className="sr-only" role="status">
            {t('common.loading')}
          </p>
        )}
        {visibleTiles.map((tile) => (
          <div
            key={tile.key}
            className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
          >
            <div className="p-4">
              <div className="flex items-center">
                <div className="shrink-0">
                  <div className="flex h-8 w-8 items-center justify-center rounded-md bg-emerald-600">
                    <svg
                      className="h-5 w-5 text-white"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d={tile.icon}
                      />
                    </svg>
                  </div>
                </div>
                <div className="ml-3 w-0 flex-1">
                  <dl>
                    <dt
                      className="truncate text-sm font-medium text-zinc-500 dark:text-zinc-400"
                      title={t(tile.label)}
                    >
                      {t(tile.label)}
                    </dt>
                    {statsQuery.isLoading ? (
                      <dd
                        className="mt-1 h-7 w-12 animate-pulse rounded bg-zinc-200 dark:bg-zinc-700"
                        data-testid={`stat-loading-${tile.key}`}
                        aria-hidden="true"
                      />
                    ) : statValue(tile) !== undefined ? (
                      <dd className="text-lg font-medium text-zinc-900 dark:text-white">
                        {formatStatCount(statValue(tile)!)}
                      </dd>
                    ) : (
                      <dd
                        className="text-lg font-medium text-red-700 dark:text-red-300"
                        data-testid={`stat-unavailable-${tile.key}`}
                        title={t('dashboard.stats.unavailable')}
                      >
                        <span aria-hidden="true">
                          {t('dashboard.stats.unavailableShort')}
                        </span>
                        <span className="sr-only">
                          {t('dashboard.stats.unavailable')}
                        </span>
                      </dd>
                    )}
                  </dl>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Only show project sections if user has organization or is superadmin */}
      {canAccessProjects && (
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          {/* Recent Projects */}
          <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <div className="px-6 py-6">
              <div className="mb-6 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('dashboard.recentProjects.title')}
                </h3>
                <Button href="/projects" variant="outline" className="text-sm">
                  {t('dashboard.recentProjects.viewAll')}
                </Button>
              </div>

              {projectsQuery.isLoading ? (
                <div className="flex flex-col items-center py-8" role="status">
                  <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-300 border-t-emerald-500 dark:border-zinc-600 dark:border-t-emerald-400"></div>
                  <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
                    {t('common.loading')}
                  </p>
                </div>
              ) : projectsQuery.isError ? (
                <div className="py-8 text-center" role="alert">
                  <p className="text-sm text-red-700 dark:text-red-300">
                    {t('dashboard.recentProjects.loadFailed')}
                  </p>
                  <Button
                    variant="outline"
                    className="mt-4 text-sm"
                    onClick={() => projectsQuery.refetch()}
                    disabled={projectsQuery.isFetching}
                  >
                    {t('dashboard.retry')}
                  </Button>
                </div>
              ) : recentProjects.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-zinc-500 dark:text-zinc-400">
                    {t('dashboard.recentProjects.noProjects')}
                  </p>
                  <Button href="/projects/create" className="mt-4">
                    {t('dashboard.recentProjects.createFirst')}
                  </Button>
                </div>
              ) : (
                <div className="space-y-4">
                  {recentProjects.map((project) => (
                    <Link
                      key={project.id}
                      href={`/projects/${project.id}`}
                      className="group flex cursor-pointer items-center justify-between rounded-lg bg-zinc-50 p-4 transition-colors hover:bg-zinc-100 dark:bg-white/5 dark:hover:bg-white/10"
                    >
                      <div className="min-w-0 flex-1">
                        <h4 className="truncate text-sm font-medium text-zinc-900 dark:text-white">
                          {project.title}
                        </h4>
                        <p className="truncate text-sm text-zinc-500 dark:text-zinc-400">
                          {project.description ||
                            t('dashboard.recentProjects.noDescription')}
                        </p>
                        <div className="mt-2 flex items-center gap-x-2 text-xs text-zinc-500 dark:text-zinc-400">
                          <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 ring-1 ring-emerald-600/20 ring-inset dark:bg-emerald-400/10 dark:text-emerald-400 dark:ring-emerald-400/30">
                            {project.task_count || 0}{' '}
                            {t(
                              project.task_count === 1
                                ? 'dashboard.recentProjects.taskOne'
                                : 'dashboard.recentProjects.tasks',
                            )}
                          </span>
                          <span>
                            {new Date(project.created_at).toLocaleDateString(
                              intlTag(locale),
                            )}
                          </span>
                        </div>
                      </div>
                      <Button
                        as="span"
                        variant="outline"
                        className="ml-4 text-xs"
                      >
                        {t('dashboard.recentProjects.openProject')}
                      </Button>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Quick Actions */}
          <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
            <div className="px-6 py-6">
              <h3 className="mb-6 text-lg font-semibold text-zinc-900 dark:text-white">
                {t('dashboard.quickActions')}
              </h3>

              <div className="space-y-4">
                <div className="rounded-lg bg-zinc-50 p-4 dark:bg-white/5">
                  <h4 className="mb-2 text-sm font-medium text-zinc-900 dark:text-white">
                    {t('dashboard.createNewProject.title')}
                  </h4>
                  <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
                    {t('dashboard.createNewProject.description')}
                  </p>
                  <Button href="/projects/create" className="w-full">
                    {t('dashboard.createNewProject.button')}
                  </Button>
                </div>

                {canManageProjectData && (
                  <>
                    <div className="rounded-lg bg-zinc-50 p-4 dark:bg-white/5">
                      <h4 className="mb-2 text-sm font-medium text-zinc-900 dark:text-white">
                        {t('dashboard.importData.title')}
                      </h4>
                      <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
                        {t('dashboard.importData.description')}
                      </p>
                      <Button href="/data" className="w-full">
                        {t('dashboard.importData.button')}
                      </Button>
                    </div>

                    <div className="rounded-lg bg-zinc-50 p-4 dark:bg-white/5">
                      <h4 className="mb-2 text-sm font-medium text-zinc-900 dark:text-white">
                        {t('dashboard.generation.title')}
                      </h4>
                      <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
                        {t('dashboard.generation.description')}
                      </p>
                      <Button href="/generations" className="w-full">
                        {t('dashboard.generation.button')}
                      </Button>
                    </div>

                    <div className="rounded-lg bg-zinc-50 p-4 dark:bg-white/5">
                      <h4 className="mb-2 text-sm font-medium text-zinc-900 dark:text-white">
                        {t('dashboard.evaluation.title')}
                      </h4>
                      <p className="mb-3 text-sm text-zinc-600 dark:text-zinc-400">
                        {t('dashboard.evaluation.description')}
                      </p>
                      <Button href="/evaluations" className="w-full">
                        {t('dashboard.evaluation.button')}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </ResponsiveContainer>
  )
}
