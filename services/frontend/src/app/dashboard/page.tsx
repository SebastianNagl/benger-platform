'use client'

import { Alert } from '@/components/shared/Alert'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjectStore } from '@/stores/projectStore'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

export default function DashboardPage() {
  const { t } = useI18n()
  const { projects, fetchProjects, loading } = useProjectStore()
  const { user, organizations } = useAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const [error, setError] = useState<string | null>(null)
  const errorParam = searchParams?.get('error') ?? null
  const [dashboardStats, setDashboardStats] = useState({
    project_count: 0,
    task_count: 0,
    annotation_count: 0,
    projects_with_generations: 0,
    projects_with_evaluations: 0,
  })
  const [statsLoading, setStatsLoading] = useState(true)

  // All authenticated users can access projects (including private projects)
  const canAccessProjects = !!user

  // Show error from redirect and clear the query param to prevent showing on refresh
  useEffect(() => {
    if (errorParam) {
      // Clear the error param from URL without full page reload
      router.replace('/dashboard', { scroll: false })
    }
  }, [errorParam, router])

  useEffect(() => {
    const loadData = async () => {
      try {
        // Load projects for recent projects display
        await fetchProjects(1, 100)

        // Load dashboard statistics from API
        const { default: api } = await import('@/lib/api')
        const stats = await api.getDashboardStats()
        setDashboardStats(stats)
        setStatsLoading(false)
      } catch (err) {
        setError(
          err instanceof Error ? err.message : t('dashboard.loadFailed')
        )
        setStatsLoading(false)
      }
    }
    loadData()
  }, [fetchProjects])

  const recentProjects =
    projects
      ?.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      .slice(0, 5) || []

  if (loading || statsLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="mt-4 text-zinc-600 dark:text-zinc-400">
            {t('common.loading')}
          </p>
        </div>
      </div>
    )
  }

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
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
        <p className="mt-2 text-lg text-zinc-600 dark:text-zinc-400">
          {t('dashboard.subtitle')}
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


      {error && (
        <div className="mb-8 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-950">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-200">
                {t('common.error')}
              </h3>
              <div className="mt-2 text-sm text-red-700 dark:text-red-300">
                {error}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stats Cards */}
      <div className="mb-8 grid grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5">
        {/* 1. Projects */}
        <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
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
                      d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                    />
                  </svg>
                </div>
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('dashboard.stats.projects')}
                  </dt>
                  <dd className="text-lg font-medium text-zinc-900 dark:text-white">
                    {dashboardStats.project_count}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        {/* 2. Issues (Tasks) */}
        <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
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
                      d="M9 5H7a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
                    />
                  </svg>
                </div>
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('dashboard.stats.issues')}
                  </dt>
                  <dd className="text-lg font-medium text-zinc-900 dark:text-white">
                    {dashboardStats.task_count}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        {/* 3. Annotations */}
        <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
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
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                    />
                  </svg>
                </div>
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('dashboard.stats.annotations')}
                  </dt>
                  <dd className="text-lg font-medium text-zinc-900 dark:text-white">
                    {dashboardStats.annotation_count}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        {/* 4. Generations */}
        <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
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
                      d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
                    />
                  </svg>
                </div>
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('dashboard.stats.generations')}
                  </dt>
                  <dd className="text-lg font-medium text-zinc-900 dark:text-white">
                    {dashboardStats.projects_with_generations}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>

        {/* 5. Evaluations */}
        <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
          <div className="p-6">
            <div className="flex items-center">
              <div className="flex-shrink-0">
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
                      d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                    />
                  </svg>
                </div>
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-zinc-500 dark:text-zinc-400">
                    {t('dashboard.stats.evaluations')}
                  </dt>
                  <dd className="text-lg font-medium text-zinc-900 dark:text-white">
                    {dashboardStats.projects_with_evaluations}
                  </dd>
                </dl>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Only show project sections if user has organization or is superadmin */}
      {canAccessProjects && (
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          {/* Recent Projects */}
          <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
            <div className="px-6 py-6">
              <div className="mb-6 flex items-center justify-between">
                <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
                  {t('dashboard.recentProjects.title')}
                </h3>
                <Button href="/projects" variant="outline" className="text-sm">
                  {t('dashboard.recentProjects.viewAll')}
                </Button>
              </div>

              {recentProjects.length === 0 ? (
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
                          <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-400 dark:ring-emerald-400/30">
                            {project.task_count || 0}{' '}
                            {t('dashboard.recentProjects.tasks')}
                          </span>
                          <span>
                            {new Date(project.created_at).toLocaleDateString(
                              'de-DE'
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
          <div className="rounded-lg bg-white shadow-sm ring-1 ring-zinc-900/5 dark:bg-zinc-900 dark:ring-white/10">
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
              </div>
            </div>
          </div>
        </div>
      )}
    </ResponsiveContainer>
  )
}
