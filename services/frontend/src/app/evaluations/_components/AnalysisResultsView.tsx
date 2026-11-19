'use client'

/**
 * The Analyses result type of the evaluations page: the analysis runs of one
 * project (variant experiments) with run, systems, estimands and family
 * filters, a strip of the selected run's facts, the forest (Bradley-Terry
 * estimands as strength forests), profile, bar or table view of its
 * estimates, the estimates table, the statistics panel (inference and fit
 * blocks), the examples of a contrast (units of the run's variant design in
 * the unit viewer) and, while the compliance overlay is active, its
 * findings for the run. Editors start a run from a spec in a dialog.
 *
 * URL state (`/evaluations?projectId=…&type=analysis`): `run`, `chartType`
 * (default `forest`; also `profile`, `bar`, `table` and `data`), `systems`,
 * `estimands` (comma separated), `family`, and `newRunFrom` (opens the
 * start dialog prefilled with that run's spec).
 * Every number is a stored estimate of the run; nothing is recomputed.
 */

import { EstimateProfiles } from '@/components/analysis/EstimateProfiles'
import { EstimatesForest } from '@/components/analysis/EstimatesForest'
import { EstimatesTable } from '@/components/analysis/EstimatesTable'
import { ExamplesPanel } from '@/components/analysis/ExamplesPanel'
import { StartAnalysisDialog } from '@/components/analysis/StartAnalysisDialog'
import { ComplianceInlineSlot } from '@/components/compliance/ComplianceSlot'
import {
  ChartTypeSelector,
  type ChartType,
} from '@/components/evaluation/ChartTypeSelector'
import { DynamicChartRenderer } from '@/components/evaluation/DynamicChartRenderer'
import { StatisticalResultsPanel } from '@/components/evaluation/StatisticalResultsPanel'
import { Button } from '@/components/shared/Button'
import { Card } from '@/components/shared/Card'
import { RunStatusBadge } from '@/components/shared/RunStatusBadge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import { specDesigns } from '@/lib/analysis/profile'
import { familiesOf, MISSING, shortHash } from '@/lib/analysis/results'
import {
  analysisAPI,
  isRunActive,
  statusOf,
  type AnalysisEstimate,
  type AnalysisRun,
  type AnalysisRunSummary,
} from '@/lib/api/analysis'
import {
  estimandsOf,
  filterEstimates,
  intervalRowsFromEstimates,
  isJointTest,
  systemsOf,
} from '@/lib/results/intervalRows'
import { analysisRunPath, evaluationsPath } from '@/lib/results/paths'
import type { Project } from '@/types/labelStudio'
import {
  BeakerIcon,
  ChevronDownIcon,
  PlusIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useRouter } from 'next/navigation'
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { InitialParams } from './MetricResultsView'

/** Chart types of the Analyses result type. */
export const ANALYSIS_CHART_TYPES: ChartType[] = [
  'data',
  'forest',
  'profile',
  'bar',
  'table',
]
export const DEFAULT_ANALYSIS_CHART: ChartType = 'forest'

/** Refresh interval of the run list while a run is pending or running. */
const LIST_POLL_MS = 4000
/** Refresh interval of the selected run while it is pending or running. */
const RUN_POLL_MS = 3000
/** Runs in the run filter (the newest; older ones open by URL). */
const RUN_PAGE_SIZE = 50

/** Family filter value for "every family". */
const ALL_FAMILIES = '__all__'

const list = (value: string | null | undefined): string[] | null => {
  const items = value?.split(',').filter(Boolean) ?? []
  return items.length > 0 ? items : null
}

/** The run the filter shows first: the newest completed, else the newest. */
export function defaultRunId(
  runs: readonly AnalysisRunSummary[],
): string | null {
  return (runs.find((r) => r.status === 'completed') ?? runs[0])?.id ?? null
}

