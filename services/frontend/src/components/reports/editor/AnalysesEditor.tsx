'use client'

/**
 * The report editor's Analyses card: the author picks completed analysis
 * runs of the project that read no other project (the API offers only
 * those), writes a title and text per run and defines its exhibits: a
 * forest plot or a table of the estimates its filters select (estimands,
 * contrasts, families, systems). Each exhibit previews the run's live
 * estimates with the components the report draws; the report itself shows
 * the estimates copied into its snapshot on publish or "Refresh data".
 */

import { AnalysisExhibit } from '@/components/reports/view/AnalysisExhibit'
import { Button } from '@/components/shared/Button'
import { Input } from '@/components/shared/Input'
import { Label } from '@/components/shared/Label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { Textarea } from '@/components/shared/Textarea'
import { useI18n } from '@/contexts/I18nContext'
import { formatInterval } from '@/lib/analysis/results'
import { analysisAPI, type AnalysisEstimate } from '@/lib/api/analysis'
import {
  listReportAnalysisRuns,
  type AnalysisExhibitContent,
  type AnalysisRunContent,
  type ReportAnalysisRunOption,
} from '@/lib/api/reports'
import {
  cleanFilters,
  EXHIBIT_FILTER_KEYS,
  exhibitFilterOptions,
  MAX_REPORT_ANALYSIS_RUNS,
  MAX_REPORT_ESTIMATES_PER_RUN,
  MAX_RUN_EXHIBITS,
  newExhibitId,
  selectEstimates,
  type AnalysisRunDefinition,
  type ExhibitFilterKey,
} from '@/lib/reports/analyses'
import { formatCount, formatDate } from '@/lib/reports/format'
import type { ReportAnalysesSnapshot, ReportExhibitType } from '@/types/report'
import {
  ArrowDownIcon,
  ArrowUpIcon,
  ChartBarIcon,
  PlusIcon,
  TableCellsIcon,
  TrashIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

type EstimatesState =
  | { status: 'loading' }
  | { status: 'error' }
  | {
      status: 'ready'
      estimates: AnalysisEstimate[]
      run: AnalysisRunDefinition
    }

const NO_BAND = 'none'

const subCardClass =
  'rounded-lg border border-zinc-200 p-4 dark:border-zinc-700 dark:bg-zinc-900/40'
const exhibitCardClass =
  'rounded-md border border-zinc-200 bg-zinc-50/60 p-3 sm:p-4 dark:border-zinc-700 dark:bg-zinc-800/40'
const iconButtonClass =
  'rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:cursor-not-allowed disabled:opacity-40 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white'

function move<T>(items: readonly T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length) return [...items]
  const next = [...items]
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

/** Whether the stored snapshot holds this exhibit as defined now. */
function inSnapshot(
  snapshot: ReportAnalysesSnapshot | null | undefined,
  runId: string,
  exhibit: AnalysisExhibitContent,
): boolean {
  const run = snapshot?.runs.find((r) => r.id === runId)
  const stored = run?.exhibits.find((e) => e.id === exhibit.id)
  if (!stored) return false
  const band =
    exhibit.type === 'forest'
      ? exhibit.band === undefined
        ? 0
        : exhibit.band
      : null
  return (
    stored.type === exhibit.type &&
    (stored.band ?? null) === band &&
    JSON.stringify(cleanFilters(stored.filters)) ===
      JSON.stringify(cleanFilters(exhibit.filters))
  )
}

function IconButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string
  onClick: () => void
  disabled?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={iconButtonClass}
    >
      {children}
    </button>
  )
}

