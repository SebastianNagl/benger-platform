'use client'

import { Badge } from '@/components/shared/Badge'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import { use, useEffect, useState } from 'react'

/**
 * Generation-run detail page (multi-run feature).
 *
 * Counterpart of /evaluations/[id]: shows the parent ResponseGeneration plus
 * every child Generation trial (one row per run_index) with status, error,
 * and a content preview. Reachable from the /runs inventory and from
 * notification deep links.
 */

interface ChildGeneration {
  id: string
  run_index: number
  status?: string | null
  created_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  has_response: boolean
  response_preview?: string | null
}

interface LinkedEvaluation {
  evaluation_id: string
  metric?: string | null
  status?: string | null
  completed_at?: string | null
  samples_evaluated?: number | null
}

interface GenerationRunDetail {
  id: string
  project_id?: string | null
  project_title?: string | null
  task_id?: string | null
  model_id?: string | null
  structure_key?: string | null
  status?: string | null
  created_at?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_by?: string | null
  error_message?: string | null
  runs_requested?: number | null
  runs_completed?: number | null
  runs_failed?: number | null
  parameters?: Record<string, unknown> | null
  prompt_used?: string | null
  children: ChildGeneration[]
  linked_evaluations?: LinkedEvaluation[]
}

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

function fmtDate(d?: string | null) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleString('de-DE')
  } catch {
    return d
  }
}

