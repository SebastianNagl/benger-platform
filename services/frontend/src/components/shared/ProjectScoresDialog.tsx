'use client'

import { Alert } from '@/components/shared/Alert'
import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { EmptyState } from '@/components/shared/EmptyStates'
import { LoadingSpinner } from '@/components/shared/LoadingSpinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import {
  formatValueForScale,
  getMetricDefinitions,
  getMetricScale,
  metricDisplayName,
} from '@/lib/api/evaluation-types'
import { XMarkIcon } from '@heroicons/react/24/outline'
import Link from 'next/link'
import type { ReactNode } from 'react'

/** One (project, metric) cell: mean with sample size and 95 % CI. */
export interface ProjectScoreCell {
  mean: number
  ci_lower: number | null
  ci_upper: number | null
  n: number
}

/** One project row of the scores-by-project table. */
export interface ProjectScoreRow {
  project_id: string
  project_name: string
  project_kind: string | null
  is_public: boolean
  /** Subject-specific count (generations of a model, annotations of a user). */
  count: number
  samples_evaluated: number
  last_evaluated: string | null
  metrics: Record<string, ProjectScoreCell>
}

export type ScoresPeriod = 'overall' | 'monthly' | 'weekly'

export interface ProjectScoresDialogProps {
  open: boolean
  onClose: () => void
  /** Subject heading (model name, annotator display name). */
  title: string
  subtitle?: string
  /** Secondary badge next to the title (provider, "you", ...). */
  badge?: string
  rows: ProjectScoreRow[]
  /** Column order of the metric columns. */
  metrics: string[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  period: ScoresPeriod
  onPeriodChange: (period: ScoresPeriod) => void
  /** Header of the subject-specific count column. */
  countLabel: string
  emptyTitle?: string
  emptyDescription?: string
  /** Muted line above the table (e.g. anonymous-scope hint). */
  hint?: ReactNode
  /** Extra block above the table (e.g. an Alert about hidden projects). */
  notice?: ReactNode
  /**
   * Optional technical settings rendered in a collapsed "Technical details"
   * section with a Copy JSON button.
   */
  settingsJson?: Record<string, unknown> | null
  /** Prefix of the `data-testid`s (`<prefix>-modal`, `-table`, `-row-<id>`, ...). */
  testIdPrefix?: string
}

const KIND_LABEL_KEYS: Record<string, string> = {
  exam: 'projects.list.kindExam',
  flashcard_collection: 'projects.list.kindDeck',
}

const TH_CLASS =
  'px-4 py-3 text-right text-xs font-medium tracking-wider whitespace-nowrap text-zinc-500 uppercase dark:text-zinc-400'

/**
 * Generic "scores by project" dialog: one subject (a model, an annotator)
 * across every project the viewer may see, as a project x metric table with
 * a period switch. Callers own the data fetching; this renders it.
 */
export function ProjectScoresDialog({
  open,
  onClose,
  title,
  subtitle,
  badge,
  rows,
  metrics,
  isLoading,
  isError,
  onRetry,
  period,
  onPeriodChange,
  countLabel,
  emptyTitle,
  emptyDescription,
  hint,
  notice,
  settingsJson,
  testIdPrefix = 'model-detail',
}: ProjectScoresDialogProps) {
  const { t } = useI18n()

  // Nothing to render (and no Headless UI mount) while closed.
  if (!open) return null

  const metricDefs = getMetricDefinitions()
  const metricLabel = (key: string) => {
    const def = metricDefs[key]
    return def ? metricDisplayName(def, t) : key
  }
  const formatMetric = (key: string, value: number) =>
    formatValueForScale(value, getMetricScale(key), false)
  const formatCI = (key: string, m: ProjectScoreCell) => {
    if (m.ci_lower === null || m.ci_upper === null) return null
    return `${formatMetric(key, m.ci_lower)} – ${formatMetric(key, m.ci_upper)}`
  }
  const formatDate = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString() : '–'
  const settingsText = settingsJson
    ? JSON.stringify(settingsJson, null, 2)
    : null

  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose()
      }}
      className="max-w-5xl"
    >
      <div data-testid={`${testIdPrefix}-modal`}>
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate text-lg font-semibold text-zinc-900 dark:text-white">
                {title}
              </h3>
              {badge && <Badge variant="secondary">{badge}</Badge>}
            </div>
            {subtitle && (
              <p className="truncate text-sm text-zinc-500 dark:text-zinc-400">
                {subtitle}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('models.close')}
            className="shrink-0 rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>

        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
              {t('models.detail.scoresByProject')}
            </h4>
            {!isLoading && !isError && rows.length > 0 && (
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                {t('models.detail.projectCount', { count: rows.length })}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {t('models.detail.period')}
            </span>
            <Select
              value={period}
              onValueChange={(v) => onPeriodChange(v as ScoresPeriod)}
            >
              <SelectTrigger
                className="h-8 w-36"
                data-testid={`${testIdPrefix}-period`}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="overall">
                  {t('leaderboards.allTime')}
                </SelectItem>
                <SelectItem value="monthly">
                  {t('leaderboards.thisMonth')}
                </SelectItem>
                <SelectItem value="weekly">
                  {t('leaderboards.thisWeek')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        {hint && (
          <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
            {hint}
          </p>
        )}
        {notice && <div className="mb-3">{notice}</div>}

        {isLoading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : isError ? (
          <div role="alert">
            <Alert variant="error">
              <p className="text-sm text-red-700 dark:text-red-300">
                {t('models.detail.loadError')}
              </p>
              <Button variant="outline" className="mt-3" onClick={onRetry}>
                {t('models.detail.retry')}
              </Button>
            </Alert>
          </div>
        ) : rows.length === 0 ? (
          <div data-testid={`${testIdPrefix}-empty`}>
            <EmptyState
              title={emptyTitle ?? t('models.detail.noScoresTitle')}
              description={
                emptyDescription ?? t('models.detail.noScoresDescription')
              }
              className="py-8"
            />
          </div>
        ) : (
          <div className="max-h-[55vh] overflow-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
            <table
              className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-700"
              data-testid={`${testIdPrefix}-table`}
            >
              <thead className="bg-zinc-50 dark:bg-zinc-800">
                <tr>
                  <th
                    scope="col"
                    className="sticky left-0 z-10 bg-zinc-50 px-4 py-3 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:bg-zinc-800 dark:text-zinc-400"
                  >
                    {t('models.detail.project')}
                  </th>
                  {metrics.map((key) => (
                    <th key={key} scope="col" title={key} className={TH_CLASS}>
                      {metricLabel(key)}
                    </th>
                  ))}
                  <th scope="col" className={TH_CLASS}>
                    {countLabel}
                  </th>
                  <th scope="col" className={TH_CLASS}>
                    {t('leaderboards.llm.samples')}
                  </th>
                  <th scope="col" className={TH_CLASS}>
                    {t('leaderboards.llm.lastEvaluated')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
                {rows.map((p) => (
                  <tr
                    key={p.project_id}
                    data-testid={`${testIdPrefix}-row-${p.project_id}`}
                    className="hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                  >
                    <td className="sticky left-0 z-10 max-w-xs bg-white px-4 py-2 dark:bg-zinc-900">
                      <Link
                        href={`/projects/${p.project_id}`}
                        className="font-medium text-emerald-600 hover:text-emerald-700 hover:underline dark:text-emerald-400 dark:hover:text-emerald-300"
                      >
                        {p.project_name}
                      </Link>
                      <div className="mt-0.5 flex flex-wrap gap-1">
                        {p.project_kind && KIND_LABEL_KEYS[p.project_kind] && (
                          <Badge variant="outline" className="text-[10px]">
                            {t(KIND_LABEL_KEYS[p.project_kind])}
                          </Badge>
                        )}
                        {p.is_public && (
                          <Badge variant="outline" className="text-[10px]">
                            {t('models.detail.publicProject')}
                          </Badge>
                        )}
                      </div>
                    </td>
                    {metrics.map((key) => {
                      const m = p.metrics[key]
                      if (!m) {
                        return (
                          <td
                            key={key}
                            className="px-4 py-2 text-right text-zinc-400 dark:text-zinc-500"
                          >
                            {t('models.detail.notAvailable')}
                          </td>
                        )
                      }
                      const ci = formatCI(key, m)
                      return (
                        <td
                          key={key}
                          className="px-4 py-2 text-right whitespace-nowrap"
                        >
                          <span className="font-semibold text-zinc-900 dark:text-white">
                            {formatMetric(key, m.mean)}
                          </span>
                          <div className="text-xs text-zinc-500">
                            {t('models.detail.samplesShort', { count: m.n })}
                            {ci && (
                              <span
                                className="ml-1"
                                title={t('leaderboards.llm.confidenceInterval')}
                              >
                                [{ci}]
                              </span>
                            )}
                          </div>
                        </td>
                      )
                    })}
                    <td className="px-4 py-2 text-right whitespace-nowrap text-zinc-500">
                      {p.count.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap text-zinc-500">
                      {p.samples_evaluated.toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap text-zinc-500">
                      {formatDate(p.last_evaluated)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {settingsText && (
          <details className="mt-4 rounded-lg border border-zinc-200 dark:border-zinc-700">
            <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-zinc-700 select-none dark:text-zinc-300">
              {t('models.detail.technicalDetails')}
            </summary>
            <pre className="max-h-64 overflow-auto border-t border-zinc-200 bg-zinc-100 p-4 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-200">
              {settingsText}
            </pre>
          </details>
        )}

        <div className="mt-6 flex items-center justify-end space-x-2 border-t border-zinc-200 pt-4 dark:border-zinc-700">
          {settingsText && (
            <Button
              variant="outline"
              data-testid={`${testIdPrefix}-copy-json`}
              onClick={() => {
                void navigator.clipboard.writeText(settingsText)
              }}
            >
              {t('models.copyJson')}
            </Button>
          )}
          <Button variant="filled" onClick={onClose}>
            {t('models.close')}
          </Button>
        </div>
      </div>
    </Dialog>
  )
}
