'use client'

import { RequestRecordView } from '@/components/analysis/RequestRecordView'
import { SeedNotSentNotice } from '@/components/generation/SeedNotSentNotice'
import { Breadcrumb } from '@/components/shared/Breadcrumb'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { RunStatusBadge } from '@/components/shared/RunStatusBadge'
import { useI18n } from '@/contexts/I18nContext'
import apiClient from '@/lib/api'
import type { TrialRequestView } from '@/lib/api/variantViews'
import { useFeatureFlag } from '@/lib/featureFlags'
import { VARIANT_EXPERIMENTS } from '@/lib/featureFlags/platformFlags'
import { intlTag } from '@/lib/i18n/locales'
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
  has_request_record?: boolean
  request_sha256?: string | null
  retried?: boolean
  first_response_preview?: string | null
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

/** The request a trial sent, as the provider client recorded it. */
function SentRequest({
  generationId,
  child,
}: {
  generationId: string
  child: ChildGeneration
}) {
  const { t } = useI18n()
  const [trial, setTrial] = useState<TrialRequestView | null>(null)
  const [error, setError] = useState<string | null>(null)
  const recorded = Boolean(child.has_request_record || child.request_sha256)

  useEffect(() => {
    if (!recorded) return
    let cancelled = false
    ;(async () => {
      try {
        const resp = await apiClient.get(
          `/runs/generations/${generationId}/trials/${child.id}/request`,
        )
        if (!cancelled) setTrial(resp as TrialRequestView)
      } catch (err: any) {
        if (!cancelled)
          setError(err?.message || t('generations.detail.request.loadFailed'))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [generationId, child.id, recorded])

  if (recorded && !trial && !error) {
    return (
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {t('generations.detail.request.loading')}
      </p>
    )
  }
  if (error) {
    return (
      <p className="text-xs text-red-700 dark:text-red-400" role="alert">
        {error}
      </p>
    )
  }
  if (!trial || (!trial.request_record && !trial.request_sha256)) {
    return (
      <p className="text-xs text-zinc-500 italic dark:text-zinc-400">
        {t('generations.detail.request.none')}
      </p>
    )
  }
  return (
    <div data-testid="sent-request">
      <RequestRecordView
        view={{
          ...trial,
          // The detail row knows the retry trail of older API answers.
          retried: trial.retried ?? child.retried,
          first_response: trial.first_response ?? child.first_response_preview,
        }}
      />
    </div>
  )
}

function fmtDate(d: string | null | undefined, locale: string) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleString(intlTag(locale))
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
  const { t, locale } = useI18n()
  const variantExperiments = useFeatureFlag(VARIANT_EXPERIMENTS)
  const router = useRouter()
  const [data, setData] = useState<GenerationRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [requestRun, setRequestRun] = useState(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        const resp = await apiClient.get(`/runs/generations/${id}`)
        if (!cancelled) setData(resp as GenerationRunDetail)
      } catch (err: any) {
        if (!cancelled)
          setError(err?.message || t('generations.detail.loadFailed'))
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
        {t('generations.detail.loading')}
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error || 'Not found'}
        </div>
        <Button
          variant="text"
          className="mt-4"
          onClick={() => router.push('/runs?type=generation')}
        >
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {t('generations.detail.back')}
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
            { label: t('navigation.dashboard'), href: '/dashboard' },
            { label: t('runs.title'), href: '/runs?type=generation' },
            { label: t('generations.detail.title') },
          ]}
        />
      </div>
      <div className="mb-6 flex items-center gap-4">
        <Button
          variant="text"
          onClick={() => router.push('/runs?type=generation')}
        >
          <ArrowLeftIcon className="mr-2 h-4 w-4" />
          {t('generations.detail.back')}
        </Button>
      </div>

      <div className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          {t('generations.detail.title')}
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
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
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.status')}
          </div>
          <div className="mt-1">
            <RunStatusBadge status={data.status} />
          </div>
        </div>
        <div>
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.model')}
          </div>
          <div className="mt-1 font-mono text-sm">{data.model_id || '—'}</div>
        </div>
        <div>
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.runs')}
          </div>
          <div className="mt-1 font-mono text-sm">
            {data.runs_completed ?? 0}/{data.runs_requested ?? 1}
            {data.runs_failed
              ? ` ${t('generations.detail.runsFailed', { count: data.runs_failed })}`
              : ''}
          </div>
        </div>
        <div>
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.started')}
          </div>
          <div className="mt-1 text-sm">{fmtDate(data.created_at, locale)}</div>
        </div>
        <div>
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.task')}
          </div>
          <div className="mt-1 font-mono text-xs">{data.task_id || '—'}</div>
        </div>
        <div>
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.structure')}
          </div>
          <div className="mt-1 font-mono text-xs">
            {data.structure_key || '—'}
          </div>
        </div>
        <div>
          <div className="text-xs tracking-wide text-zinc-500 uppercase">
            {t('generations.detail.completed')}
          </div>
          <div className="mt-1 text-sm">
            {fmtDate(data.completed_at, locale)}
          </div>
        </div>
        {data.project_id && (
          <div>
            <div className="text-xs tracking-wide text-zinc-500 uppercase">
              {t('generations.detail.project')}
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
          <div className="font-medium">{t('generations.detail.error')}</div>
          <pre className="mt-2 text-xs whitespace-pre-wrap">
            {data.error_message}
          </pre>
        </div>
      )}

      {/* Parameters */}
      {data.parameters && Object.keys(data.parameters).length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.parameters')}
          </h2>
          <SeedNotSentNotice parameters={data.parameters} className="mb-2" />
          <pre className="rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/40">
            {JSON.stringify(data.parameters, null, 2)}
          </pre>
        </div>
      )}

      {/* Per-trial breakdown */}
      {isMultiRun && data.children.length > 0 && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t('generations.detail.trials')}
          </h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
              <thead className="bg-zinc-50 text-left text-xs tracking-wide text-zinc-500 uppercase dark:bg-zinc-900/40 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.runIndex')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.status')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.completed')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.preview')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {data.children.map((c) => (
                  <tr key={c.id}>
                    <td className="px-4 py-3 font-mono text-xs">
                      {c.run_index}
                    </td>
                    <td className="px-4 py-3">
                      <RunStatusBadge status={c.status} />
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {fmtDate(c.completed_at, locale)}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {c.error_message ? (
                        <span className="text-red-600 dark:text-red-400">
                          {c.error_message}
                        </span>
                      ) : c.response_preview ? (
                        <span className="text-zinc-700 dark:text-zinc-300">
                          {c.response_preview}
                        </span>
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
      {!isMultiRun &&
        data.children.length > 0 &&
        data.children[0].response_preview && (
          <div className="mb-6">
            <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
              {t('generations.detail.response')}
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
            {t('generations.detail.linkedEvaluations')}
          </h2>
          <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
              <thead className="bg-zinc-50 text-left text-xs tracking-wide text-zinc-500 uppercase dark:bg-zinc-900/40 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.metric')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.status')}
                  </th>
                  <th className="px-4 py-3 text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.completed')}
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400">
                    {t('generations.detail.scoredSamples')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
                {data.linked_evaluations.map((ev) => (
                  <tr
                    key={ev.evaluation_id}
                    onClick={() =>
                      router.push(`/evaluations/${ev.evaluation_id}`)
                    }
                    className="cursor-pointer hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                  >
                    <td className="px-4 py-3 font-mono text-xs">
                      {ev.metric || <span className="text-zinc-400">—</span>}
                    </td>
                    <td className="px-4 py-3">
                      <RunStatusBadge status={ev.status} />
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {fmtDate(ev.completed_at, locale)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs">
                      {ev.samples_evaluated ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* What the provider client actually sent (per trial); the request
          record belongs to the variant_experiments flag */}
      {variantExperiments && data.children.length > 0 && (
        <div className="mb-6">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-white">
              {t('generations.detail.request.title')}
            </h2>
            {data.children.length > 1 && (
              <label className="flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400">
                {t('generations.detail.runIndex')}
                <select
                  value={requestRun}
                  onChange={(e) => setRequestRun(Number(e.target.value))}
                  className="rounded-md border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-900"
                  data-testid="request-run-select"
                >
                  {data.children.map((c, i) => (
                    <option key={c.id} value={i}>
                      {c.run_index}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
            {t('generations.detail.request.help')}
          </p>
          <SentRequest
            key={
              data.children[Math.min(requestRun, data.children.length - 1)].id
            }
            generationId={data.id}
            child={
              data.children[Math.min(requestRun, data.children.length - 1)]
            }
          />
        </div>
      )}

      {/* Prompt templates of the structure (not what was sent) */}
      {data.prompt_used && (
        <div className="mb-6">
          <h2 className="mb-2 text-sm font-semibold text-zinc-900 dark:text-white">
            {t(
              variantExperiments
                ? 'generations.detail.promptTemplates'
                : 'generations.detail.prompt',
            )}
          </h2>
          <pre className="max-h-96 overflow-auto rounded-md border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/40">
            {data.prompt_used}
          </pre>
        </div>
      )}
    </div>
  )
}