function FilterSelect({
  id,
  label,
  options,
  value,
  onChange,
}: {
  id: string
  label: string
  options: string[]
  value: string[]
  onChange: (next: string[]) => void
}) {
  const { t } = useI18n()
  // A stored value the run no longer has stays selectable, so it can be removed.
  const all = useMemo(
    () => [...new Set([...options, ...value])],
    [options, value],
  )
  return (
    <div className="min-w-0">
      <Label htmlFor={id}>{label}</Label>
      <Select multiple value={value} onValueChange={onChange}>
        <SelectTrigger
          id={id}
          className="mt-1 w-full"
          disabled={all.length === 0}
          data-testid={id}
        >
          <SelectValue placeholder={t('reports.editor.analyses.filterAll')} />
        </SelectTrigger>
        <SelectContent>
          {all.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function ExhibitEditor({
  runId,
  exhibit,
  index,
  count,
  label,
  estimates,
  snapshot,
  onChange,
  onMove,
  onRemove,
}: {
  runId: string
  exhibit: AnalysisExhibitContent
  index: number
  count: number
  label: string
  estimates: EstimatesState
  snapshot: ReportAnalysesSnapshot | null | undefined
  onChange: (next: AnalysisExhibitContent) => void
  onMove: (to: number) => void
  onRemove: () => void
}) {
  const { t, locale } = useI18n()
  const live = useMemo(
    () => (estimates.status === 'ready' ? estimates.estimates : []),
    [estimates],
  )
  const definition = estimates.status === 'ready' ? estimates.run : null
  const options = useMemo(
    () => exhibitFilterOptions(live, definition),
    [live, definition],
  )
  const filters = exhibit.filters ?? {}
  const selected = useMemo(
    () => selectEstimates(live, exhibit.filters, definition),
    [live, exhibit.filters, definition],
  )
  // Bound sets the selected estimates declare, labelled by their first bounds.
  const bands = useMemo(() => {
    const out: { index: number; label: string }[] = []
    for (const e of selected) {
      ;(e.tost ?? []).forEach((b, i) => {
        if (!out.some((x) => x.index === i))
          out.push({
            index: i,
            label: formatInterval(b.lower, b.upper, locale),
          })
      })
    }
    return out.sort((a, b) => a.index - b.index)
  }, [selected, locale])
  const prefix = `exhibit-${runId}-${exhibit.id}`
  const setFilter = (key: ExhibitFilterKey, values: string[]) =>
    onChange({
      ...exhibit,
      filters: cleanFilters({ ...filters, [key]: values }),
    })
  const band = exhibit.band === undefined ? 0 : exhibit.band
  const current = inSnapshot(snapshot, runId, exhibit)

  return (
    <div className={exhibitCardClass} data-testid="analysis-exhibit-editor">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-zinc-900 dark:text-white">
            {label}
          </span>
          <span
            className={
              current
                ? 'rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300'
                : 'rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-800 dark:bg-amber-900/30 dark:text-amber-300'
            }
            data-testid="exhibit-snapshot-status"
          >
            {current
              ? t('reports.editor.analyses.inSnapshot')
              : t('reports.editor.analyses.notInSnapshot')}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <IconButton
            label={t('reports.editor.analyses.moveUp')}
            onClick={() => onMove(index - 1)}
            disabled={index === 0}
          >
            <ArrowUpIcon className="h-4 w-4" />
          </IconButton>
          <IconButton
            label={t('reports.editor.analyses.moveDown')}
            onClick={() => onMove(index + 1)}
            disabled={index === count - 1}
          >
            <ArrowDownIcon className="h-4 w-4" />
          </IconButton>
          <IconButton
            label={t('reports.editor.analyses.removeExhibit')}
            onClick={onRemove}
          >
            <TrashIcon className="h-4 w-4" />
          </IconButton>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="min-w-0">
          <Label htmlFor={`${prefix}-type`}>
            {t('reports.editor.analyses.exhibitType')}
          </Label>
          <Select
            value={exhibit.type}
            onValueChange={(v) =>
              onChange({
                ...exhibit,
                type: v as ReportExhibitType,
                band: v === 'forest' ? 0 : null,
              })
            }
          >
            <SelectTrigger
              id={`${prefix}-type`}
              className="mt-1 w-full"
              data-testid="exhibit-type"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="forest">
                {t('reports.editor.analyses.typeForest')}
              </SelectItem>
              <SelectItem value="table">
                {t('reports.editor.analyses.typeTable')}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="min-w-0">
          <Label htmlFor={`${prefix}-title`}>
            {t('reports.editor.analyses.exhibitTitle')}
          </Label>
          <Input
            id={`${prefix}-title`}
            value={exhibit.title ?? ''}
            onChange={(e) => onChange({ ...exhibit, title: e.target.value })}
            className="mt-1"
          />
        </div>
        {EXHIBIT_FILTER_KEYS.map((key) => (
          <FilterSelect
            key={key}
            id={`${prefix}-${key}`}
            label={t(`reports.editor.analyses.filter.${key}`)}
            options={options[key]}
            value={filters[key] ?? []}
            onChange={(values) => setFilter(key, values)}
          />
        ))}
        {exhibit.type === 'forest' && bands.length > 0 && (
          <div className="min-w-0">
            <Label htmlFor={`${prefix}-band`}>
              {t('reports.editor.analyses.band')}
            </Label>
            <Select
              value={band === null ? NO_BAND : String(band)}
              onValueChange={(v) =>
                onChange({ ...exhibit, band: v === NO_BAND ? null : Number(v) })
              }
            >
              <SelectTrigger id={`${prefix}-band`} className="mt-1 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_BAND}>
                  {t('analysis.forest.noBand')}
                </SelectItem>
                {bands.map((b) => (
                  <SelectItem key={b.index} value={String(b.index)}>
                    {t('reports.editor.analyses.bandOption', {
                      n: b.index + 1,
                      bounds: b.label,
                    })}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="min-w-0 sm:col-span-2">
          <Label htmlFor={`${prefix}-caption`}>
            {t('reports.editor.analyses.caption')}
          </Label>
          <Textarea
            id={`${prefix}-caption`}
            value={exhibit.caption ?? ''}
            onChange={(e) => onChange({ ...exhibit, caption: e.target.value })}
            placeholder={t('reports.editor.analyses.captionPlaceholder')}
            rows={2}
          />
        </div>
      </div>

      <div className="mt-4 border-t border-zinc-200 pt-3 dark:border-zinc-700">
        <p
          className="mb-1 text-xs text-zinc-500 dark:text-zinc-400"
          data-testid="exhibit-preview-count"
        >
          {estimates.status === 'ready'
            ? t('reports.editor.analyses.previewCount', {
                shown: formatCount(selected.length, locale),
                total: formatCount(live.length, locale),
              })
            : estimates.status === 'loading'
              ? t('reports.editor.analyses.loadingEstimates')
              : t('reports.editor.analyses.estimatesFailed')}
        </p>
        {estimates.status === 'ready' && (
          <AnalysisExhibit
            type={exhibit.type}
            estimates={selected}
            band={exhibit.type === 'forest' ? band : null}
            label={t('reports.editor.analyses.preview')}
            title={exhibit.title}
            caption={exhibit.caption}
            t={t}
          />
        )}
      </div>
    </div>
  )
}

export interface AnalysesEditorProps {
  projectId: string
  customText: string
  runs: AnalysisRunContent[]
  onCustomTextChange: (text: string) => void
  onRunsChange: (runs: AnalysisRunContent[]) => void
  /** The stored snapshot's Analyses section (what the report shows now). */
  snapshot: ReportAnalysesSnapshot | null | undefined
}

export function AnalysesEditor({
  projectId,
  customText,
  runs,
  onCustomTextChange,
  onRunsChange,
  snapshot,
}: AnalysesEditorProps) {
  const { t, locale } = useI18n()
  const [options, setOptions] = useState<ReportAnalysisRunOption[] | null>(null)
  const [optionsFailed, setOptionsFailed] = useState(false)
  const [toAdd, setToAdd] = useState('')
  const [estimates, setEstimates] = useState<Record<string, EstimatesState>>({})
  const requested = useRef(new Set<string>())

  useEffect(() => {
    let cancelled = false
    listReportAnalysisRuns(projectId)
      .then((items) => {
        if (!cancelled) setOptions(items)
      })
      .catch(() => {
        if (!cancelled) setOptionsFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const offered = useMemo(
    () => new Map((options ?? []).map((o) => [o.id, o])),
    [options],
  )
  const runIds = runs.map((r) => r.run_id).join('\u0000')

  // Live estimates of every run in the section, for the previews.
  useEffect(() => {
    if (!options) return
    for (const runId of runIds ? runIds.split('\u0000') : []) {
      if (!offered.has(runId) || requested.current.has(runId)) continue
      requested.current.add(runId)
      Promise.all([analysisAPI.listEstimates(runId), analysisAPI.getRun(runId)])
        .then(([items, run]) =>
          setEstimates((p) => ({
            ...p,
            [runId]: {
              status: 'ready',
              estimates: items,
              run: { normalized_spec: run.normalized_spec, fits: run.fits },
            },
          })),
        )
        .catch(() =>
          setEstimates((p) => ({ ...p, [runId]: { status: 'error' } })),
        )
    }
  }, [runIds, options, offered])

  const used = new Set(runs.map((r) => r.run_id))
  const addable = (options ?? []).filter((o) => !used.has(o.id))
  const omitted = new Map(
    (snapshot?.omitted ?? []).map((o) => [o.run_id, o.reason]),
  )

  const updateRun = (index: number, next: AnalysisRunContent) =>
    onRunsChange(runs.map((r, i) => (i === index ? next : r)))

  const addRun = () => {
    if (!toAdd) return
    onRunsChange([
      ...runs,
      {
        run_id: toAdd,
        title: null,
        text: null,
        exhibits: [
          { id: newExhibitId([]), type: 'forest', filters: {}, band: 0 },
        ],
      },
    ])
    setToAdd('')
  }

  const addExhibit = (index: number, type: ReportExhibitType) => {
    const run = runs[index]
    updateRun(index, {
      ...run,
      exhibits: [
        ...run.exhibits,
        {
          id: newExhibitId(run.exhibits.map((e) => e.id)),
          type,
          filters: {},
          band: type === 'forest' ? 0 : null,
        },
      ],
    })
  }

  // Exhibits are numbered across the section as the report numbers them.
  let figures = 0
  let tables = 0

  return (
    <div className="space-y-4" data-testid="analyses-editor">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        {t('reports.editor.analyses.hint')}
      </p>
      <div>
        <Label htmlFor="analysesText">
          {t('reports.editor.analyses.customText')}
        </Label>
        <Textarea
          id="analysesText"
          value={customText}
          onChange={(e) => onCustomTextChange(e.target.value)}
          placeholder={t('reports.editor.analyses.customTextPlaceholder')}
          rows={3}
        />
      </div>

      {runs.map((run, index) => {
        const option = offered.get(run.run_id)
        const stored = snapshot?.runs.find((r) => r.id === run.run_id)
        const name = option?.name ?? stored?.name ?? run.run_id
        const unavailable =
          (options !== null && !option) || omitted.has(run.run_id)
        // A run the API does not offer has no live estimates to preview.
        const state: EstimatesState =
          options !== null && !option
            ? { status: 'error' }
            : (estimates[run.run_id] ?? { status: 'loading' })
        const union = new Set<number>()
        if (state.status === 'ready') {
          for (const ex of run.exhibits) {
            for (const e of selectEstimates(
              state.estimates,
              ex.filters,
              state.run,
            ))
              union.add(e.position)
          }
        }
        return (
          <section
            key={run.run_id}
            className={subCardClass}
            data-testid="analysis-run-editor"
            data-run-id={run.run_id}
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="text-base font-semibold [overflow-wrap:anywhere] text-zinc-900 dark:text-white">
                  {name}
                </h3>
                {option && (
                  <p className="text-xs text-zinc-500 dark:text-zinc-400">
                    {t('reports.editor.analyses.runSummary', {
                      date: formatDate(option.completed_at, locale) || '–',
                      estimates: formatCount(
                        option.estimates_count ?? 0,
                        locale,
                      ),
                      hash: option.spec_hash.slice(0, 12),
                    })}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1">
                <IconButton
                  label={t('reports.editor.analyses.moveUp')}
                  onClick={() => onRunsChange(move(runs, index, index - 1))}
                  disabled={index === 0}
                >
                  <ArrowUpIcon className="h-4 w-4" />
                </IconButton>
                <IconButton
                  label={t('reports.editor.analyses.moveDown')}
                  onClick={() => onRunsChange(move(runs, index, index + 1))}
                  disabled={index === runs.length - 1}
                >
                  <ArrowDownIcon className="h-4 w-4" />
                </IconButton>
                <IconButton
                  label={t('reports.editor.analyses.removeRun')}
                  onClick={() =>
                    onRunsChange(runs.filter((_, i) => i !== index))
                  }
                >
                  <TrashIcon className="h-4 w-4" />
                </IconButton>
              </div>
            </div>

            {unavailable && (
              <p
                className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200"
                role="alert"
                data-testid="analysis-run-unavailable"
              >
                {t('reports.editor.analyses.runUnavailable')}
              </p>
            )}

            <div className="space-y-3">
              <div>
                <Label htmlFor={`analysis-run-${index}-title`}>
                  {t('reports.editor.analyses.runTitle')}
                </Label>
                <Input
                  id={`analysis-run-${index}-title`}
                  value={run.title ?? ''}
                  placeholder={name}
                  onChange={(e) =>
                    updateRun(index, { ...run, title: e.target.value })
                  }
                  className="mt-1"
                />
              </div>
              <div>
                <Label htmlFor={`analysis-run-${index}-text`}>
                  {t('reports.editor.analyses.runText')}
                </Label>
                <Textarea
                  id={`analysis-run-${index}-text`}
                  value={run.text ?? ''}
                  placeholder={t('reports.editor.analyses.runTextPlaceholder')}
                  onChange={(e) =>
                    updateRun(index, { ...run, text: e.target.value })
                  }
                  rows={3}
                />
              </div>

              {union.size > MAX_REPORT_ESTIMATES_PER_RUN && (
                <p
                  className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200"
                  data-testid="analysis-run-too-many"
                >
                  {t('reports.editor.analyses.tooManyEstimates', {
                    count: formatCount(union.size, locale),
                    max: formatCount(MAX_REPORT_ESTIMATES_PER_RUN, locale),
                  })}
                </p>
              )}

              {run.exhibits.map((exhibit, j) => {
                const label =
                  exhibit.type === 'forest'
                    ? t('reports.view.analyses.figure', { n: ++figures })
                    : t('reports.view.analyses.table', { n: ++tables })
                return (
                  <ExhibitEditor
                    key={exhibit.id}
                    runId={run.run_id}
                    exhibit={exhibit}
                    index={j}
                    count={run.exhibits.length}
                    label={label}
                    estimates={state}
                    snapshot={snapshot}
                    onChange={(next) =>
                      updateRun(index, {
                        ...run,
                        exhibits: run.exhibits.map((e, k) =>
                          k === j ? next : e,
                        ),
                      })
                    }
                    onMove={(to) =>
                      updateRun(index, {
                        ...run,
                        exhibits: move(run.exhibits, j, to),
                      })
                    }
                    onRemove={() =>
                      updateRun(index, {
                        ...run,
                        exhibits: run.exhibits.filter((_, k) => k !== j),
                      })
                    }
                  />
                )
              })}

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => addExhibit(index, 'forest')}
                  disabled={run.exhibits.length >= MAX_RUN_EXHIBITS}
                >
                  <ChartBarIcon className="mr-2 h-4 w-4" />
                  {t('reports.editor.analyses.addForest')}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => addExhibit(index, 'table')}
                  disabled={run.exhibits.length >= MAX_RUN_EXHIBITS}
                >
                  <TableCellsIcon className="mr-2 h-4 w-4" />
                  {t('reports.editor.analyses.addTable')}
                </Button>
              </div>
            </div>
          </section>
        )
      })}

      <div className="rounded-lg border border-dashed border-zinc-300 p-4 dark:border-zinc-700">
        {optionsFailed ? (
          <p className="text-sm text-red-700 dark:text-red-400">
            {t('reports.editor.analyses.runsFailed')}
          </p>
        ) : options === null ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('reports.editor.analyses.loadingRuns')}
          </p>
        ) : options.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('reports.editor.analyses.noRuns')}
          </p>
        ) : addable.length === 0 ? (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {t('reports.editor.analyses.allRunsAdded')}
          </p>
        ) : (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="min-w-0 flex-1">
              <Label htmlFor="analysis-run-add">
                {t('reports.editor.analyses.addRunLabel')}
              </Label>
              <Select searchable value={toAdd} onValueChange={setToAdd}>
                <SelectTrigger
                  id="analysis-run-add"
                  className="mt-1 w-full"
                  data-testid="analysis-run-add"
                >
                  <SelectValue
                    placeholder={t('reports.editor.analyses.pickRun')}
                  />
                </SelectTrigger>
                <SelectContent>
                  {addable.map((o) => (
                    <SelectItem key={o.id} value={o.id} textValue={o.name}>
                      {t('reports.editor.analyses.runOption', {
                        name: o.name,
                        date: formatDate(o.completed_at, locale) || '–',
                      })}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              variant="outline"
              onClick={addRun}
              disabled={!toAdd || runs.length >= MAX_REPORT_ANALYSIS_RUNS}
            >
              <PlusIcon className="mr-2 h-4 w-4" />
              {t('reports.editor.analyses.addRun')}
            </Button>
          </div>
        )}
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          {t('reports.editor.analyses.singleProjectOnly')}
        </p>
      </div>
    </div>
  )
}
