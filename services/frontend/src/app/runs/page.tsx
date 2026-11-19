'use client'

import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { RunStatusBadge } from '@/components/shared/RunStatusBadge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { projectsAPI } from '@/lib/api/projects'
import { intlTag } from '@/lib/i18n/locales'
import { translate } from '@/lib/utils/translate'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

/**
 * Single-run inventory page (multi-run feature).
 *
 * Shows individual generation, evaluation and analysis runs across the
 * platform — the canonical "find a run" view. Clicking a row deep-links into
 * the detail page for that run. The aggregate dashboards at /evaluations and /generations
 * keep their existing role (cross-run scoresheets per project / per model).
 *
 * Notification routing in NotificationDropdown also points here.
 */

type RunType = 'generation' | 'evaluation' | 'analysis'

const RUN_TYPES: RunType[] = ['evaluation', 'generation', 'analysis']

const TAB_LABELS: Record<RunType, string> = {
  evaluation: 'runs.tabs.evaluation',
  generation: 'runs.tabs.generation',
  analysis: 'runs.tabs.analysis',
}

// Columns of each tab (started, project, status, the tab's own, duration),
// for the full-width loading and empty rows.
const COLUMN_COUNT: Record<RunType, number> = {
  generation: 7,
  evaluation: 8,
  analysis: 8,
}

const STATUSES = ['pending', 'running', 'completed', 'failed']

const asRunType = (value: string | null | undefined): RunType =>
  RUN_TYPES.includes(value as RunType) ? (value as RunType) : 'evaluation'

interface RunSummary {
  id: string
  type: RunType
  project_id?: string | null
  project_title?: string | null
  status?: string | null
  created_at?: string | null
  completed_at?: string | null
  created_by?: string | null
  error_message?: string | null
  model_id?: string | null
  structure_key?: string | null
  runs_requested?: number | null
  runs_completed?: number | null
  runs_failed?: number | null
  task_id?: string | null
  // Evaluation runs: every model the run graded. model_id is 'unknown' for
  // a run over several models (or over submitted answers only).
  evaluated_model_ids?: string[] | null
  judge_models?: string[] | null
  samples_evaluated?: number | null
  metrics?: string[] | null
  // Analysis runs.
  name?: string | null
  frame_rows?: number | null
  estimates_count?: number | null
  spec_hash?: string | null
  engine_version?: string | null
}

/** The models an evaluation run graded, or '—' when it graded none. */
function evaluationModelsLabel(run: RunSummary): string {
  if (run.evaluated_model_ids) {
    return run.evaluated_model_ids.join(', ') || '—'
  }
  return run.model_id && run.model_id !== 'unknown' ? run.model_id : '—'
}

