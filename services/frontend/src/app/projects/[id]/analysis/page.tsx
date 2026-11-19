'use client'

/**
 * Analysis runs of a project: the runs, newest first, and (for editors) a
 * form that starts a run from a spec. `?from=<runId>` prefills the form with
 * that run's spec, so a run can be repeated or varied.
 */

import { NewAnalysisRunForm } from '@/components/analysis/NewAnalysisRunForm'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { RunStatusBadge } from '@/components/shared/RunStatusBadge'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { MISSING, shortHash } from '@/lib/analysis/results'
import {
  analysisAPI,
  isRunActive,
  statusOf,
  type AnalysisRunSummary,
} from '@/lib/api/analysis'
import { projectsAPI } from '@/lib/api/projects'
import { intlTag } from '@/lib/i18n/locales'
import type { Project } from '@/types/labelStudio'
import { PlusIcon } from '@heroicons/react/24/outline'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

const LIST_POLL_MS = 4000

function formatDate(value: string | null | undefined, locale: string) {
  if (!value) return MISSING
  try {
    return new Date(value).toLocaleString(intlTag(locale), {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return value
  }
}

export default function ProjectAnalysisPage() {
  const { t, locale } = useI18n()
  const { user } = useAuth()
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const projectId = typeof params?.id === 'string' ? params.id : ''
  const fromRunId = searchParams?.get('from') || null

  const [project, setProject] = useState<Project | null>(null)
  const [runs, setRuns] = useState<AnalysisRunSummary[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [designKeys, setDesignKeys] = useState<string[]>([])
  const [showForm, setShowForm] = useState(Boolean(fromRunId))
  const [prefill, setPrefill] = useState<{ spec: string; name: string } | null>(
    null,
  )
  const [prefillError, setPrefillError] = useState<string | null>(null)

  const loadRuns = useCallback(async () => {
    try {
      const page = await analysisAPI.listRuns(projectId)
      setRuns(page.items)
      setTotal(page.total)
      setError(null)
    } catch (err) {
      setError(
        statusOf(err) === 404 || statusOf(err) === 403
          ? 'forbidden'
          : (err as Error)?.message || 'failed',
      )
    }
  }, [projectId])

  useEffect(() => {
    if (!projectId) return
    void loadRuns()
    projectsAPI
      .get(projectId)
      .then(setProject)
      .catch(() => undefined)
    analysisAPI
      .listDesignKeys(projectId)
      .then(setDesignKeys)
      .catch(() => undefined)
  }, [projectId, loadRuns])

  // Refresh while a run in the list is still pending or running.
  const anyActive = runs?.some((r) => isRunActive(r.status)) ?? false
  useEffect(() => {
    if (!anyActive) return
    const timer = window.setTimeout(() => void loadRuns(), LIST_POLL_MS)
    return () => window.clearTimeout(timer)
  }, [anyActive, runs, loadRuns])

  useEffect(() => {
    if (!fromRunId) return
    let cancelled = false
    analysisAPI
      .getRun(fromRunId)
      .then((run) => {
        if (cancelled) return
        if (run.project_id !== projectId) {
          setPrefillError(t('analysis.list.prefillFailed'))
          return
        }
        setPrefill({
          spec: JSON.stringify(run.spec, null, 2),
          name: run.name,
        })
      })
      .catch(() => {
        if (!cancelled) setPrefillError(t('analysis.list.prefillFailed'))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromRunId, projectId])

  // The backend's own edit decision, the rule the start route enforces.
  const canStart = !!user?.is_superadmin || project?.can_edit === true
  const waitingForPrefill = Boolean(fromRunId) && !prefill && !prefillError

  const th =
    'px-4 py-3 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'

  return (
    <div className="container mx-auto space-y-6 px-4 py-8">
      <Breadcrumb
        items={[
          { label: t('navigation.projects'), href: '/projects' },
          {
            label: project?.title || t('analysis.project'),
            href: `/projects/${projectId}`,
          },
          { label: t('analysis.title') },
        ]}
      />

      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('analysis.title')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('analysis.list.subtitle')}
          </p>
        </div>
        {canStart && !showForm && (
          <Button
            variant="primary"
            onClick={() => setShowForm(true)}
            data-testid="analysis-new-run"
          >
            <PlusIcon className="mr-2 h-4 w-4" />
            {t('analysis.list.newRun')}
          </Button>
        )}
      </div>

      {canStart && showForm && (
        <section className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-zinc-900 dark:text-white">
                {t('analysis.list.newRun')}
              </h2>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('analysis.list.newRunDescription')}
              </p>
            </div>
            <Button variant="text" onClick={() => setShowForm(false)}>
              {t('common.cancel')}
            </Button>
          </div>
          {prefillError && (
            <p
              className="mb-3 text-sm text-red-600 dark:text-red-400"
              role="alert"
            >
              {prefillError}
            </p>
          )}
          {waitingForPrefill ? (
            <p className="text-sm text-zinc-500" role="status">
              {t('analysis.run.loading')}
            </p>
          ) : (
            <NewAnalysisRunForm
              key={prefill ? 'prefilled' : 'blank'}
              projectId={projectId}
              initialSpec={prefill?.spec}
              initialName={prefill?.name}
              designKeys={designKeys}
              onStarted={(run) =>
                router.push(`/projects/${projectId}/analysis/${run.id}`)
              }
            />
          )}
        </section>
      )}

      {error && (
        <div
          className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          role="alert"
        >
          {error === 'forbidden'
            ? t('analysis.list.forbidden')
            : error === 'failed'
              ? t('analysis.list.loadFailed')
              : error}
        </div>
      )}

      {!error && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table
            className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800"
            data-testid="analysis-runs-table"
          >
            <thead className="bg-zinc-50 dark:bg-zinc-900/40">
              <tr>
                <th className={th}>{t('analysis.list.col.name')}</th>
                <th className={th}>{t('analysis.list.col.status')}</th>
                <th className={th}>{t('analysis.list.col.created')}</th>
                <th className={`${th} text-right`}>
                  {t('analysis.list.col.rows')}
                </th>
                <th className={`${th} text-right`}>
                  {t('analysis.list.col.estimates')}
                </th>
                <th className={th}>{t('analysis.list.col.specHash')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
              {runs === null && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-6 text-center text-xs text-zinc-500"
                  >
                    {t('analysis.run.loading')}
                  </td>
                </tr>
              )}
              {runs?.length === 0 && (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-sm text-zinc-500"
                  >
                    {t('analysis.list.empty')}
                  </td>
                </tr>
              )}
              {runs?.map((run) => (
                <tr
                  key={run.id}
                  className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                  onClick={() =>
                    router.push(`/projects/${projectId}/analysis/${run.id}`)
                  }
                  data-testid="analysis-run-row"
                >
                  <td className="px-4 py-3">
                    <a
                      href={`/projects/${projectId}/analysis/${run.id}`}
                      className="font-medium text-zinc-900 hover:underline dark:text-white"
                      onClick={(e) => {
                        e.preventDefault()
                        router.push(`/projects/${projectId}/analysis/${run.id}`)
                      }}
                    >
                      {run.name}
                    </a>
                    {run.error_message && (
                      <div className="mt-0.5 max-w-md truncate text-xs text-red-600 dark:text-red-400">
                        {run.error_message}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <RunStatusBadge status={run.status} />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-zinc-700 dark:text-zinc-300">
                    {formatDate(run.created_at, locale)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs">
                    {run.frame_rows ?? MISSING}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs">
                    {run.estimates_count ?? MISSING}
                  </td>
                  <td
                    className="px-4 py-3 font-mono text-xs text-zinc-600 dark:text-zinc-400"
                    title={run.spec_hash}
                  >
                    {shortHash(run.spec_hash)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {runs && total > runs.length && (
            <p className="border-t border-zinc-200 px-4 py-2 text-xs text-zinc-500 dark:border-zinc-800">
              {t('analysis.list.more', { shown: runs.length, total })}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