/** The analysis URL of the evaluations page for a view state. */
export function analysisViewUrl(state: {
  projectId: string
  run: string | null
  chartType: ChartType
  systems: readonly string[] | null
  estimands: readonly string[] | null
  family: string | null
}): string {
  const params = new URLSearchParams(
    evaluationsPath({
      projectId: state.projectId,
      type: 'analysis',
      run: state.run,
    }).split('?')[1],
  )
  if (state.chartType !== DEFAULT_ANALYSIS_CHART) {
    params.set('chartType', state.chartType)
  }
  if (state.systems) params.set('systems', state.systems.join(','))
  if (state.estimands) params.set('estimands', state.estimands.join(','))
  if (state.family) params.set('family', state.family)
  return `/evaluations?${params.toString()}`
}

/** A checkbox dropdown of the filter bar (null selection: all). */
function CheckboxDropdown({
  label,
  options,
  selected,
  onChange,
  testId,
}: {
  label: string
  options: readonly string[]
  selected: readonly string[] | null
  onChange: (next: string[] | null) => void
  testId: string
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const handle = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])
  const isOn = (value: string) => selected === null || selected.includes(value)
  const toggle = (value: string) => {
    const current = selected ?? [...options]
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value]
    onChange(next.length === options.length ? null : next)
  }
  const summary =
    selected === null
      ? t('evaluation.viewer.filters.allModels')
      : `${selected.length} ${t('evaluation.viewer.filters.selected')}`
  return (
    <div className="relative" ref={ref}>
      <span className="mb-1 block text-xs font-medium text-zinc-500">
        {label}
      </span>
      <Button
        variant="outline"
        onClick={() => setOpen(!open)}
        className="w-36 justify-between"
        aria-label={`${label}: ${summary}`}
        aria-expanded={open}
        data-testid={testId}
      >
        <span className="truncate">{summary}</span>
        <ChevronDownIcon
          className={`ml-2 h-4 w-4 opacity-70 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </Button>
      {open && (
        <div
          className="absolute z-50 mt-1 max-h-60 w-64 max-w-[calc(100vw-2rem)] overflow-auto rounded-lg border border-zinc-200 bg-white p-2 shadow-lg dark:border-zinc-700 dark:bg-zinc-800"
          data-testid={`${testId}-panel`}
        >
          <button
            type="button"
            onClick={() => onChange(null)}
            className="mb-1 w-full px-2 py-1 text-left text-xs text-emerald-600 hover:text-emerald-700 dark:text-emerald-400"
          >
            {t('evaluation.viewer.filters.selectAll')}
          </button>
          <button
            type="button"
            onClick={() => onChange([])}
            className="mb-2 w-full px-2 py-1 text-left text-xs text-zinc-500 hover:text-zinc-700 dark:text-zinc-400"
          >
            {t('evaluation.viewer.filters.clearAll')}
          </button>
          {options.map((value) => (
            <label
              key={value}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-700"
            >
              <input
                type="checkbox"
                checked={isOn(value)}
                onChange={() => toggle(value)}
                className="rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500"
              />
              <span className="flex-1 truncate text-sm text-zinc-900 dark:text-zinc-100">
                {value}
              </span>
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="truncate font-mono text-sm text-zinc-900 dark:text-zinc-100">
        {children}
      </dd>
    </div>
  )
}

export interface AnalysisResultsViewProps {
  project: Project
  /** Leading filter-bar controls of the shell (project picker, result type). */
  filterBarLead: ReactNode
  /** URL parameters to restore the view from, read once on mount. */
  initialParams: InitialParams | null
  /** Whether the viewer may start runs (superadmin or the project's can_edit). */
  canStart: boolean
}

type RunState =
  | { kind: 'none' }
  | { kind: 'loading' }
  | { kind: 'notFound' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; run: AnalysisRun }

export function AnalysisResultsView({
  project,
  filterBarLead,
  initialParams,
  canStart,
}: AnalysisResultsViewProps) {
  const { t } = useI18n()
  const router = useRouter()
  const projectId = project.id.toString()

  const initial = useMemo(() => {
    const chart = initialParams?.get('chartType') as ChartType | null
    return {
      run: initialParams?.get('run') || null,
      chartType:
        chart && ANALYSIS_CHART_TYPES.includes(chart)
          ? chart
          : DEFAULT_ANALYSIS_CHART,
      systems: list(initialParams?.get('systems')),
      estimands: list(initialParams?.get('estimands')),
      family: initialParams?.get('family') || null,
      newRunFrom: initialParams?.get('newRunFrom') || null,
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally parse the URL once on mount; the view writes it back.
  }, [])

  const [runs, setRuns] = useState<AnalysisRunSummary[] | null>(null)
  const [total, setTotal] = useState(0)
  const [listError, setListError] = useState<string | null>(null)
  const [failedRefreshes, setFailedRefreshes] = useState(0)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(initial.run)
  const [runState, setRunState] = useState<RunState>({ kind: 'none' })
  const [failedPolls, setFailedPolls] = useState(0)
  const [estimates, setEstimates] = useState<AnalysisEstimate[] | null>(null)
  const [estimatesError, setEstimatesError] = useState<string | null>(null)
  const [systems, setSystems] = useState<string[] | null>(initial.systems)
  const [estimands, setEstimands] = useState<string[] | null>(initial.estimands)
  const [family, setFamily] = useState<string | null>(initial.family)
  const [chartType, setChartType] = useState<ChartType>(initial.chartType)
  const [startOpen, setStartOpen] = useState(
    Boolean(initial.newRunFrom) && canStart,
  )
  const [fromRunId, setFromRunId] = useState<string | null>(initial.newRunFrom)

  const loadRuns = useCallback(
    async (isRefresh = false) => {
      try {
        const page = await analysisAPI.listRuns(projectId, RUN_PAGE_SIZE)
        const items = page?.items ?? []
        setRuns(items)
        setTotal(page?.total ?? items.length)
        setListError(null)
        setSelectedRunId((current) => current ?? defaultRunId(items))
      } catch (error) {
        if (isRefresh) {
          setFailedRefreshes((n) => n + 1)
          return
        }
        setRuns([])
        setListError(
          statusOf(error) === 404 || statusOf(error) === 403
            ? 'forbidden'
            : 'failed',
        )
      }
    },
    [projectId],
  )

  useEffect(() => {
    void loadRuns()
  }, [loadRuns])

  // Refresh the list while one of its runs is still pending or running.
  const anyActive = runs?.some((r) => isRunActive(r.status)) ?? false
  useEffect(() => {
    if (!anyActive) return
    const timer = window.setTimeout(() => void loadRuns(true), LIST_POLL_MS)
    return () => window.clearTimeout(timer)
  }, [anyActive, runs, failedRefreshes, loadRuns])

  const selectedRunRef = useRef<string | null>(selectedRunId)
  const loadRun = useCallback(
    async (runId: string, isPoll = false) => {
      try {
        const run = await analysisAPI.getRun(runId)
        if (selectedRunRef.current !== runId) return
        if (run.project_id !== projectId) {
          setRunState({ kind: 'notFound' })
          return
        }
        setRunState({ kind: 'ready', run })
      } catch (error) {
        if (selectedRunRef.current !== runId) return
        if (isPoll && statusOf(error) !== 404) {
          setFailedPolls((n) => n + 1)
          return
        }
        setRunState(
          statusOf(error) === 404
            ? { kind: 'notFound' }
            : {
                kind: 'error',
                message:
                  (error as Error)?.message || t('analysis.run.loadFailed'),
              },
        )
      }
    },
    // t is stable per locale; a locale switch need not reload the run.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [projectId],
  )

  // The selected run, fresh on every selection.
  useEffect(() => {
    selectedRunRef.current = selectedRunId
    setEstimates(null)
    setEstimatesError(null)
    if (!selectedRunId) {
      setRunState({ kind: 'none' })
      return
    }
    setRunState({ kind: 'loading' })
    void loadRun(selectedRunId)
  }, [selectedRunId, loadRun])

  const run = runState.kind === 'ready' ? runState.run : null
  const status = run?.status

  // Poll the selected run while it can still change.
  useEffect(() => {
    if (!run || !isRunActive(run.status)) return
    const timer = window.setTimeout(
      () => void loadRun(run.id, true),
      RUN_POLL_MS,
    )
    return () => window.clearTimeout(timer)
  }, [run, failedPolls, loadRun])

  // Estimates once the run has completed (failed runs have none).
  const runId = run?.id
  useEffect(() => {
    if (status !== 'completed' || !runId) return
    let cancelled = false
    analysisAPI
      .listEstimates(runId)
      .then((items) => {
        if (!cancelled) setEstimates(items)
      })
      .catch((error) => {
        if (!cancelled)
          setEstimatesError(
            (error as Error)?.message || t('analysis.estimates.loadFailed'),
          )
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, runId])

  const systemOptions = useMemo(() => systemsOf(estimates ?? []), [estimates])
  const estimandOptions = useMemo(
    () => estimandsOf(estimates ?? []),
    [estimates],
  )
  const familyOptions = useMemo(() => familiesOf(estimates ?? []), [estimates])

  // Keep the filters to values the run has (a URL or an earlier run may name
  // others); a filter left with nothing falls back to all.
  useEffect(() => {
    if (!estimates) return
    const prune = (selected: string[] | null, options: string[]) => {
      if (selected === null) return null
      const kept = selected.filter((v) => options.includes(v))
      return kept.length > 0 || selected.length === 0 ? kept : null
    }
    setSystems((s) => prune(s, systemOptions))
    setEstimands((s) => prune(s, estimandOptions))
    setFamily((f) => (f && familyOptions.includes(f) ? f : null))
  }, [estimates, systemOptions, estimandOptions, familyOptions])

  const filtered = useMemo(
    () =>
      estimates
        ? filterEstimates(estimates, { systems, estimands, family })
        : [],
    [estimates, systems, estimands, family],
  )
  const pooledLabel = t('analysis.scope.pooled')
  const intervalRows = useMemo(
    () => intervalRowsFromEstimates(filtered, { pooledLabel }),
    [filtered, pooledLabel],
  )
  const plotted = useMemo(
    () => filtered.filter((e) => !isJointTest(e)),
    [filtered],
  )

  // Write the view state back to the URL once the runs are known.
  const runsLoaded = runs !== null
  useEffect(() => {
    if (!runsLoaded) return
    router.replace(
      analysisViewUrl({
        projectId,
        run: selectedRunId,
        chartType,
        systems,
        estimands,
        family,
      }),
      { scroll: false },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps -- router is stable; only sync when the view state changes
  }, [
    runsLoaded,
    projectId,
    selectedRunId,
    chartType,
    systems,
    estimands,
    family,
  ])

  const anyFilterSet =
    systems !== null ||
    estimands !== null ||
    family !== null ||
    chartType !== DEFAULT_ANALYSIS_CHART

  const onStarted = (started: AnalysisRun) => {
    setStartOpen(false)
    setFromRunId(null)
    setSelectedRunId(started.id)
    void loadRuns(true)
  }

  const selectedSummary = runs?.find((r) => r.id === selectedRunId) ?? null
  const runOptions =
    selectedRunId && runs && !selectedSummary && run
      ? [run, ...runs]
      : (runs ?? [])

  return (
    <>
      <Card className="mb-2 p-4">
        <div className="flex flex-wrap items-end gap-3">
          {filterBarLead}

          {runs && runOptions.length > 0 && (
            <div className="flex w-full flex-col sm:w-auto">
              <span
                className="mb-1 block text-xs font-medium text-zinc-500"
                id="analysis-run-filter-label"
              >
                {t('evaluation.viewer.filters.run')}
              </span>
              <Select
                value={selectedRunId ?? ''}
                onValueChange={(value: string) => setSelectedRunId(value)}
              >
                <SelectTrigger
                  className="w-full sm:w-64"
                  aria-labelledby="analysis-run-filter-label"
                  data-testid="analysis-run-filter"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {runOptions.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {t('evaluation.viewer.filters.runOption', {
                        name: r.name,
                        status: t(
                          `evaluations.detail.statusLabels.${r.status}`,
                        ),
                      })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {systemOptions.length > 0 && (
            <CheckboxDropdown
              label={t('evaluation.viewer.filters.systems')}
              options={systemOptions}
              selected={systems}
              onChange={setSystems}
              testId="analysis-systems-filter"
            />
          )}

          {estimandOptions.length > 0 && (
            <CheckboxDropdown
              label={t('evaluation.viewer.filters.estimands')}
              options={estimandOptions}
              selected={estimands}
              onChange={setEstimands}
              testId="analysis-estimands-filter"
            />
          )}

          {familyOptions.length > 0 && (
            <div className="flex flex-col">
              <span
                className="mb-1 block text-xs font-medium text-zinc-500"
                id="analysis-family-filter-label"
              >
                {t('evaluation.viewer.filters.family')}
              </span>
              <Select
                value={family ?? ALL_FAMILIES}
                onValueChange={(value: string) =>
                  setFamily(value === ALL_FAMILIES ? null : value)
                }
              >
                <SelectTrigger
                  className="w-40"
                  aria-labelledby="analysis-family-filter-label"
                  data-testid="analysis-family-filter"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_FAMILIES}>
                    {t('evaluation.viewer.filters.allFamilies')}
                  </SelectItem>
                  {familyOptions.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {runs && runs.length > 0 && (
            <div className="flex flex-col">
              <span className="mb-1 block text-xs font-medium text-zinc-500">
                {t('evaluation.viewer.filters.view')}
              </span>
              <ChartTypeSelector
                selectedType={chartType}
                onChange={setChartType}
                availableTypes={ANALYSIS_CHART_TYPES}
                persistPreference={false}
                size="sm"
              />
            </div>
          )}

          {runs && runs.length > 0 && (
            <Button
              variant="outline"
              onClick={() => {
                setChartType(DEFAULT_ANALYSIS_CHART)
                setSystems(null)
                setEstimands(null)
                setFamily(null)
              }}
              disabled={!anyFilterSet}
              aria-label={t('evaluation.viewer.filters.clearAllFilters')}
              title={t('evaluation.viewer.filters.clearAllFilters')}
              className={
                anyFilterSet
                  ? 'bg-emerald-50 text-emerald-700 ring-emerald-300 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-700'
                  : ''
              }
              data-testid="analysis-clear-filters"
            >
              <XMarkIcon className="h-4 w-4" />
            </Button>
          )}

          {canStart && (
            <Button
              variant="primary"
              onClick={() => {
                setFromRunId(null)
                setStartOpen(true)
              }}
              className="sm:ml-auto"
              data-testid="analysis-start"
            >
              <PlusIcon className="mr-2 h-4 w-4" />
              {t('evaluation.viewer.analysis.start')}
            </Button>
          )}
        </div>
      </Card>

      <div className="space-y-6">
        {listError && (
          <div
            className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
            role="alert"
          >
            {listError === 'forbidden'
              ? t('analysis.list.forbidden')
              : t('analysis.list.loadFailed')}
          </div>
        )}

        {runs === null && (
          <p className="py-8 text-center text-sm text-zinc-500" role="status">
            {t('analysis.run.loading')}
          </p>
        )}

        {runs && runs.length === 0 && !listError && !selectedRunId && (
          <Card className="p-12 text-center" data-testid="analysis-empty">
            <BeakerIcon className="mx-auto h-12 w-12 text-zinc-400" />
            <h3 className="mt-4 text-lg font-semibold text-zinc-900 dark:text-white">
              {t('analysis.list.empty')}
            </h3>
            <p className="mx-auto mt-2 max-w-xl text-zinc-500 dark:text-zinc-400">
              {t('analysis.list.subtitle')}
            </p>
          </Card>
        )}

        {runs && total > runs.length && (
          <p className="text-xs text-zinc-500">
            {t('analysis.list.more', { shown: runs.length, total })}
          </p>
        )}

        {runState.kind === 'loading' && (
          <p className="text-sm text-zinc-500" role="status">
            {t('analysis.run.loading')}
          </p>
        )}

        {(runState.kind === 'notFound' || runState.kind === 'error') && (
          <div
            className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
            data-testid="analysis-run-error"
          >
            {runState.kind === 'notFound'
              ? t('analysis.run.notFound')
              : runState.message}
          </div>
        )}

        {run && (
          <Card className="p-4" data-testid="analysis-run-strip">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold break-words text-zinc-900 dark:text-white">
                  {run.name}
                </h2>
                <RunStatusBadge status={run.status} />
              </div>
              <Button
                variant="outline"
                href={analysisRunPath(run.id)}
                data-testid="analysis-run-details"
              >
                {t('evaluation.viewer.analysis.runDetails')}
              </Button>
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
              <Fact label={t('analysis.list.col.rows')}>
                {run.frame_rows ?? MISSING}
              </Fact>
              <Fact label={t('analysis.list.col.estimates')}>
                {run.estimates_count ?? MISSING}
              </Fact>
              <Fact label={t('analysis.list.col.specHash')}>
                <span title={run.spec_hash}>{shortHash(run.spec_hash)}</span>
              </Fact>
              <Fact label={t('evaluation.viewer.analysis.engine')}>
                {run.engine_version || MISSING}
              </Fact>
            </dl>
          </Card>
        )}

        {run && isRunActive(run.status) && (
          <div
            className="rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300"
            role="status"
            data-testid="analysis-run-active"
          >
            {t(`analysis.run.${run.status}`)}
          </div>
        )}

        {run?.status === 'failed' && (
          <div
            className="rounded border border-red-300 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
            role="alert"
            data-testid="analysis-run-failed"
          >
            <p className="font-medium">{t('analysis.run.failed')}</p>
            {run.error_message && <p className="mt-1">{run.error_message}</p>}
          </div>
        )}

        {run?.status === 'completed' && estimatesError && (
          <div
            className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
            role="alert"
          >
            {estimatesError}
          </div>
        )}

        {run?.status === 'completed' && !estimates && !estimatesError && (
          <p className="text-sm text-zinc-500" role="status">
            {t('analysis.estimates.loading')}
          </p>
        )}

        {run?.status === 'completed' && estimates && (
          <>
            {chartType !== 'data' && (
              <Card className="p-6" data-testid="analysis-chart-card">
                <h3 className="mb-4 text-lg font-semibold dark:text-white">
                  {t('evaluation.viewer.chart.title')}
                </h3>
                {chartType === 'forest' ? (
                  <EstimatesForest run={run} estimates={plotted} />
                ) : chartType === 'profile' ? (
                  <EstimateProfiles
                    run={run}
                    estimates={plotted}
                    allEstimates={estimates}
                  />
                ) : (
                  <DynamicChartRenderer
                    chartType={chartType}
                    models={[]}
                    metrics={[]}
                    intervalRows={intervalRows}
                    intervalSeriesHeader={t(
                      'evaluation.statisticalResults.analysis.contrast',
                    )}
                    height={600}
                    emptyMessage={t('analysis.estimates.empty')}
                  />
                )}
              </Card>
            )}

            <Card className="p-6" data-testid="analysis-estimates-card">
              <h3 className="text-lg font-semibold dark:text-white">
                {t('analysis.estimates.title')}
              </h3>
              <p className="mt-1 mb-4 text-sm text-zinc-500 dark:text-zinc-400">
                {t('analysis.estimates.description')}
              </p>
              <EstimatesTable estimates={filtered} showFilters={false} />
            </Card>

            <StatisticalResultsPanel
              data={null}
              analysis={{ run, estimates: filtered }}
            />

            {specDesigns(run).length > 0 && (
              <Card className="p-6" data-testid="analysis-examples-card">
                <h3 className="text-lg font-semibold dark:text-white">
                  {t('analysis.views.examples.title')}
                </h3>
                <p className="mt-1 mb-4 text-sm text-zinc-500 dark:text-zinc-400">
                  {t('analysis.views.examples.description')}
                </p>
                <ExamplesPanel
                  projectId={projectId}
                  run={run}
                  estimates={plotted}
                />
              </Card>
            )}

            <div
              className="empty:hidden"
              data-testid="analysis-run-findings-slot"
            >
              <ComplianceInlineSlot
                slot="AnalysisRunFindings"
                props={{ projectId, run, estimates }}
              />
            </div>
          </>
        )}
      </div>

      {canStart && (
        <StartAnalysisDialog
          isOpen={startOpen}
          onClose={() => {
            setStartOpen(false)
            setFromRunId(null)
          }}
          projectId={projectId}
          fromRunId={fromRunId}
          onStarted={onStarted}
        />
      )}
    </>
  )
}
