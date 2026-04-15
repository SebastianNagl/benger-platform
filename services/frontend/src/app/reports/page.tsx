/**
 * Reports Page - Published Project Reports
 *
 * Displays published project reports with evaluation results.
 * - Superadmins see all published reports
 * - Org members see reports from their organizations only
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { canAccessReports } from '@/utils/permissions'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'

interface Organization {
  id: string
  name: string
}

interface PublishedReport {
  id: string
  project_id: string
  project_title: string
  published_at: string
  task_count: number
  annotation_count: number
  model_count: number
  organizations: Organization[]
}

export default function ReportsPage() {
  const router = useRouter()
  const { user, isLoading: authLoading } = useAuth()
  const { t } = useI18n()
  const [reports, setReports] = useState<PublishedReport[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Check permissions - only superadmins and org_admins can access
  useEffect(() => {
    if (!authLoading && !canAccessReports(user)) {
      router.replace('/projects?error=no-permission')
    }
  }, [user, authLoading, router])

  useEffect(() => {
    if (!authLoading && canAccessReports(user)) {
      loadReports()
    }
  }, [authLoading, user])

  const loadReports = async () => {
    try {
      setLoading(true)
      setError(null)

      const response = await fetch('/api/reports', {
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error(`Failed to load reports: ${response.statusText}`)
      }

      const data = await response.json()
      setReports(data)
    } catch (err: any) {
      console.error('Failed to load reports:', err)
      setError(err.message || t('reports.loadFailed'))
    } finally {
      setLoading(false)
    }
  }

  // Show loading state while checking permissions
  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg">{t('common.loading')}</div>
      </div>
    )
  }

  // Show permission denied if user cannot access
  if (!canAccessReports(user)) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
            <svg
              className="h-6 w-6 text-red-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
              />
            </svg>
          </div>
          <h3 className="mt-2 text-sm font-medium text-gray-900">
            {t('common.accessDenied')}
          </h3>
          <p className="mt-1 text-sm text-gray-500">
            {t('reports.accessDeniedMessage')}
          </p>
          <div className="mt-6">
            <button
              type="button"
              onClick={() => router.push('/projects')}
              className="inline-flex items-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500"
            >
              {t('common.backToProjects')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-lg">{t('reports.loadingReports')}</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="rounded-lg border border-red-300 bg-red-50 p-6">
          <div className="text-red-800">{error}</div>
          <button
            onClick={loadReports}
            className="mt-4 rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
          >
            {t('common.retry')}
          </button>
        </div>
      </div>
    )
  }

  if (reports.length === 0) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900">
            {t('reports.noReports')}
          </h2>
          <p className="mt-2 text-gray-600">
            {t('reports.noReportsDescription')}
          </p>
        </div>
      </div>
    )
  }

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
              label: t('navigation.reports') || 'Reports',
              href: '/reports',
            },
          ]}
        />
      </div>

      <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">{t('reports.title')}</h1>
      <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {reports.map((report) => (
          <div
            key={report.id}
            onClick={() => router.push(`/reports/${report.id}`)}
            className="cursor-pointer rounded-lg border border-zinc-200 bg-white p-6 shadow transition-shadow hover:shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
          >
            <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
              {report.project_title}
            </h3>

            <div className="mt-4 flex flex-wrap gap-2">
              {report.organizations.map((org) => (
                <span
                  key={org.id}
                  className="inline-block rounded bg-zinc-100 px-2 py-1 text-xs text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300"
                >
                  {org.name}
                </span>
              ))}
            </div>

            <div className="mt-4 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
              <div>{report.task_count} {t('reports.tasks')}</div>
              {report.annotation_count > 0 && (
                <div>{report.annotation_count} {t('reports.annotations')}</div>
              )}
              <div>{report.model_count} {t('reports.models')}</div>
              <div className="text-xs text-zinc-500 dark:text-zinc-500">
                {t('reports.published')} {new Date(report.published_at).toLocaleDateString()}
              </div>
            </div>
          </div>
        ))}
      </div>
    </ResponsiveContainer>
  )
}
