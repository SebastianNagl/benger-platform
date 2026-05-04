/**
 * Sample Results Table Component
 *
 * Interactive table with drill-down for per-sample evaluation results.
 * Uses TanStack Table v8 for performance and flexibility.
 * Issue #763: Per-sample evaluation results and visualization dashboard
 */

'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { getMetricCell } from '@/lib/extensions/metricRenderers'
import {
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useMemo, useState } from 'react'

interface SampleResult {
  id: string
  task_id: string
  field_name: string
  answer_type: string
  ground_truth: Record<string, any>
  prediction: Record<string, any>
  metrics: Record<string, number>
  passed: boolean
  confidence_score: number | null
  error_message: string | null
  processing_time_ms: number | null
}

interface SampleResultsTableProps {
  data: SampleResult[]
  onRowClick?: (sample: SampleResult) => void
}

export function SampleResultsTable({
  data,
  onRowClick,
}: SampleResultsTableProps) {
  const { t } = useI18n()
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')

  const columns = useMemo<ColumnDef<SampleResult>[]>(
    () => [
      {
        accessorKey: 'passed',
        header: t('evaluation.sampleResultsTable.status'),
        cell: ({ row }) => (
          <div className="flex items-center justify-center">
            {row.original.passed ? (
              <CheckCircleIcon className="h-5 w-5 text-green-500" />
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
          <code className="font-mono text-xs">
            {row.original.task_id.substring(0, 8)}...
          </code>
        ),
        size: 120,
      },
      {
        accessorKey: 'field_name',
        header: t('evaluation.sampleResultsTable.field'),
        size: 120,
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
          const metricNames = Object.keys(metrics)
          if (metricNames.length === 0)
            return <span className="text-gray-400">-</span>

          return (
            <div className="flex flex-wrap gap-1">
              {metricNames.slice(0, 2).map((key) => {
                // Extension hook: extended metrics (e.g. korrektur_falloesung)
                // can register a cell renderer to extract the score from a
                // structured value blob ({value, method, details, error}).
                const customCell = getMetricCell(key)?.(metrics[key])
                if (customCell !== null && customCell !== undefined) {
                  return (
                    <div key={key} className="text-xs">
                      <span className="font-medium">{key}:</span>{' '}
                      <span className="text-blue-600">{customCell}</span>
                    </div>
                  )
                }
                return (
                  <div key={key} className="text-xs">
                    <span className="font-medium">{key}:</span>{' '}
                    <span className="text-blue-600">
                      {(metrics[key] as number)?.toFixed?.(3) ?? 'N/A'}
                    </span>
                  </div>
                )
              })}
              {metricNames.length > 2 && (
                <span className="text-xs text-gray-500">
                  {t('evaluation.sampleResultsTable.moreMetrics', { count: metricNames.length - 2 })}
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
          if (score === null) return <span className="text-gray-400">-</span>

          const colorClass =
            score >= 0.8
              ? 'text-green-600'
              : score >= 0.5
                ? 'text-yellow-600'
                : 'text-red-600'

          return (
            <span className={`font-medium ${colorClass}`}>
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
      {
        id: 'actions',
        header: t('evaluation.sampleResultsTable.details'),
        cell: ({ row }) => (
          <Button
            variant="text"
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
    [expandedRow, t]
  )

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: {
      pagination: {
        pageSize: 25,
      },
    },
  })

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder={t('evaluation.sampleResultsTable.filterPlaceholder')}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
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
                  value === 'all' ? undefined : value === 'passed'
                )
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder={t('evaluation.sampleResultsTable.allStatus')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('evaluation.sampleResultsTable.allStatus')}</SelectItem>
              <SelectItem value="passed">{t('evaluation.sampleResultsTable.passedOnly')}</SelectItem>
              <SelectItem value="failed">{t('evaluation.sampleResultsTable.failedOnly')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full">
          <thead className="bg-gray-50">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-700"
                    style={{ width: header.getSize() }}
                  >
                    {header.isPlaceholder ? null : (
                      <div
                        className={
                          header.column.getCanSort()
                            ? 'cursor-pointer select-none'
                            : ''
                        }
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                        {{
                          asc: ' 🔼',
                          desc: ' 🔽',
                        }[header.column.getIsSorted() as string] ?? null}
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-gray-200 bg-white">
            {table.getRowModel().rows.map((row) => (
              <>
                <tr
                  key={row.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => onRowClick?.(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-sm">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </td>
                  ))}
                </tr>

                {/* Expanded Row Details */}
                {expandedRow === row.id && (
                  <tr key={`${row.id}-expanded`}>
                    <td colSpan={columns.length} className="bg-gray-50 p-4">
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <h4 className="mb-2 font-medium text-gray-700">
                              {t('evaluation.sampleResultsTable.groundTruth')}
                            </h4>
                            <pre className="max-h-40 overflow-auto rounded bg-white p-3 text-xs">
                              {JSON.stringify(
                                row.original.ground_truth,
                                null,
                                2
                              )}
                            </pre>
                          </div>
                          <div>
                            <h4 className="mb-2 font-medium text-gray-700">
                              {t('evaluation.sampleResultsTable.prediction')}
                            </h4>
                            <pre className="max-h-40 overflow-auto rounded bg-white p-3 text-xs">
                              {JSON.stringify(row.original.prediction, null, 2)}
                            </pre>
                          </div>
                        </div>

                        <div>
                          <h4 className="mb-2 font-medium text-gray-700">
                            {t('evaluation.sampleResultsTable.allMetrics')}
                          </h4>
                          <div className="grid grid-cols-3 gap-2 rounded bg-white p-3 md:grid-cols-4 lg:grid-cols-6">
                            {Object.entries(row.original.metrics).map(
                              ([key, value]) => (
                                <div key={key} className="text-sm">
                                  <div className="text-xs text-gray-600">
                                    {key}
                                  </div>
                                  <div className="font-medium">
                                    {value?.toFixed(3) ?? 'N/A'}
                                  </div>
                                </div>
                              )
                            )}
                          </div>
                        </div>

                        {row.original.error_message && (
                          <div>
                            <h4 className="mb-2 font-medium text-red-700">
                              {t('evaluation.sampleResultsTable.error')}
                            </h4>
                            <div className="rounded bg-red-50 p-3 text-sm text-red-800">
                              {row.original.error_message}
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600">
          {t('evaluation.sampleResultsTable.showing')}{' '}
          {table.getState().pagination.pageIndex *
            table.getState().pagination.pageSize +
            1}{' '}
          {t('evaluation.sampleResultsTable.to')}{' '}
          {Math.min(
            (table.getState().pagination.pageIndex + 1) *
              table.getState().pagination.pageSize,
            table.getFilteredRowModel().rows.length
          )}{' '}
          {t('evaluation.sampleResultsTable.of')} {table.getFilteredRowModel().rows.length} {t('evaluation.sampleResultsTable.results')}
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
