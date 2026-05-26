'use client'

import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { FilterToolbar } from '@/components/shared/FilterToolbar'
import { Pagination } from '@/components/shared/Pagination'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useAuth } from '@/contexts/AuthContext'
import { useI18n } from '@/contexts/I18nContext'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useProjects } from '@/hooks/useProjects'
import {
  AvailableMetric,
  getMetricDefinitions,
  getMetricScale,
  getMetricSummable,
  type MetricDisplayScale,
} from '@/lib/api/evaluation-types'
import type { LLMLeaderboardEntry } from '@/lib/api/leaderboards'
import { Menu } from '@headlessui/react'
import { CheckIcon, ChevronDownIcon } from '@heroicons/react/20/solid'
import {
  ChartBarIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'

type TimePeriod = 'overall' | 'monthly' | 'weekly'

type TFn = (key: string, vars?: Record<string, unknown>) => string

const TIME_PERIOD_KEYS: { value: TimePeriod; key: string }[] = [
  { value: 'overall', key: 'leaderboards.allTime' },
  { value: 'monthly', key: 'leaderboards.thisMonth' },
  { value: 'weekly', key: 'leaderboards.thisWeek' },
]

// Always-shown ranking metrics. Extended on each render with whatever the
// backend reports in `available_metrics` for the current project, intersected
// with the metric registry so junk keys like *_response / *_passed never
// appear in the dropdown. Notenpunkte sits in this list because it's the
// default ranking metric in prod (German legal grading) — mirrors the human
// and co-creation leaderboards which also default to grade points.
//
// `average` used to live here as a cross-metric mean, but pooling values
// from incompatible scales (0–1 bleu, 0–18 Notenpunkte, 0–100 korrektur)
// produced dimensionally meaningless arithmetic means that the formatter
// then rendered as "1400%". PR #116 removed the synthetic row from the
// aggregator and the option from this list. Pick a concrete metric instead.
const CORE_METRICS = [
  'llm_judge_falloesung_grade_points',
  'accuracy',
] as const

function camelize(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())
}

