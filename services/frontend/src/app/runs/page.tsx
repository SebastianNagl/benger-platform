'use client'

import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { projectsAPI } from '@/lib/api/projects'
import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useEffect, useState } from 'react'

/**
 * Single-run inventory page (multi-run feature).
 *
 * Shows individual generation and evaluation runs across the platform — the
 * canonical "find a run" view. Clicking a row deep-links into the detail
 * page for that run. The aggregate dashboards at /evaluations and /generations
 * keep their existing role (cross-run scoresheets per project / per model).
 *
 * Notification routing in NotificationDropdown also points here.
 */

type RunType = 'generation' | 'evaluation'

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
  judge_models?: string[] | null
  samples_evaluated?: number | null
  metrics?: string[] | null
}

interface PaginatedRunsResponse {
  items: RunSummary[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 25

function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-zinc-400">—</span>
  const tone =
    status === 'completed'
      ? 'success'
      : status === 'failed'
        ? 'error'
        : status === 'running' || status === 'pending'
          ? 'warning'
          : 'secondary'
  return <Badge variant={tone as any}>{status}</Badge>
}

function formatDate(d?: string | null) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleString('de-DE', {
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

export default function RunsPage() {
  const { t } = useI18n()
  const router = useRouter()
  const searchParams = useSearchParams()
  const initialTab = (searchParams?.get('type') as RunType) || 'evaluation'
  const initialProject = searchParams?.get('project_id') || ''
  const [tab, setTab] = useState<RunType>(initialTab)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>('')
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
        const items = (resp?.items || []) as Array<{ id: string; title: string }>
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
      setError(err?.message || 'Failed to load runs')
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

  useEffect(() => {
    load()
  }, [load])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  const navigateToRun = (run: RunSummary) => {
    if (run.type === 'evaluation') {
      router.push(`/evaluations/${run.id}`)
    } else {
      router.push(`/generations/${run.id}`)
    }
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: 'Home', href: '/dashboard' },
            { label: t('runs.title', 'Läufe') },
          ]}
        />
      </div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zinc-900 dark:text-white">
            {t('runs.title', 'Läufe')}
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {t(
              'runs.subtitle',
              'Inventar einzelner Generierungs- und Evaluierungsläufe. Klicken Sie eine Zeile an, um die Details des Laufs zu sehen.',
            )}
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-4 border-b border-zinc-200 dark:border-zinc-800">
        <nav className="-mb-px flex gap-6">
          {(['evaluation', 'generation'] as RunType[]).map((tname) => (
            <button
              key={tname}
              onClick={() => handleTabChange(tname)}
              className={`whitespace-nowrap border-b-2 py-3 text-sm font-medium ${
                tab === tname
                  ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                  : 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200'
              }`}
            >
              {tname === 'evaluation'
                ? t('runs.tabs.evaluation', 'Evaluierungen')
                : t('runs.tabs.generation', 'Generierungen')}
            </button>
          ))}
        </nav>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label className="text-xs text-zinc-500">{t('runs.filterProject', 'Projekt')}</label>
        <select
          value={projectFilter}
          onChange={(e) => handleProjectChange(e.target.value)}
          className="h-8 rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">{t('runs.allProjects', 'Alle Projekte')}</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
        <label className="text-xs text-zinc-500">{t('runs.filterStatus', 'Status')}</label>
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value)
            setPage(1)
          }}
          className="h-8 rounded-md border border-zinc-300 bg-white px-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          <option value="">{t('runs.allStatuses', 'Alle')}</option>
          <option value="pending">pending</option>
          <option value="running">running</option>
          <option value="completed">completed</option>
          <option value="failed">failed</option>
        </select>
        <span className="ml-auto text-xs text-zinc-500">
          {data
            ? String(t('runs.totalCount', '{count} Einträge')).replace(
                '{count}',
                String(data.total),
              )
            : ''}
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
          <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900/40 dark:text-zinc-400">
            <tr>
              <th className="px-3 py-2">{t('runs.col.started', 'Gestartet')}</th>
              <th className="px-3 py-2">{t('runs.col.project', 'Projekt')}</th>
              <th className="px-3 py-2">{t('runs.col.status', 'Status')}</th>
              {tab === 'generation' ? (
                <>
                  <th className="px-3 py-2">{t('runs.col.model', 'Modell')}</th>
                  <th className="px-3 py-2">{t('runs.col.structure', 'Struktur')}</th>
                  <th className="px-3 py-2 text-right">{t('runs.col.runs', 'Läufe')}</th>
                </>
              ) : (
                <>
                  <th className="px-3 py-2">{t('runs.col.targetModel', 'Ziel-Modell')}</th>
                  <th className="px-3 py-2">{t('runs.col.judges', 'Judges')}</th>
                  <th className="px-3 py-2">{t('runs.col.metrics', 'Metriken')}</th>
                  <th className="px-3 py-2 text-right">{t('runs.col.samples', 'Samples')}</th>
                </>
              )}
              <th className="px-3 py-2 text-right">{t('runs.col.duration', 'Dauer')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
            {loading && (
              <tr>
                <td colSpan={tab === 'generation' ? 7 : 8} className="px-3 py-6 text-center text-xs text-zinc-500">
                  {t('runs.loading', 'Lade…')}
                </td>
              </tr>
            )}
            {!loading && data?.items.length === 0 && (
              <tr>
                <td colSpan={tab === 'generation' ? 7 : 8} className="px-3 py-6 text-center text-xs text-zinc-500">
                  {t('runs.empty', 'Keine Einträge')}
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
                  <td className="px-3 py-2 whitespace-nowrap text-zinc-700 dark:text-zinc-300">
                    {formatDate(run.created_at)}
                  </td>
                  <td className="px-3 py-2 max-w-xs truncate">
                    {run.project_title || (
                      <span className="text-zinc-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <StatusBadge status={run.status} />
                  </td>
                  {tab === 'generation' ? (
                    <>
                      <td className="px-3 py-2 font-mono text-xs">{run.model_id || '—'}</td>
                      <td className="px-3 py-2 font-mono text-xs">{run.structure_key || '—'}</td>
                      <td className="px-3 py-2 text-right font-mono text-xs">
                        {run.runs_requested && run.runs_requested > 1
                          ? `${run.runs_completed ?? 0}/${run.runs_requested}${
                              run.runs_failed ? ` (${run.runs_failed} fehlgeschlagen)` : ''
                            }`
                          : '1'}
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 py-2 font-mono text-xs">{run.model_id || '—'}</td>
                      <td className="px-3 py-2 font-mono text-xs">
                        {run.judge_models && run.judge_models.length > 0
                          ? run.judge_models.join(', ')
                          : '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs max-w-xs truncate" title={run.metrics?.join(', ')}>
                        {run.metrics && run.metrics.length > 0 ? run.metrics.join(', ') : '—'}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs">
                        {run.samples_evaluated ?? '—'}
                      </td>
                    </>
                  )}
                  <td className="px-3 py-2 text-right text-xs text-zinc-500">
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
            {String(t('runs.pageInfo', 'Seite {page} von {total}'))
              .replace('{page}', String(page))
              .replace('{total}', String(totalPages))}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={page <= 1 || loading}
              onClick={() => setPage(page - 1)}
            >
              {t('runs.prev', 'Zurück')}
            </Button>
            <Button
              variant="outline"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(page + 1)}
            >
              {t('runs.next', 'Weiter')}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
