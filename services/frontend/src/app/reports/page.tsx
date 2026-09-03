/**
 * Reports Page - Published Project Reports
 *
 * Lists published project reports. There is no frontend gate: the API
 * filters per caller.
 * - Anonymous visitors see public reports (minimal logged-out layout)
 * - Signed-in users additionally see their organizations' published reports
 * - Superadmins see every published report
 *
 * Issue #770: Project Reports Publishing System
 */

'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Card } from '@/components/shared/Card'
import { ResponsiveContainer } from '@/components/shared/ResponsiveContainer'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import {
  listPublishedReports,
  type PublishedReportListItem,
} from '@/lib/api/reports'
import Link from 'next/link'
import { useCallback, useEffect, useState } from 'react'

function isPublicReport(report: PublishedReportListItem): boolean {
  return report.visibility === 'public' || report.is_public === true
}

export default function ReportsPage() {
  const { user, isLoading: authLoading } = useAuth()
  const { t } = useI18n()
  const [reports, setReports] = useState<PublishedReportListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<{ detail: string | null } | null>(null)

  // No `t` dependency on purpose: the translator is recreated on locale
  // changes and must not re-trigger the fetch (the message is translated at
  // render time from the stored detail).
  const loadReports = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listPublishedReports()
      setReports(Array.isArray(data) ? data : [])
    } catch (err: any) {
      console.error('Failed to load reports:', err)
      setError({ detail: typeof err?.message === 'string' ? err.message : null })
    } finally {
      setLoading(false)
    }
  }, [])

  // Wait for the session check so a signed-in user's org reports are included
  // in the first request instead of only the public ones.
  useEffect(() => {
    if (!authLoading) {
      loadReports()
    }
  }, [authLoading, loadReports])

  const showLoading = authLoading || loading

  return (
    <ResponsiveContainer size="xl" className="pb-10 pt-8">
      {user && (
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
      )}

      <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
        {t('reports.title')}
      </h1>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">
        {t(
          'reports.intro',
          'Veröffentlichte Evaluationsberichte: wie gut Sprachmodelle und Teilnehmende bei den Aufgaben eines Projekts abgeschnitten haben.'
        )}
      </p>
      {!authLoading && !user && (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-500">
          {t(
            'reports.anonymousHint',
            'Sie sehen öffentliche Berichte. Nach der Anmeldung erscheinen zusätzlich die Berichte Ihrer Organisationen.'
          )}{' '}
          <Link
            href="/login?next=%2Freports"
            className="font-medium text-emerald-700 hover:underline dark:text-emerald-400"
          >
            {t('reports.signIn', 'Anmelden')}
          </Link>
        </p>
      )}

      {showLoading ? (
        <Card
          className="mt-8 flex flex-col items-center justify-center px-6 py-16 text-center"
          data-testid="reports-loading"
        >
          <div className="mb-4 h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500"></div>
          <p className="m-0 text-zinc-600 dark:text-zinc-400">
            {t('reports.loadingReports', 'Berichte werden geladen...')}
          </p>
        </Card>
      ) : error ? (
        <Card
          className="mt-8 px-6 py-10 text-center"
          data-testid="reports-error"
          role="alert"
        >
          <h2 className="m-0 text-lg font-semibold text-zinc-900 dark:text-white">
            {t('reports.loadFailed', 'Berichte konnten nicht geladen werden')}
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-zinc-600 dark:text-zinc-400">
            {t(
              'reports.loadFailedHint',
              'Bitte versuchen Sie es erneut. Bleibt das Problem bestehen, wenden Sie sich an das BenGER-Team.'
            )}
          </p>
          {error.detail && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-500">
              {error.detail}
            </p>
          )}
          <button
            type="button"
            onClick={loadReports}
            className="mt-6 inline-flex items-center rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900"
          >
            {t('reports.reload', 'Erneut laden')}
          </button>
        </Card>
      ) : reports.length === 0 ? (
        <Card
          className="mt-8 border-dashed px-6 py-16 text-center"
          data-testid="reports-empty"
        >
          <h2 className="m-0 text-xl font-semibold text-zinc-900 dark:text-white">
            {t('reports.noReports', 'Keine veröffentlichten Berichte')}
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-zinc-600 dark:text-zinc-400">
            {user
              ? t('reports.noReportsDescription')
              : t(
                  'reports.noPublicReportsDescription',
                  'Derzeit ist kein Bericht öffentlich freigegeben.'
                )}
          </p>
        </Card>
      ) : (
        <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {reports.map((report) => {
            const isPublic = isPublicReport(report)
            return (
              <Link
                key={report.id}
                href={`/reports/${report.id}`}
                className="block rounded-lg border border-zinc-200 bg-white p-6 no-underline shadow transition-shadow hover:shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
                data-testid={`report-card-${report.id}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <h3 className="m-0 text-lg font-semibold text-zinc-900 dark:text-white">
                    {report.project_title}
                  </h3>
                  <span
                    data-testid="report-visibility"
                    className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      isPublic
                        ? 'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300'
                        : 'bg-zinc-100 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300'
                    }`}
                  >
                    {isPublic
                      ? t('reports.visibility.public', 'Öffentlich')
                      : t('reports.visibility.organizations', 'Organisation')}
                  </span>
                </div>

                {report.organizations.length > 0 && (
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
                )}

                <div className="mt-4 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
                  <div>
                    {report.task_count} {t('reports.tasks')}
                  </div>
                  {report.annotation_count > 0 && (
                    <div>
                      {report.annotation_count} {t('reports.annotations')}
                    </div>
                  )}
                  <div>
                    {report.model_count} {t('reports.models')}
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-500">
                    {t('reports.published')}{' '}
                    {new Date(report.published_at).toLocaleDateString()}
                  </div>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </ResponsiveContainer>
  )
}
