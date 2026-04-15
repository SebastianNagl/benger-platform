'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Pagination } from '@/components/shared/Pagination'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useProjects } from '@/hooks/useProjects'
import type {
  LLMLeaderboardEntry,
  LLMLeaderboardResponse,
} from '@/lib/api/leaderboards'
import { Listbox, Menu } from '@headlessui/react'
import { CheckIcon, ChevronDownIcon } from '@heroicons/react/20/solid'
import {
  ChartBarIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import { useCallback, useEffect, useState } from 'react'

type TimePeriod = 'overall' | 'monthly' | 'weekly'

const TIME_PERIOD_KEYS: { value: TimePeriod; key: string }[] = [
  { value: 'overall', key: 'leaderboards.allTime' },
  { value: 'monthly', key: 'leaderboards.thisMonth' },
  { value: 'weekly', key: 'leaderboards.thisWeek' },
]

const METRIC_KEYS = [
  { value: 'average', key: 'leaderboards.llm.metrics.average' },
  { value: 'accuracy', key: 'leaderboards.llm.metrics.accuracy' },
  { value: 'f1_score', key: 'leaderboards.llm.metrics.f1Score' },
  { value: 'raw_score', key: 'leaderboards.llm.metrics.rawScore' },
]

const providerColors: Record<string, string> = {
  openai: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  anthropic:
    'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  google: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  deepinfra:
    'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  meta: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300',
  mistral: 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-300',
  alibaba: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300',
  deepseek: 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-300',
  cohere: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
  other: 'bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-300',
  unknown: 'bg-zinc-100 text-zinc-800 dark:bg-zinc-900 dark:text-zinc-300',
}

export function LLMLeaderboardTable() {
  const { apiClient } = useAuth()
  const { t } = useI18n()
  const { projects, fetchProjects } = useProjects()
  const [loading, setLoading] = useState(true)
  const [leaderboard, setLeaderboard] = useState<LLMLeaderboardEntry[]>([])
  const [filteredLeaderboard, setFilteredLeaderboard] = useState<
    LLMLeaderboardEntry[]
  >([])
  const [availableMetrics, setAvailableMetrics] = useState<string[]>([])
  const [availableEvaluationTypes, setAvailableEvaluationTypes] = useState<
    string[]
  >([])
  const [period, setPeriod] = useState<TimePeriod>('overall')
  const [metric, setMetric] = useState('average')
  const [aggregation, setAggregation] = useState<'average' | 'sum'>('average')
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([])
  const [selectedEvaluationTypes, setSelectedEvaluationTypes] = useState<
    string[]
  >([])
  const [searchQuery, setSearchQuery] = useState('')
  const [showSearch, setShowSearch] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [totalItems, setTotalItems] = useState(0)

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const loadLeaderboard = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const offset = (currentPage - 1) * pageSize
      const response: LLMLeaderboardResponse =
        await apiClient.leaderboards.getLLMLeaderboard({
          period,
          metric,
          limit: pageSize,
          offset,
          project_ids:
            selectedProjectIds.length > 0 ? selectedProjectIds : undefined,
          evaluation_types:
            selectedEvaluationTypes.length > 0
              ? selectedEvaluationTypes
              : undefined,
          include_all_models: true,
          aggregation,
        })

      setLeaderboard(response.leaderboard)
      setFilteredLeaderboard(response.leaderboard)
      setAvailableMetrics(response.available_metrics)
      setAvailableEvaluationTypes(response.available_evaluation_types || [])
      setTotalItems(response.total_models)
    } catch (err: any) {
      console.error('Failed to load LLM leaderboard:', err)
      setError(err.message || t('leaderboards.llm.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [
    period,
    metric,
    aggregation,
    selectedProjectIds,
    selectedEvaluationTypes,
    apiClient.leaderboards,
    currentPage,
    pageSize,
  ])

  // Reset to page 1 when filters change
  useEffect(() => {
    setCurrentPage(1)
  }, [period, metric, aggregation, selectedProjectIds, selectedEvaluationTypes])

  useEffect(() => {
    loadLeaderboard()
  }, [loadLeaderboard])

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    setCurrentPage(1)
  }

  useEffect(() => {
    if (!searchQuery.trim()) {
      setFilteredLeaderboard(leaderboard)
      return
    }

    const query = searchQuery.toLowerCase()
    const filtered = leaderboard.filter(
      (entry) =>
        entry.model_name.toLowerCase().includes(query) ||
        entry.provider.toLowerCase().includes(query)
    )
    setFilteredLeaderboard(filtered)
  }, [searchQuery, leaderboard])

  const getMedalIcon = (rank: number) => {
    switch (rank) {
      case 1:
        return (
          <span className="text-2xl" title={t('leaderboards.llm.firstPlace')}>
            🥇
          </span>
        )
      case 2:
        return (
          <span className="text-2xl" title={t('leaderboards.llm.secondPlace')}>
            🥈
          </span>
        )
      case 3:
        return (
          <span className="text-2xl" title={t('leaderboards.llm.thirdPlace')}>
            🥉
          </span>
        )
      default:
        return (
          <span className="text-lg font-semibold text-zinc-500">{rank}</span>
        )
    }
  }

  const formatScore = (score: number | null) => {
    if (score === null || score === undefined) return 'n/a'
    if (aggregation === 'sum') {
      return score.toFixed(2)
    }
    return (score * 100).toFixed(1) + '%'
  }

  const formatCI = (ci_lower: number | null, ci_upper: number | null) => {
    if (ci_lower === null || ci_upper === null) return null
    return `${(ci_lower * 100).toFixed(1)}% - ${(ci_upper * 100).toFixed(1)}%`
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString()
  }

  const toggleProject = (projectId: string) => {
    setSelectedProjectIds((prev) =>
      prev.includes(projectId)
        ? prev.filter((id) => id !== projectId)
        : [...prev, projectId]
    )
  }

  // Get the score to display based on selected metric
  const getDisplayScore = (entry: LLMLeaderboardEntry): number | null => {
    if (metric === 'average') {
      return entry.average_score
    }
    return entry.metrics[metric] ?? null
  }

  // Get the column header label based on selected metric
  const getScoreColumnLabel = () => {
    if (metric === 'average') {
      return t('leaderboards.llm.scoreCi')
    }
    const metricKey = METRIC_KEYS.find((m) => m.value === metric)?.key
    return metricKey ? t(metricKey) : t('leaderboards.llm.score')
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-emerald-500 border-t-transparent"></div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-500">{error}</p>
        <Button onClick={loadLeaderboard} className="mt-4">
          {t('leaderboards.retry')}
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Time Period Filter */}
        <Listbox value={period} onChange={setPeriod}>
          <div className="relative">
            <Listbox.Button
              as={Button}
              variant="outline"
              className="w-36 justify-between gap-2"
            >
              <span className="truncate text-sm">
                {t(TIME_PERIOD_KEYS.find((o) => o.value === period)?.key || 'leaderboards.allTime')}
              </span>
              <ChevronDownIcon className="h-4 w-4" />
            </Listbox.Button>
            <Listbox.Options className="absolute left-0 z-10 mt-2 max-h-60 w-40 overflow-auto rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
              {TIME_PERIOD_KEYS.map((option) => (
                <Listbox.Option
                  key={option.value}
                  value={option.value}
                  className={({ active }) =>
                    `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                      active
                        ? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
                        : 'text-zinc-900 dark:text-zinc-100'
                    }`
                  }
                >
                  {({ selected }) => (
                    <>
                      <span
                        className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}
                      >
                        {t(option.key)}
                      </span>
                      {selected && (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-600">
                          <CheckIcon className="h-5 w-5" />
                        </span>
                      )}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </div>
        </Listbox>

        {/* Metric Filter */}
        <Listbox value={metric} onChange={setMetric}>
          <div className="relative">
            <Listbox.Button
              as={Button}
              variant="outline"
              className="w-48 justify-between gap-2"
            >
              <span className="truncate text-sm">
                {t(METRIC_KEYS.find((o) => o.value === metric)?.key || 'leaderboards.llm.selectMetric')}
              </span>
              <ChevronDownIcon className="h-4 w-4" />
            </Listbox.Button>
            <Listbox.Options className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
              {METRIC_KEYS.map((option) => (
                <Listbox.Option
                  key={option.value}
                  value={option.value}
                  className={({ active }) =>
                    `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                      active
                        ? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
                        : 'text-zinc-900 dark:text-zinc-100'
                    }`
                  }
                >
                  {({ selected }) => (
                    <>
                      <span
                        className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}
                      >
                        {t(option.key)}
                      </span>
                      {selected && (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-600">
                          <CheckIcon className="h-5 w-5" />
                        </span>
                      )}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </div>
        </Listbox>

        {/* Project Filter */}
        <Menu as="div" className="relative">
          <Menu.Button as={Button} variant="outline" className="gap-2">
            <FunnelIcon className="h-4 w-4" />
            <span>
              {selectedProjectIds.length > 0
                ? t('leaderboards.llm.projectsCount', { count: selectedProjectIds.length })
                : t('leaderboards.allProjects')}
            </span>
            {selectedProjectIds.length > 0 && (
              <span className="ml-1 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                {selectedProjectIds.length}
              </span>
            )}
            <ChevronDownIcon className="h-4 w-4" />
          </Menu.Button>
          <Menu.Items className="absolute right-0 z-10 mt-2 max-h-60 w-64 overflow-auto rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
            {projects.map((project) => (
              <Menu.Item key={project.id}>
                {({ active }) => (
                  <button
                    className={`flex w-full items-center px-4 py-2 text-left text-sm ${
                      active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                    }`}
                    onClick={() => toggleProject(project.id)}
                  >
                    <input
                      type="checkbox"
                      checked={selectedProjectIds.includes(project.id)}
                      onChange={() => {}}
                      className="mr-3 h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                    />
                    <span className="truncate text-zinc-900 dark:text-zinc-100">
                      {project.title}
                    </span>
                  </button>
                )}
              </Menu.Item>
            ))}
          </Menu.Items>
        </Menu>

        {/* Evaluation Types Filter */}
        {availableEvaluationTypes.length > 0 && (
          <Menu as="div" className="relative">
            <Menu.Button as={Button} variant="outline" className="gap-2">
              <ChartBarIcon className="h-4 w-4" />
              <span>
                {selectedEvaluationTypes.length > 0
                  ? t('leaderboards.llm.evalTypesCount', { count: selectedEvaluationTypes.length })
                  : t('leaderboards.llm.allEvalTypes')}
              </span>
              {selectedEvaluationTypes.length > 0 && (
                <span className="ml-1 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                  {selectedEvaluationTypes.length}
                </span>
              )}
              <ChevronDownIcon className="h-4 w-4" />
            </Menu.Button>
            <Menu.Items className="absolute right-0 z-10 mt-2 max-h-60 w-64 overflow-auto rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
              {availableEvaluationTypes.map((evalType) => (
                <Menu.Item key={evalType}>
                  {({ active }) => (
                    <button
                      className={`flex w-full items-center px-4 py-2 text-left text-sm ${
                        active ? 'bg-zinc-100 dark:bg-zinc-800' : ''
                      }`}
                      onClick={() =>
                        setSelectedEvaluationTypes((prev) =>
                          prev.includes(evalType)
                            ? prev.filter((t) => t !== evalType)
                            : [...prev, evalType]
                        )
                      }
                    >
                      <input
                        type="checkbox"
                        checked={selectedEvaluationTypes.includes(evalType)}
                        onChange={() => {}}
                        className="mr-3 h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
                      />
                      <span className="truncate text-zinc-900 dark:text-zinc-100">
                        {evalType}
                      </span>
                    </button>
                  )}
                </Menu.Item>
              ))}
            </Menu.Items>
          </Menu>
        )}

        {/* Aggregation Mode */}
        <Listbox value={aggregation} onChange={setAggregation}>
          <div className="relative">
            <Listbox.Button
              as={Button}
              variant="outline"
              className="w-36 justify-between gap-2"
            >
              <span className="truncate text-sm">
                {t(`leaderboards.aggregation.${aggregation}`)}
              </span>
              <ChevronDownIcon className="h-4 w-4" />
            </Listbox.Button>
            <Listbox.Options className="absolute z-10 mt-2 max-h-60 w-40 overflow-auto rounded-lg bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none dark:bg-zinc-900">
              {(['average', 'sum'] as const).map((mode) => (
                <Listbox.Option
                  key={mode}
                  value={mode}
                  className={({ active }) =>
                    `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                      active
                        ? 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100'
                        : 'text-zinc-900 dark:text-zinc-100'
                    }`
                  }
                >
                  {({ selected }) => (
                    <>
                      <span
                        className={`block truncate ${selected ? 'font-medium' : 'font-normal'}`}
                      >
                        {t(`leaderboards.aggregation.${mode}`)}
                      </span>
                      {selected && (
                        <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-emerald-600">
                          <CheckIcon className="h-5 w-5" />
                        </span>
                      )}
                    </>
                  )}
                </Listbox.Option>
              ))}
            </Listbox.Options>
          </div>
        </Listbox>

        {/* Search Toggle */}
        <Button
          variant="outline"
          onClick={() => setShowSearch(!showSearch)}
          className={`ml-auto ${showSearch ? 'bg-emerald-50 dark:bg-emerald-900/20' : ''}`}
        >
          <MagnifyingGlassIcon className="h-4 w-4" />
        </Button>
      </div>

      {/* Search Input */}
      {showSearch && (
        <Input
          type="text"
          placeholder={t('leaderboards.llm.searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="max-w-xs"
        />
      )}

      {/* Leaderboard Table */}
      {filteredLeaderboard.length === 0 ? (
        <div className="py-12 text-center">
          <ChartBarIcon className="mx-auto h-12 w-12 text-zinc-400" />
          <h3 className="mt-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
            {t('leaderboards.llm.noDataTitle')}
          </h3>
          <p className="mt-1 text-sm text-zinc-500">
            {t('leaderboards.llm.noDataDescription')}
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-700">
          <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-700">
            <thead className="bg-zinc-50 dark:bg-zinc-800">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.rank')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.llm.model')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.llm.provider')}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {getScoreColumnLabel()}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.llm.evaluations')}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.llm.samples')}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.llm.lastEvaluated')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
              {filteredLeaderboard.map((entry) => {
                const displayScore = getDisplayScore(entry)
                const hasScore = displayScore !== null && displayScore !== undefined
                return (
                  <tr
                    key={entry.model_id}
                    className={
                      hasScore
                        ? 'hover:bg-zinc-50 dark:hover:bg-zinc-800/50'
                        : 'bg-zinc-50/50 dark:bg-zinc-800/30'
                    }
                  >
                    <td className="whitespace-nowrap px-4 py-4 text-sm font-medium">
                      {hasScore ? (
                        getMedalIcon(entry.rank)
                      ) : (
                        <span className="text-zinc-400 dark:text-zinc-500">
                          {entry.rank}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-4 text-sm">
                      <div
                        className={
                          hasScore
                            ? 'font-medium text-zinc-900 dark:text-white'
                            : 'font-medium text-zinc-500 dark:text-zinc-400'
                        }
                      >
                        {entry.model_name}
                      </div>
                      <div className="text-xs text-zinc-500">
                        {entry.model_id}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-sm">
                      <Badge
                        className={
                          providerColors[entry.provider.toLowerCase()] ||
                          providerColors.unknown
                        }
                      >
                        {entry.provider}
                      </Badge>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-right text-sm">
                      {hasScore ? (
                        <span className="font-semibold text-zinc-900 dark:text-white">
                          {formatScore(displayScore)}
                        </span>
                      ) : (
                        <span className="text-zinc-400 dark:text-zinc-500">n/a</span>
                      )}
                      {/* Only show CI for average score in average mode */}
                      {metric === 'average' &&
                        aggregation !== 'sum' &&
                        formatCI(entry.ci_lower, entry.ci_upper) && (
                          <div
                            className="text-xs text-zinc-500"
                            title={t('leaderboards.llm.confidenceInterval')}
                          >
                            [{formatCI(entry.ci_lower, entry.ci_upper)}]
                          </div>
                        )}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-zinc-500">
                      {entry.evaluation_count}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-zinc-500">
                      {entry.samples_evaluated.toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-zinc-500">
                      {formatDate(entry.last_evaluated)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalItems > 0 && (
        <Pagination
          currentPage={currentPage}
          totalPages={Math.ceil(totalItems / pageSize)}
          totalItems={totalItems}
          pageSize={pageSize}
          onPageChange={setCurrentPage}
          onPageSizeChange={handlePageSizeChange}
          pageSizeOptions={[25, 50, 100]}
        />
      )}

      {/* Available Metrics */}
      {availableMetrics.length > 0 && (
        <div className="mt-4 text-sm text-zinc-500">
          <span className="font-medium">{t('leaderboards.llm.availableMetrics')}:</span>{' '}
          {availableMetrics.slice(0, 10).join(', ')}
          {availableMetrics.length > 10 &&
            ` ${t('leaderboards.llm.andMore', { count: availableMetrics.length - 10 })}`}
        </div>
      )}
    </div>
  )
}
