/**
 * Sample Results Table Component
 *
 * Interactive table with drill-down for per-sample evaluation results.
 * Uses TanStack Table for sorting, filtering and pagination.
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { Alert } from '@/components/shared/Alert'
import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import {
  configDisplayLabel,
  fieldSelectorLabel,
  formatMetricNumber,
  isSidecarMetricKey,
  metricDisplayLabel,
  parseSampleFieldKey,
  readableSampleValue,
  type RunConfigLabel,
} from '@/lib/evaluation/runDisplay'
import {
  getMetricCell,
  getMetricDetail,
} from '@/lib/extensions/metricRenderers'
import {
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import {
  type ColumnDef,
  columnFilteringFeature,
  columnSizingFeature,
  columnVisibilityFeature,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_equals,
  filterFn_includesString,
  filterFn_weakEquals,
  flexRender,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
} from '@tanstack/react-table'
import clsx from 'clsx'
import { Fragment, type ReactNode, useMemo, useState } from 'react'

// TanStack Table v9 is feature-sliced: declare once, statically, which
// features and row models this table uses (sorting, per-column filtering for
// the text + status filters, client-side pagination).
const features = tableFeatures({
  columnFilteringFeature,
  columnSizingFeature, // header.getSize()
  columnVisibilityFeature, // row.getVisibleCells()
  rowSortingFeature,
  rowPaginationFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: {
    includesString: filterFn_includesString,
    equals: filterFn_equals,
    weakEquals: filterFn_weakEquals,
  },
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
})
type SampleTableFeatures = typeof features

/**
 * What a metric shows in the table: a registered extension cell renderer
 * first, then a plain number. Judge and Korrektur metrics are stored as a
 * {value, method, details, error} blob rather than a number; without a
 * renderer such a blob shows its numeric value. Anything else shows N/A
 * instead of calling a method the value does not have, which used to crash
 * the whole run page when a judge-graded row was expanded.
 */
function formatMetric(key: string, raw: unknown): ReactNode {
  const custom = getMetricCell(key)?.(raw)
  if (custom !== null && custom !== undefined) return custom
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return formatMetricNumber(key, raw)
  }
  if (raw && typeof raw === 'object') {
    const value = (raw as { value?: unknown }).value
    if (typeof value === 'number' && Number.isFinite(value)) {
      return formatMetricNumber(key, value)
    }
  }
  return 'N/A'
}

/** Metric keys a reader cares about: companion values stay hidden. */
function visibleMetricKeys(metrics: Record<string, unknown>): string[] {
  return Object.keys(metrics).filter((key) => !isSidecarMetricKey(key))
}

interface SampleResult {
  id: string
  task_id: string
  field_name: string
  answer_type: string
  ground_truth: Record<string, any> | string | null
  prediction: Record<string, any> | string | null
  metrics: Record<string, unknown>
  passed: boolean
  confidence_score: number | null
  error_message: string | null
  processing_time_ms: number | null
}

/**
 * Per-task consistency lookup (multi-run feature, migration 042).
 * Keys are task_ids; values come from the statistics endpoint's
 * task_consistency_by_model_metric block. Renders as an extra column when
 * provided AND at least one row has data; hidden otherwise.
 */
export interface TaskConsistencyEntry {
  n_runs: number
  variance?: number | null
  fleiss_kappa?: number | null
  percent_agreement?: number | null
}

interface SampleResultsTableProps {
  data: SampleResult[]
  onRowClick?: (sample: SampleResult) => void
  consistencyByTaskId?: Record<string, TaskConsistencyEntry>
  /** The run's evaluation configs, to name a sample by its config. */
  configs?: ReadonlyArray<RunConfigLabel>
  /** The project's label config, to name answer fields by their headers. */
  labelConfig?: string | null
}

type Translate = (
  key: string,
  varsOrFallback?: Record<string, unknown> | string,
) => string

/**
 * What the field column shows. The worker keys a sample as
 * `config|prediction_field|reference_field`; a reader wants the config's
 * name (else its metric's name) and the answer field it graded.
 */
function describeSampleField(
  sample: SampleResult,
  configs: ReadonlyArray<RunConfigLabel>,
  t: Translate,
  labelConfig?: string | null,
): { title: string; field: string | null } {
  const { configId, predictionField } = parseSampleFieldKey(sample.field_name)
  if (!configId) return { title: sample.field_name, field: null }
  const firstMetric = visibleMetricKeys(sample.metrics ?? {})[0]
  const field = fieldSelectorLabel(predictionField, t, labelConfig)
  const title = configDisplayLabel(configId, configs, firstMetric, t) ?? field
  return { title, field: title === field ? null : field }
}