export default function GenerationRunDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const { t } = useI18n()
  const router = useRouter()
  const [data, setData] = useState<GenerationRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const resp = await apiClient.get(`/runs/generations/${id}`)
        if (!cancelled) setData(resp as GenerationRunDetail)
      } catch (err: any) {
        if (!cancelled) setError(err?.message || 'Failed to load generation run')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id])

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 text-sm text-zinc-500">
        {t('generations.detail.loading', 'Lade…')}
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error || 'Not found'}
        </div>
        <Button variant="text" className="mt-4" onClick={() => router.push('/runs?type=generation')}>
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {t('generations.detail.back', 'Zurück')}
        </Button>
      </div>
    )
  }

  const isMultiRun = (data.runs_requested ?? 1) > 1

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-4">
        <Breadcrumb
          items={[
            { label: 'Home', href: '/dashboard' },
            { label: t('runs.title', 'Läufe'), href: '/runs?type=generation' },
            { label: t('generations.detail.title', 'Generierungs-Lauf') },
          ]}
        />
      </div>
      <div className="mb-6 flex items-center gap-4">
        <Button variant="text" onClick={() => router.push('/runs?type=generation')}>
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {t('generations.detail.back', 'Zurück zu Läufe')}
        </Button>
      </div>

      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-900 dark:text-white">
          {t('generations.detail.title', 'Generierungs-Lauf')}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          <span className="font-mono text-xs">{data.id}</span>
          {data.project_title && (
            <>
              {' · '}
              {data.project_title}
            </>
          )}
        </p>
      </div>

      {/* Summary card — uses the shared Card component to match the
          project page / eval detail / dashboard look. */}
      <Card className="mb-6 grid grid-cols-2 gap-4 p-4 md:grid-cols-4">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.status', 'Status')}
          </div>
          <div className="mt-1">
            <StatusBadge status={data.status} />
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.model', 'Modell')}
          </div>
          <div className="mt-1 font-mono text-sm">{data.model_id || '—'}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.runs', 'Läufe')}
          </div>
          <div className="mt-1 font-mono text-sm">
            {data.runs_completed ?? 0}/{data.runs_requested ?? 1}
            {data.runs_failed ? ` (${data.runs_failed} fehlgeschlagen)` : ''}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.started', 'Gestartet')}
          </div>
          <div className="mt-1 text-sm">{fmtDate(data.created_at)}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.task', 'Task')}
          </div>
          <div className="mt-1 font-mono text-xs">{data.task_id || '—'}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.structure', 'Struktur')}
          </div>
          <div className="mt-1 font-mono text-xs">{data.structure_key || '—'}</div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">
            {t('generations.detail.completed', 'Abgeschlossen')}
          </div>
          <div className="mt-1 text-sm">{fmtDate(data.completed_at)}</div>
        </div>
        {data.project_id && (
          <div>
            <div className="text-xs uppercase tracking-wide text-zinc-500">
              {t('generations.detail.project', 'Projekt')}
            </div>
            <div className="mt-1">
              <Button
                variant="text"
                onClick={() => router.push(`/projects/${data.project_id}`)}
              >
                {data.project_title || data.project_id}
              </Button>
            </div>
          </div>
        )}
      </Card>

      {/* Error banner */}
      {data.status === 'failed' && data.error_message && (
        <div className="mb-6 rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <div className="font-medium">{t('generations.detail.error', 'Fehler')}</div>
          <pre className="mt-2 whitespace-pre-wrap text-xs">{data.error_message}</pre>
        </div>
      )}

      {/* Parameters */}
      {data.parameters && Object.keys(data.parameters).length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.parameters', 'Parameter')}
          </h2>
          <pre className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/40">
            {JSON.stringify(data.parameters, null, 2)}
          </pre>
        </div>
      )}

      {/* Per-trial breakdown */}
      {isMultiRun && data.children.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.trials', 'Pro Lauf')}
          </h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
              <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900/40 dark:text-zinc-400">
                <tr>
                  <th className="px-3 py-2">{t('generations.detail.runIndex', 'Lauf #')}</th>
                  <th className="px-3 py-2">{t('generations.detail.status', 'Status')}</th>
                  <th className="px-3 py-2">{t('generations.detail.completed', 'Abgeschlossen')}</th>
                  <th className="px-3 py-2">{t('generations.detail.preview', 'Antwort (Vorschau)')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {data.children.map((c) => (
                  <tr key={c.id}>
                    <td className="px-3 py-2 font-mono text-xs">{c.run_index}</td>
                    <td className="px-3 py-2">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="px-3 py-2 text-xs">{fmtDate(c.completed_at)}</td>
                    <td className="px-3 py-2 text-xs">
                      {c.error_message ? (
                        <span className="text-red-600 dark:text-red-400">{c.error_message}</span>
                      ) : c.response_preview ? (
                        <span className="text-zinc-700 dark:text-zinc-300">{c.response_preview}</span>
                      ) : (
                        <span className="text-zinc-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Single-run preview (no per-trial breakdown needed) */}
      {!isMultiRun && data.children.length > 0 && data.children[0].response_preview && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.response', 'Antwort')}
          </h2>
          <pre className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/40">
            {data.children[0].response_preview}
          </pre>
        </div>
      )}

      {/* Linked evaluations — every EvaluationRun that scored this gen's
          children. Lets the user hop straight into eval results. */}
      {data.linked_evaluations && data.linked_evaluations.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.linkedEvaluations', 'Verknüpfte Evaluierungen')}
          </h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
              <thead className="bg-zinc-50 text-left text-xs uppercase tracking-wide text-zinc-500 dark:bg-zinc-900/40 dark:text-zinc-400">
                <tr>
                  <th className="px-3 py-2">{t('generations.detail.metric', 'Metrik')}</th>
                  <th className="px-3 py-2">{t('generations.detail.status', 'Status')}</th>
                  <th className="px-3 py-2">{t('generations.detail.completed', 'Abgeschlossen')}</th>
                  <th className="px-3 py-2 text-right">{t('generations.detail.scoredSamples', 'Bewertete Samples')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {data.linked_evaluations.map((ev) => (
                  <tr
                    key={ev.evaluation_id}
                    onClick={() => router.push(`/evaluations/${ev.evaluation_id}`)}
                    className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                  >
                    <td className="px-3 py-2 font-mono text-xs">
                      {ev.metric || <span className="text-zinc-400">—</span>}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={ev.status} />
                    </td>
                    <td className="px-3 py-2 text-xs">{fmtDate(ev.completed_at)}</td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {ev.samples_evaluated ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Prompt used */}
      {data.prompt_used && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.prompt', 'Verwendeter Prompt')}
          </h2>
          <pre className="max-h-96 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/40">
            {data.prompt_used}
          </pre>
        </div>
      )}
    </div>
  )
}