// Label resolution: i18n key first (preserves existing translations for the
// core 4), then registry display_name (covers extended metrics that ship
// their own German/English labels), then the raw key as a defensive last
// resort. The I18nContext's `t()` returns the key unchanged when no
// translation is found, which is how we detect the miss.
function getMetricLabel(
  metricKey: string,
  t: TFn,
  defs: Record<string, AvailableMetric>,
): string {
  const i18nKey = `leaderboards.llm.metrics.${camelize(metricKey)}`
  const translated = t(i18nKey)
  if (translated && translated !== i18nKey) return translated
  return defs[metricKey]?.display_name ?? metricKey
}

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
  const [period, setPeriod] = useState<TimePeriod>('overall')
  // Default to Notenpunkte (Falllösung) so the LLM leaderboard opens on the
  // same scoring axis as the human + co-creation leaderboards. Models
  // without judge results just show n/a and sort to the bottom.
  const [metric, setMetric] = useState('llm_judge_falloesung_grade_points')
  const [aggregation, setAggregation] = useState<'average' | 'sum'>('average')
  const [selectedProjectIds, setSelectedProjectIds] = useState<string[]>([])
  const [selectedEvaluationTypes, setSelectedEvaluationTypes] = useState<
    string[]
  >([])
  const [searchQuery, setSearchQuery] = useState('')
  // Server-side search: the debounced term is forwarded as `?search=` so
  // pagination total reflects the filter across all pages (previously the
  // search ran client-side over the loaded page only and pagination lied).
  const debouncedSearchQuery = useDebouncedValue(searchQuery, 250)
  // Default off — including catalog models with zero evaluations padded the
  // leaderboard with 67 n/a rows on prod (16 with data, 83 total). Opt in
  // via the filter panel when you want to see catalog-vs-evaluated coverage.
  // Mutually exclusive with the min-samples threshold below: padding rows
  // have 0 gens / 0 samples so they never pass any positive threshold.
  const [includeAllModels, setIncludeAllModels] = useState(false)
  // Default on — drops low-sample models from the ranking so the leaderboard
  // doesn't surface noisy single-digit-gen models alongside well-evaluated
  // ones. Threshold values match the API defaults; opting out sends 0.
  const [minSamplesEnabled, setMinSamplesEnabled] = useState(true)
  const MIN_GENERATIONS_THRESHOLD = 50
  const MIN_SAMPLES_THRESHOLD = 50
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  // Server state via TanStack Query: caches per (filter, page) tuple,
  // dedupes overlapping mounts, keeps the previous page visible during
  // refetches so filter tweaks feel snappy instead of blanking the table.
  // Stale time of 30s matches the typical gap between recompute_aggregates
  // beats (event-driven + hourly cron); shorter and we'd burn requests on
  // every navigation, longer and a freshly-finalised eval wouldn't show up
  // when the user opens the leaderboard right after triggering it.
  const trimmedSearch = debouncedSearchQuery.trim()
  const leaderboardQuery = useQuery({
    queryKey: [
      'leaderboards',
      'llm',
      {
        period,
        metric,
        aggregation,
        currentPage,
        pageSize,
        selectedProjectIds,
        selectedEvaluationTypes,
        search: trimmedSearch,
        includeAllModels,
        minSamplesEnabled,
      },
    ],
    queryFn: () => {
      const offset = (currentPage - 1) * pageSize
      return apiClient.leaderboards.getLLMLeaderboard({
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
        include_all_models: includeAllModels,
        aggregation,
        search: trimmedSearch ? trimmedSearch : undefined,
        min_generation_count: minSamplesEnabled ? MIN_GENERATIONS_THRESHOLD : 0,
        min_samples_evaluated: minSamplesEnabled ? MIN_SAMPLES_THRESHOLD : 0,
      })
    },
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  const leaderboard = leaderboardQuery.data?.leaderboard ?? []
  const availableMetrics = leaderboardQuery.data?.available_metrics ?? []
  const availableEvaluationTypes =
    leaderboardQuery.data?.available_evaluation_types ?? []
  const totalItems = leaderboardQuery.data?.total_models ?? 0
  // `isPending` is only true on the very first fetch (no cache, no
  // placeholder); subsequent filter-driven refetches keep the previous
  // data visible so the table doesn't flash. `isFetching` would also flip
  // for background refetches but we intentionally don't render a global
  // spinner for those.
  const loading = leaderboardQuery.isPending
  const error = leaderboardQuery.error
    ? (leaderboardQuery.error as Error).message || t('leaderboards.llm.loadFailed')
    : null

  // Reset to page 1 when filters change. We can't put this inside the
  // query callback (pre-react-query the state-driven refetch handled it);
  // an explicit effect keeps it decoupled and matches the existing pattern.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCurrentPage(1)
  }, [
    period,
    metric,
    aggregation,
    selectedProjectIds,
    selectedEvaluationTypes,
    debouncedSearchQuery,
    includeAllModels,
    minSamplesEnabled,
  ])

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    setCurrentPage(1)
  }

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

  // Scale-aware formatter. The metric registry is the single source of
  // truth: a metric declared `display_scale: '0-1'` displays as a percent
  // (×100), `'0-100'` displays as-is, `'0-18'` as Notenpunkte, `'raw'`
  // unitless. Unknown keys default to `'0-1'` for backwards compatibility
  // with the historical formatter behaviour. This unifies what used to be
  // a hand-maintained `NATIVELY_PERCENT_METRICS` allowlist plus a
  // `endsWith('grade_points')` special case.
  const formatValueForScale = (value: number, scale: MetricDisplayScale, sum: boolean): string => {
    if (scale === '0-18') {
      return sum ? `${value.toFixed(1)} NP` : `${value.toFixed(1)} / 18 NP`
    }
    if (sum) {
      // Sums of percentage-shaped metrics aren't dimensionally meaningful
      // (sum of 100 bleu scores at 0.05 = 5, "5%" reads as 5/100 not 5
      // bleu-units). Render as a raw number with no unit suffix and let
      // the user infer.
      return value.toFixed(2)
    }
    if (scale === '0-100') return `${value.toFixed(1)}%`
    if (scale === '0-1') return `${(value * 100).toFixed(1)}%`
    return value.toFixed(2) // raw
  }

  const formatScore = (score: number | null) => {
    if (score === null || score === undefined) return 'n/a'
    return formatValueForScale(score, getMetricScale(metric), aggregation === 'sum')
  }

  const formatCI = (ci_lower: number | null, ci_upper: number | null) => {
    if (ci_lower === null || ci_upper === null) return null
    const scale = getMetricScale(metric)
    // CI on a sum is set to null by the aggregator, so we shouldn't get
    // here in that case; defensive `sum=false` keeps the format consistent
    // with the metric's natural scale if a caller does pass it.
    const fmt = (v: number) => formatValueForScale(v, scale, false)
    return `${fmt(ci_lower)} – ${fmt(ci_upper)}`
  }

  // Sum aggregation is only meaningful for metrics whose registry entry
  // declares `summable: true` (Notenpunkte, exact_match, accuracy as
  // count-correct). For ratios like BLEU summing across N evaluations
  // produces a dimensionally weird number; we gate the toggle.
  const currentMetricSummable = getMetricSummable(metric)

  const toggleProject = (projectId: string) => {
    setSelectedProjectIds((prev) =>
      prev.includes(projectId)
        ? prev.filter((id) => id !== projectId)
        : [...prev, projectId]
    )
  }

  // Get the score to display based on selected metric. The synthetic
  // 'average' metric is gone (PR #116); read the per-metric value directly.
  const getDisplayScore = (entry: LLMLeaderboardEntry): number | null => {
    return entry.metrics[metric] ?? null
  }

  // Dropdown options: the core ranking metrics (always visible) plus any
  // additional registered metric reported by the backend for this project
  // (so e.g. korrektur_falloesung shows up automatically when present).
  const metricOptions = useMemo(() => {
    const defs = getMetricDefinitions()
    const core = CORE_METRICS.map((value) => ({
      value,
      label: getMetricLabel(value, t, defs),
    }))
    const seen = new Set<string>(CORE_METRICS)
    const extra = (availableMetrics ?? [])
      .filter((m) => !seen.has(m) && defs[m])
      .map((m) => ({ value: m, label: getMetricLabel(m, t, defs) }))
    return [...core, ...extra]
  }, [availableMetrics, t])

  // If the selected metric is no longer in the option list (e.g. the user
  // switched filters and the data dropped it), fall back to the first
  // available option. The historical fallback was 'average' but that
  // metric was removed in PR #116; default to Notenpunkte (the leaderboard's
  // landing metric) if it's still on offer, otherwise the first option.
  useEffect(() => {
    if (metricOptions.length === 0) return
    if (!metricOptions.some((o) => o.value === metric)) {
      const fallback =
        metricOptions.find((o) => o.value === 'llm_judge_falloesung_grade_points') ??
        metricOptions[0]
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMetric(fallback.value)
    }
  }, [metricOptions, metric])

  // If the user has Sum selected and switches to a non-summable metric,
  // snap back to Average so the displayed numbers don't become nonsense
  // (the API would reject sum-on-non-summable; this prevents the round-trip).
  useEffect(() => {
    if (aggregation === 'sum' && !currentMetricSummable) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setAggregation('average')
    }
  }, [aggregation, currentMetricSummable])

  // Get the column header label based on selected metric.
  const getScoreColumnLabel = () => {
    const opt = metricOptions.find((m) => m.value === metric)
    return opt?.label ?? t('leaderboards.llm.score')
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
        <Button onClick={() => leaderboardQuery.refetch()} className="mt-4">
          {t('leaderboards.retry')}
        </Button>
      </div>
    )
  }

  const projectsMenu = (
    <>
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
    </>
  )

  return (
    <div className="space-y-4">
      <FilterToolbar
        variant="bare"
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t('leaderboards.llm.searchPlaceholder')}
        searchLabel={t('common.filters.search')}
        filtersLabel={t('common.filters.filters')}
        hasActiveFilters={
          period !== 'overall' ||
          aggregation !== 'average' ||
          selectedProjectIds.length > 0 ||
          selectedEvaluationTypes.length > 0 ||
          searchQuery.trim() !== '' ||
          includeAllModels ||
          !minSamplesEnabled
        }
        onClearFilters={() => {
          setPeriod('overall')
          setAggregation('average')
          setSelectedProjectIds([])
          setSelectedEvaluationTypes([])
          setSearchQuery('')
          setIncludeAllModels(false)
          setMinSamplesEnabled(true)
        }}
        clearLabel={t('common.filters.clearAll')}
        leftExtras={projectsMenu}
      >
        <FilterToolbar.Field label={t('leaderboards.allTime')}>
          <Select value={period} onValueChange={(v) => setPeriod(v as TimePeriod)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIME_PERIOD_KEYS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(option.key)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('leaderboards.llm.selectMetric')}>
          <Select value={metric} onValueChange={setMetric}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {metricOptions.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('leaderboards.aggregation.average')}>
          <Select
            value={aggregation}
            onValueChange={(v) => setAggregation(v as 'average' | 'sum')}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="average">{t('leaderboards.aggregation.average')}</SelectItem>
              {/* Sum is only meaningful for summable metrics (Notenpunkte,
                  exact_match, accuracy as count-correct). For ratios like
                  BLEU/ROUGE summing across N evals is dimensionally weird;
                  hide the option when the current metric isn't summable. */}
              {currentMetricSummable && (
                <SelectItem value="sum">{t('leaderboards.aggregation.sum')}</SelectItem>
              )}
            </SelectContent>
          </Select>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('leaderboards.llm.includeAllModels')}>
          {/* Catalog padding + the min-samples threshold are semantically
              opposite: padding rows have 0 generations and 0 samples, so
              the threshold would filter them all out the moment they're
              added. Disable the checkbox while the threshold is on so the
              user sees the dependency rather than toggling and getting
              the same 12 rows back. */}
          <label
            className={
              minSamplesEnabled
                ? 'inline-flex cursor-not-allowed items-center gap-2 text-sm text-zinc-400 dark:text-zinc-500'
                : 'inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300'
            }
            title={
              minSamplesEnabled
                ? t('leaderboards.llm.includeAllModelsDisabledHint')
                : undefined
            }
          >
            <input
              type="checkbox"
              checked={includeAllModels && !minSamplesEnabled}
              disabled={minSamplesEnabled}
              onChange={(e) => setIncludeAllModels(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            />
            <span>{t('leaderboards.llm.includeAllModelsLabel')}</span>
          </label>
        </FilterToolbar.Field>

        <FilterToolbar.Field label={t('leaderboards.llm.minSamples')}>
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <input
              type="checkbox"
              checked={minSamplesEnabled}
              onChange={(e) => setMinSamplesEnabled(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
            />
            <span>
              {t('leaderboards.llm.minSamplesLabel', {
                gens: MIN_GENERATIONS_THRESHOLD,
                samples: MIN_SAMPLES_THRESHOLD,
              })}
            </span>
          </label>
        </FilterToolbar.Field>
      </FilterToolbar>

      {/* Leaderboard Table */}
      {leaderboard.length === 0 ? (
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
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {t('leaderboards.llm.generations', 'Generations')}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                  {getScoreColumnLabel()}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 bg-white dark:divide-zinc-700 dark:bg-zinc-900">
              {leaderboard.map((entry) => {
                const displayScore = getDisplayScore(entry)
                const hasScore = displayScore !== null && displayScore !== undefined
                // CI is meaningful for any per-metric mean; aggregator sets
                // ci_lower/ci_upper=null in sum mode so we just check
                // presence here instead of gating on metric/aggregation.
                const ciText =
                  aggregation === 'sum'
                    ? null
                    : formatCI(entry.ci_lower, entry.ci_upper)
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
                      <div className="flex items-center gap-2">
                        <span
                          className={
                            hasScore
                              ? 'font-medium text-zinc-900 dark:text-white'
                              : 'font-medium text-zinc-500 dark:text-zinc-400'
                          }
                        >
                          {entry.model_name}
                        </span>
                        <Badge
                          className={
                            providerColors[entry.provider.toLowerCase()] ||
                            providerColors.unknown
                          }
                        >
                          {entry.provider}
                        </Badge>
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-right text-sm text-zinc-500">
                      {(entry.generation_count ?? 0).toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 text-right text-sm">
                      {hasScore ? (
                        <span className="font-semibold text-zinc-900 dark:text-white">
                          {formatScore(displayScore)}
                        </span>
                      ) : (
                        <span className="text-zinc-400 dark:text-zinc-500">n/a</span>
                      )}
                      {hasScore && ciText && (
                        <div
                          className="text-xs text-zinc-500"
                          title={t('leaderboards.llm.confidenceInterval')}
                        >
                          [{ciText}]
                        </div>
                      )}
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