// Long references (a Musterlösung runs to tens of thousands of characters)
// start collapsed so an expanded row stays scannable.
const COLLAPSE_CHARS = 600
const COLLAPSE_LINES = 12

function SampleValue({
  label,
  value,
  testId,
}: {
  label: string
  value: unknown
  testId: string
}) {
  const { t } = useI18n()
  const [showAll, setShowAll] = useState(false)
  const { text, isStructured } = readableSampleValue(value)
  const isLong =
    text.length > COLLAPSE_CHARS || text.split('\n').length > COLLAPSE_LINES
  const clamp = isLong && !showAll

  return (
    <div data-testid={testId} className="min-w-0">
      <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {label}
      </h4>
      <div className="rounded-md border border-zinc-200 bg-white p-3 dark:border-zinc-700 dark:bg-zinc-900">
        {text === '' ? (
          <p className="text-sm text-zinc-400 dark:text-zinc-500">
            {t('evaluation.sampleResultsTable.empty')}
          </p>
        ) : isStructured ? (
          <pre
            className={clsx(
              'overflow-auto font-mono text-xs text-zinc-800 dark:text-zinc-200',
              clamp && 'max-h-60',
            )}
          >
            {text}
          </pre>
        ) : (
          <div
            className={clsx(
              'text-sm leading-relaxed break-words whitespace-pre-wrap text-zinc-800 dark:text-zinc-200',
              clamp && 'max-h-60 overflow-hidden',
            )}
          >
            {text}
          </div>
        )}
        {isLong && (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="mt-2 text-sm font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300"
          >
            {showAll
              ? t('evaluation.sampleResultsTable.showLess')
              : t('evaluation.sampleResultsTable.showMore')}
          </button>
        )}
      </div>
    </div>
  )
}

