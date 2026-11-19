'use client'

/**
 * Profiles of a run's estimates (the `profile` view of the evaluations page
 * and the run page): the contrasts whose estimates vary over a scope column,
 * one at a time, drawn with `EstimateProfileChart`. The reader picks the
 * contrast and the x, series and facet columns; by default x is the first
 * numeric scope column other than the system and the series is the system.
 * A fitted slope is drawn only where the run estimated the slope of exactly
 * what is plotted (`profileSlopes`); otherwise the view says so.
 */

import { useI18n } from '@/contexts/I18nContext'
import {
  defaultProfileColumns,
  profileFromEstimates,
  scopeColumns,
  profileSlopes,
  type ProfileColumns,
} from '@/lib/analysis/profile'
import { groupByContrast } from '@/lib/analysis/results'
import type { AnalysisEstimate, AnalysisRun } from '@/lib/api/analysis'
import { contrastLabel, isJointTest } from '@/lib/results/intervalRows'
import { useMemo, useState } from 'react'
import { EstimateProfileChart } from './EstimateProfileChart'

const SELECT =
  'w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 sm:w-auto sm:max-w-xs dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100'
const NONE = ''

/** The contrast groups a profile can be drawn of, in engine order. */
export function profileGroups(estimates: readonly AnalysisEstimate[]) {
  return groupByContrast(estimates.filter((e) => !isJointTest(e))).filter(
    (g) => defaultProfileColumns(g.estimates) !== null,
  )
}

export function EstimateProfiles({
  run,
  estimates,
  allEstimates,
}: {
  run: AnalysisRun
  /** The estimates to draw (e.g. the filtered ones). */
  estimates: readonly AnalysisEstimate[]
  /** Every estimate of the run, where the fitted slope is looked up. */
  allEstimates?: readonly AnalysisEstimate[]
}) {
  const { t } = useI18n()
  const groups = useMemo(() => profileGroups(estimates), [estimates])
  const [picked, setPicked] = useState<string | null>(null)
  const group = groups.find((g) => g.key === picked) ?? groups[0] ?? null
  const columns = useMemo(
    () => (group ? scopeColumns(group.estimates) : []),
    [group],
  )
  const defaults = useMemo(
    () => (group ? defaultProfileColumns(group.estimates) : null),
    [group],
  )
  // The reader's picks; undefined keeps the default, null means "none".
  const [chosen, setChosen] = useState<Partial<ProfileColumns>>({})
  const has = (name: string | null | undefined): name is string =>
    !!name && columns.some((c) => c.name === name)
  const x = has(chosen.x) ? chosen.x : (defaults?.x ?? null)
  const wantedSeries =
    chosen.series === undefined ? (defaults?.series ?? null) : chosen.series
  const series = has(wantedSeries) && wantedSeries !== x ? wantedSeries : null
  const facet =
    has(chosen.facet) && chosen.facet !== x && chosen.facet !== series
      ? chosen.facet
      : null
  const cols: ProfileColumns | null = x ? { x, series, facet } : null

  const data =
    group && cols
      ? profileFromEstimates(group.estimates, cols, {
          allLabel: t('analysis.views.profile.allLine'),
        })
      : null
  const outcome = group?.estimates[0]?.outcome ?? null
  const slopes =
    group && cols
      ? profileSlopes(run, allEstimates ?? estimates, group.estimates, cols).map(
          ({ line, estimate }) => ({
            slope: estimate.estimate as number,
            lower: estimate.ci_lower,
            upper: estimate.ci_upper,
            label:
              line === null
                ? contrastLabel(estimate)
                : `${cols.series} = ${line} · ${contrastLabel(estimate)}`,
            ...(line === null ? {} : { line }),
          }),
        )
      : []

  if (!group || !cols || !data) {
    return (
      <p
        className="py-8 text-center text-sm text-zinc-500 dark:text-zinc-400"
        data-testid="profile-none"
      >
        {t('analysis.views.profile.none')}
      </p>
    )
  }

  const columnSelect = (
    label: string,
    value: string | null,
    onChange: (v: string | null) => void,
    testId: string,
    allowNone: boolean,
  ) => (
    <label className="flex w-full min-w-0 flex-col gap-1 text-xs font-medium text-zinc-500 sm:w-auto">
      {label}
      <select
        className={SELECT}
        value={value ?? NONE}
        onChange={(e) => onChange(e.target.value || null)}
        name={testId}
        data-testid={testId}
      >
        {allowNone && (
          <option value={NONE}>{t('analysis.views.profile.noColumn')}</option>
        )}
        {columns.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  )

  return (
    <div className="min-w-0 space-y-4" data-testid="estimate-profiles">
      <div className="flex flex-wrap items-end gap-3">
        {groups.length > 1 && (
          <label className="flex w-full min-w-0 flex-col gap-1 text-xs font-medium text-zinc-500 sm:w-auto">
            {t('analysis.views.profile.contrast')}
            <select
              className={SELECT}
              value={group.key}
              onChange={(e) => {
                setPicked(e.target.value)
                setChosen({})
              }}
              name="profile-contrast"
              data-testid="profile-contrast"
            >
              {groups.map((g) => (
                <option key={g.key} value={g.key}>
                  {contrastLabel(g.estimates[0])}
                </option>
              ))}
            </select>
          </label>
        )}
        {columnSelect(
          t('analysis.views.profile.x'),
          cols.x,
          (v) => v && setChosen((c) => ({ ...c, x: v })),
          'profile-x',
          false,
        )}
        {columnSelect(
          t('analysis.views.profile.series'),
          cols.series,
          (v) => setChosen((c) => ({ ...c, series: v })),
          'profile-series',
          true,
        )}
        {columnSelect(
          t('analysis.views.profile.facet'),
          cols.facet,
          (v) => setChosen((c) => ({ ...c, facet: v })),
          'profile-facet',
          true,
        )}
      </div>
      <EstimateProfileChart
        data={data}
        xLabel={cols.x}
        yLabel={outcome ?? contrastLabel(group.estimates[0])}
        slopes={slopes}
      />
      {slopes.length === 0 && (
        <p
          className="text-xs text-zinc-500 dark:text-zinc-400"
          data-testid="profile-no-slope"
        >
          {t('analysis.views.profile.noSlope')}
        </p>
      )}
    </div>
  )
}