interface PaginatedRunsResponse {
  items: RunSummary[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 25

function formatDate(d: string | null | undefined, locale: string) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleString(intlTag(locale), {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return d
  }
}

function formatDuration(start?: string | null, end?: string | null) {
  if (!start || !end) return '—'
  try {
    const s = new Date(start).getTime()
    const e = new Date(end).getTime()
    const sec = Math.max(0, Math.round((e - s) / 1000))
    if (sec < 60) return `${sec}s`
    const m = Math.floor(sec / 60)
    const rest = sec % 60
    return `${m}m ${rest}s`
  } catch {
    return '—'
  }
}

// The Select treats an empty value as unset, so "all" gets a sentinel.
const ALL = '__all__'

export default function RunsPage() {
  const { t, locale } = useI18n()
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = asRunType(searchParams?.get('type'))
  const initialProject = searchParams?.get('project_id') || ''
  const initialStatus = searchParams?.get('status') || ''
  const [tab, setTab] = useState<RunType>(initialTab)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>(
    STATUSES.includes(initialStatus) ? initialStatus : '',
  )
  const [projectFilter, setProjectFilter] = useState<string>(initialProject)
  const [projects, setProjects] = useState<{ id: string; title: string }[]>([])
  const [data, setData] = useState<PaginatedRunsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Project list for the filter dropdown — loaded once. Cache in module
  // scope would skip the call across remounts, but the cost is small and
  // a stale list is more annoying than a 100ms refetch.
  useEffect(() => {
    let cancelled = false
    projectsAPI
      .list(1, 200)
      .then((resp) => {
        if (cancelled) return
        const items = (resp?.items || []) as Array<{
          id: string
          title: string
        }>
        setProjects(items.map((p) => ({ id: String(p.id), title: p.title })))
      })
      .catch(() => {
        // Filter is optional — silently fall back to "all projects" mode.
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Sync tab to URL so a notification deep-link to /runs?type=generation
  // lands on the right tab and refreshes scope a user can copy/share.
  const handleTabChange = useCallback(
    (next: RunType) => {
      setTab(next)
      setPage(1)
      const params = new URLSearchParams(searchParams?.toString() || '')
      params.set('type', next)
      router.replace(`/runs?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        type: tab,
        page: String(page),
        page_size: String(PAGE_SIZE),
      })
      if (statusFilter) params.set('status', statusFilter)
      if (projectFilter) params.set('project_id', projectFilter)
      const resp = await apiClient.get(`/runs?${params.toString()}`)
      setData(resp as PaginatedRunsResponse)
    } catch (err: any) {
      // translate() (not t) keeps the fetch callback's deps stable.
      setError(err?.message || translate('runs.loadFailed'))
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [tab, page, statusFilter, projectFilter])

  // Sync project filter to URL so a deep-link to /runs?project_id=... works
  // and the back button preserves the filter state.
  const handleProjectChange = useCallback(
    (next: string) => {
      setProjectFilter(next)
      setPage(1)
      const params = new URLSearchParams(searchParams?.toString() || '')
      if (next) params.set('project_id', next)
      else params.delete('project_id')
      router.replace(`/runs?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  // Sync the status filter to the URL like the project filter.
  const handleStatusChange = useCallback(
    (next: string) => {
      setStatusFilter(next)
      setPage(1)
      const params = new URLSearchParams(searchParams?.toString() || '')
      if (next) params.set('status', next)
      else params.delete('status')
      router.replace(`/runs?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  useEffect(() => {
    load()
  }, [load])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const navigateToRun = (run: RunSummary) => {
    if (run.type === 'evaluation') {
      router.push(`/evaluations/${run.id}`)
    } else if (run.type === 'analysis') {
      router.push(`/projects/${run.project_id}/analysis/${run.id}`)
    } else {
      router.push(`/generations/${run.id}`)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('runs.title') },
          ]}
        />
      </div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
            {t('runs.title')}
          </h1>
          <p className="mt-2 text-zinc-600 dark:text-zinc-400">
            {t('runs.subtitle')}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-4">
        <nav className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800">
          {RUN_TYPES.map((tname) => (
            <button
              key={tname}
              onClick={() => handleTabChange(tname)}
              aria-pressed={tab === tname}
              data-testid={`runs-tab-${tname}`}
              className={`h-7 rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors ${
                tab === tname
                  ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                  : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
              } focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900`}
            >
              {t(TAB_LABELS[tname])}
            </button>
          ))}
        </nav>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-xs text-zinc-500">
          {t('runs.filterProject')}
        </label>
        <Select
          searchable
          value={projectFilter || ALL}
          onValueChange={(v) => handleProjectChange(v === ALL ? '' : v)}
        >
          <SelectTrigger
            className="w-56"
            aria-label={t('runs.filterProject')}
            data-testid="runs-project-filter"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem pinned value={ALL}>
              {t('runs.allProjects')}
            </SelectItem>
            {projects.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="text-xs text-zinc-500">
          {t('runs.filterStatus')}
        </label>
        <Select
          value={statusFilter || ALL}
          onValueChange={(v) => handleStatusChange(v === ALL ? '' : v)}
        >
          <SelectTrigger
            className="w-40"
            aria-label={t('runs.filterStatus')}
            data-testid="runs-status-filter"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('runs.allStatuses')}</SelectItem>
            {STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {t(`evaluations.detail.statusLabels.${s}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-xs text-zinc-500">
          {data ? t('runs.totalCount', { count: data.total }) : ''}
        </span>
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
          <thead className="bg-zinc-50 text-left text-xs tracking-wide text-zinc-500 uppercase dark:bg-zinc-900/40 dark:text-zinc-400">
            <tr>
              <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                {t('runs.col.started')}
              </th>
              <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                {t('runs.col.project')}
              </th>
              <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                {t('runs.col.status')}
              </th>
              {tab === 'generation' ? (
                <>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.model')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.structure')}
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.runs')}
                  </th>
                </>
              ) : tab === 'analysis' ? (
                <>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('analysis.list.col.name')}
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('analysis.list.col.rows')}
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('analysis.list.col.estimates')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('analysis.list.col.specHash')}
                  </th>
                </>
              ) : (
                <>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.targetModel')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.judges')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.metrics')}
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('runs.col.samples')}
                  </th>
                </>
              )}
              <th className="px-4 py-3 text-right text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                {t('runs.col.duration')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 bg-white text-zinc-900 dark:divide-zinc-800 dark:bg-zinc-950 dark:text-zinc-100">
            {loading && (
              <tr>
                <td
                  colSpan={COLUMN_COUNT[tab]}
                  className="px-3 py-6 text-center text-xs text-zinc-500"
                >
                  {t('runs.loading')}
                </td>
              </tr>
            )}
            {!loading && data?.items.length === 0 && (
              <tr>
                <td
                  colSpan={COLUMN_COUNT[tab]}
                  className="px-3 py-6 text-center text-xs text-zinc-500"
                >
                  {t('runs.empty')}
                </td>
              </tr>
            )}
            {!loading &&
              data?.items.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => navigateToRun(run)}
                  className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                >
                  <td className="px-4 py-3 whitespace-nowrap text-zinc-700 dark:text-zinc-300">
                    {formatDate(run.created_at, locale)}
                  </td>
                  <td className="max-w-xs truncate px-4 py-3">
                    {run.project_title || (
                      <span className="text-zinc-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <RunStatusBadge status={run.status} />
                  </td>
                  {tab === 'generation' ? (
                    <>
                      <td className="px-4 py-3 font-mono text-xs">
                        {run.model_id || '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {run.structure_key || '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs">
                        {run.runs_requested && run.runs_requested > 1
                          ? `${run.runs_completed ?? 0}/${run.runs_requested}${
                              run.runs_failed
                                ? ` ${t('generations.detail.runsFailed', { count: run.runs_failed })}`
                                : ''
                            }`
                          : '1'}
                      </td>
                    </>
                  ) : tab === 'analysis' ? (
                    <>
                      <td
                        className="max-w-xs truncate px-4 py-3"
                        title={run.name ?? undefined}
                      >
                        {run.name || '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs">
                        {run.frame_rows ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs">
                        {run.estimates_count ?? '—'}
                      </td>
                      <td
                        className="px-4 py-3 font-mono text-xs"
                        title={run.spec_hash ?? undefined}
                      >
                        {run.spec_hash ? run.spec_hash.slice(0, 12) : '—'}
                      </td>
                    </>
                  ) : (
                    <>
                      <td
                        className="max-w-xs truncate px-4 py-3 font-mono text-xs"
                        title={evaluationModelsLabel(run)}
                      >
                        {evaluationModelsLabel(run)}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {run.judge_models && run.judge_models.length > 0
                          ? run.judge_models.join(', ')
                          : '—'}
                      </td>
                      <td
                        className="max-w-xs truncate px-4 py-3 font-mono text-xs"
                        title={run.metrics?.join(', ')}
                      >
                        {run.metrics && run.metrics.length > 0
                          ? run.metrics.join(', ')
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-right font-mono text-xs">
                        {run.samples_evaluated ?? '—'}
                      </td>
                    </>
                  )}
                  <td className="px-4 py-3 text-right text-xs text-zinc-500">
                    {formatDuration(run.created_at, run.completed_at)}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs text-zinc-500">
            {t('runs.pageInfo', { page, total: totalPages })}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={page <= 1 || loading}
              onClick={() => setPage(page - 1)}
            >
              {t('runs.prev')}
            </Button>
            <Button
              variant="outline"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(page + 1)}
            >
              {t('runs.next')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