export function SampleResultsTable({
  data,
  onRowClick,
  consistencyByTaskId,
  configs = [],
  labelConfig = null,
}: SampleResultsTableProps) {
  const { t } = useI18n()
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')

  // Show the consistency column only when the caller supplied data AND at
  // least one task has more than 1 run. For legacy single-run evaluations
  // this stays hidden so the table layout doesn't change unexpectedly.
  const showConsistencyColumn = useMemo(() => {
    if (!consistencyByTaskId) return false
    return Object.values(consistencyByTaskId).some((c) => (c?.n_runs ?? 0) > 1)
  }, [consistencyByTaskId])

  const columns = useMemo<ColumnDef<SampleTableFeatures, SampleResult>[]>(
    () => [
      {
        accessorKey: 'passed',
        header: t('evaluation.sampleResultsTable.status'),
        cell: ({ row }) => (
          <div className="flex items-center justify-center">
            {row.original.passed ? (
              <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
            ) : (
              <XCircleIcon className="h-5 w-5 text-red-500" />
            )}
          </div>
        ),
        size: 80,
      },
      {
        accessorKey: 'task_id',
        header: t('evaluation.sampleResultsTable.taskId'),
        cell: ({ row }) => (
          <code className="font-mono text-xs text-zinc-600 dark:text-zinc-400">
            {row.original.task_id.substring(0, 8)}...
          </code>
        ),
        size: 120,
      },
      {
        // Sorted and filtered by what the reader sees, not the stored key.
        id: 'field_name',
        accessorFn: (sample) => {
          const { title, field } = describeSampleField(
            sample,
            configs,
            t,
            labelConfig,
          )
          return field ? `${title} ${field}` : title
        },
        header: t('evaluation.sampleResultsTable.field'),
        cell: ({ row }) => {
          const { title, field } = describeSampleField(
            row.original,
            configs,
            t,
            labelConfig,
          )
          return (
            <div className="min-w-0">
              <div className="font-medium text-zinc-900 dark:text-white">
                {title}
              </div>
              {field && (
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {field}
                </div>
              )}
            </div>
          )
        },
        size: 180,
      },
      {
        accessorKey: 'answer_type',
        header: t('evaluation.sampleResultsTable.type'),
        cell: ({ row }) => (
          <Badge variant="outline">{row.original.answer_type}</Badge>
        ),
        size: 100,
      },
      {
        id: 'metrics',
        header: t('evaluation.sampleResultsTable.metrics'),
        cell: ({ row }) => {
          const metrics = row.original.metrics
          const metricNames = visibleMetricKeys(metrics)
          if (metricNames.length === 0)
            return <span className="text-zinc-400">-</span>

          return (
            <div className="flex flex-wrap gap-x-3 gap-y-1">
              {metricNames.slice(0, 2).map((key) => (
                <div key={key} className="text-xs">
                  <span className="font-medium text-zinc-700 dark:text-zinc-300">
                    {metricDisplayLabel(key, undefined, t)}:
                  </span>{' '}
                  <span className="text-emerald-700 tabular-nums dark:text-emerald-400">
                    {formatMetric(key, metrics[key])}
                  </span>
                </div>
              ))}
              {metricNames.length > 2 && (
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                  {t('evaluation.sampleResultsTable.moreMetrics', {
                    count: metricNames.length - 2,
                  })}
                </span>
              )}
            </div>
          )
        },
        size: 200,
      },
      {
        accessorKey: 'confidence_score',
        header: t('evaluation.sampleResultsTable.confidence'),
        cell: ({ row }) => {
          const score = row.original.confidence_score
          if (score === null) return <span className="text-zinc-400">-</span>

          const colorClass =
            score >= 0.8
              ? 'text-emerald-600 dark:text-emerald-400'
              : score >= 0.5
                ? 'text-amber-600 dark:text-amber-400'
                : 'text-red-600 dark:text-red-400'

          return (
            <span className={`font-medium tabular-nums ${colorClass}`}>
              {(score * 100).toFixed(1)}%
            </span>
          )
        },
        size: 100,
      },
      {
        accessorKey: 'processing_time_ms',
        header: t('evaluation.sampleResultsTable.timeMs'),
        cell: ({ row }) => {
          const time = row.original.processing_time_ms
          return time !== null ? time.toFixed(0) : '-'
        },
        size: 100,
      },
      // Multi-run consistency column (migration 042). Shows variance across
      // runs of the same task; rendered only when consistencyByTaskId is
      // present and at least one task has n_runs > 1 (showConsistencyColumn).
      ...(showConsistencyColumn
        ? [
            {
              id: 'consistency',
              header: t(
                'evaluation.sampleResultsTable.consistency',
                'Konsistenz',
              ),
              cell: ({ row }: { row: { original: SampleResult } }) => {
                const c = consistencyByTaskId?.[row.original.task_id]
                if (!c || (c.n_runs ?? 0) < 2) {
                  return <span className="text-zinc-400">—</span>
                }
                if (c.variance !== null && c.variance !== undefined) {
                  return (
                    <span
                      className="font-mono text-xs"
                      title={`n_runs=${c.n_runs}`}
                    >
                      σ²={c.variance.toFixed(4)}
                    </span>
                  )
                }
                if (c.fleiss_kappa !== null && c.fleiss_kappa !== undefined) {
                  return (
                    <span
                      className="font-mono text-xs"
                      title={`Fleiss κ across ${c.n_runs} runs`}
                    >
                      κ={c.fleiss_kappa.toFixed(3)}
                    </span>
                  )
                }
                return <span className="text-zinc-400">—</span>
              },
              size: 110,
            } as ColumnDef<SampleTableFeatures, SampleResult>,
          ]
        : []),
      {
        id: 'actions',
        header: t('evaluation.sampleResultsTable.details'),
        cell: ({ row }) => (
          <Button
            variant="text"
            aria-expanded={expandedRow === row.id}
            onClick={() => {
              setExpandedRow(expandedRow === row.id ? null : row.id)
            }}
          >
            {expandedRow === row.id ? (
              <ChevronUpIcon className="h-4 w-4" />
            ) : (
              <ChevronDownIcon className="h-4 w-4" />
            )}
          </Button>
        ),
        size: 80,
      },
    ],
    [
      expandedRow,
      t,
      showConsistencyColumn,
      consistencyByTaskId,
      configs,
      labelConfig,
    ],
  )

  const table = useTable<SampleTableFeatures, SampleResult>({
    features,
    data,
    columns,
    initialState: {
      pagination: {
        pageIndex: 0,
        pageSize: 25,
      },
    },
  })

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="min-w-48 flex-1">
          <Input
            type="text"
            placeholder={t('evaluation.sampleResultsTable.filterPlaceholder')}
            onChange={(e) =>
              table.getColumn('field_name')?.setFilterValue(e.target.value)
            }
          />
        </div>
        <div>
          <Select
            value={statusFilter}
            onValueChange={(value) => {
              setStatusFilter(value)
              table
                .getColumn('passed')
                ?.setFilterValue(
                  value === 'all' ? undefined : value === 'passed',
                )
            }}
          >
            <SelectTrigger>
              <SelectValue
                placeholder={t('evaluation.sampleResultsTable.allStatus')}
              />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                {t('evaluation.sampleResultsTable.allStatus')}
              </SelectItem>
              <SelectItem value="passed">
                {t('evaluation.sampleResultsTable.passedOnly')}
              </SelectItem>
              <SelectItem value="failed">
                {t('evaluation.sampleResultsTable.failedOnly')}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table className="w-full divide-y divide-zinc-200 dark:divide-zinc-800">
          <thead className="bg-zinc-50 dark:bg-zinc-800/50">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sorted = header.column.getIsSorted()
                  return (
                    <th
                      key={header.id}
                      aria-sort={
                        sorted === 'asc'
                          ? 'ascending'
                          : sorted === 'desc'
                            ? 'descending'
                            : undefined
                      }
                      className="px-4 py-3 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400"
                      style={{ width: header.getSize() }}
                    >
                      {header.isPlaceholder ? null : (
                        <div
                          className={clsx(
                            'inline-flex items-center gap-1',
                            header.column.getCanSort() &&
                              'cursor-pointer select-none hover:text-zinc-700 dark:hover:text-zinc-200',
                          )}
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(
                            header.column.columnDef.header,
                            header.getContext(),
                          )}
                          {sorted === 'asc' && (
                            <ChevronUpIcon
                              className="h-3.5 w-3.5"
                              aria-hidden="true"
                            />
                          )}
                          {sorted === 'desc' && (
                            <ChevronDownIcon
                              className="h-3.5 w-3.5"
                              aria-hidden="true"
                            />
                          )}
                        </div>
                      )}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-800 dark:bg-zinc-900">
            {table.getRowModel().rows.map((row) => (
              <Fragment key={row.id}>
                <tr
                  className="cursor-pointer transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-4 py-3 align-top text-sm text-zinc-700 dark:text-zinc-300"
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  ))}
                </tr>

                {/* Expanded Row Details */}
                {expandedRow === row.id && (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="bg-zinc-50 p-4 dark:bg-zinc-800/40"
                    >
                      <div className="space-y-4">
                        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                          <SampleValue
                            label={t(
                              'evaluation.sampleResultsTable.groundTruth',
                            )}
                            value={row.original.ground_truth}
                            testId="sample-ground-truth"
                          />
                          <SampleValue
                            label={t(
                              'evaluation.sampleResultsTable.prediction',
                            )}
                            value={row.original.prediction}
                            testId="sample-prediction"
                          />
                        </div>

                        <div>
                          <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
                            {t('evaluation.sampleResultsTable.allMetrics')}
                          </h4>
                          <div className="grid grid-cols-2 gap-3 rounded-md border border-zinc-200 bg-white p-3 md:grid-cols-4 lg:grid-cols-6 dark:border-zinc-700 dark:bg-zinc-900">
                            {visibleMetricKeys(row.original.metrics).map(
                              (key) => {
                                const value = row.original.metrics[key]
                                // As in ResultsTabs: a metric that registers a
                                // detail component renders its full payload,
                                // for a Bewertungsbogen the filled sheet,
                                // across the row instead of a single number.
                                const DetailComp = getMetricDetail(key)
                                if (DetailComp) {
                                  return (
                                    <div key={key} className="col-span-full">
                                      <DetailComp
                                        value={value}
                                        evaluation={
                                          row.original as unknown as Record<
                                            string,
                                            unknown
                                          >
                                        }
                                      />
                                    </div>
                                  )
                                }
                                return (
                                  <div key={key} className="text-sm">
                                    <div className="text-xs text-zinc-500 dark:text-zinc-400">
                                      {metricDisplayLabel(key, undefined, t)}
                                    </div>
                                    <div className="font-medium text-zinc-900 tabular-nums dark:text-white">
                                      {formatMetric(key, value)}
                                    </div>
                                  </div>
                                )
                              },
                            )}
                          </div>
                        </div>

                        {row.original.error_message && (
                          <Alert variant="error">
                            <h4 className="font-medium text-red-800 dark:text-red-200">
                              {t('evaluation.sampleResultsTable.error')}
                            </h4>
                            <p className="mt-1 text-sm break-words text-red-800 dark:text-red-200">
                              {row.original.error_message}
                            </p>
                          </Alert>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('evaluation.sampleResultsTable.showing')}{' '}
          {table.state.pagination.pageIndex * table.state.pagination.pageSize +
            1}{' '}
          {t('evaluation.sampleResultsTable.to')}{' '}
          {Math.min(
            (table.state.pagination.pageIndex + 1) *
              table.state.pagination.pageSize,
            table.getFilteredRowModel().rows.length,
          )}{' '}
          {t('evaluation.sampleResultsTable.of')}{' '}
          {table.getFilteredRowModel().rows.length}{' '}
          {t('evaluation.sampleResultsTable.results')}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            {t('evaluation.sampleResultsTable.previous')}
          </Button>
          <Button
            variant="outline"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            {t('evaluation.sampleResultsTable.next')}
          </Button>
        </div>
      </div>
    </div>
  )
}
