'use client'

/**
 * Examples of a contrast: the units of the variant design an analysis run
 * read, paged, and one unit opened in the unit viewer with the twins of the
 * factor the contrast compares side by side and the answers of the chosen
 * system. The contrast's factor comes from the run's spec where it can be
 * read (`focusForContrast`); the reader can pick another factor in the
 * viewer. Needs full read access to the project's task content.
 */

import { useI18n } from '@/contexts/I18nContext'
import { specDesigns } from '@/lib/analysis/profile'
import { groupByContrast } from '@/lib/analysis/results'
import { focusForContrast } from '@/lib/analysis/units'
import {
  statusOf,
  type AnalysisEstimate,
  type AnalysisRun,
} from '@/lib/api/analysis'
import {
  variantViewsAPI,
  type VariantDesignRow,
  type VariantUnitPage,
} from '@/lib/api/variantViews'
import {
  contrastLabel,
  isJointTest,
  systemOf,
} from '@/lib/results/intervalRows'
import clsx from 'clsx'
import { useEffect, useMemo, useState } from 'react'
import { VariantUnitLoader } from './VariantUnitViewer'
import { Notice } from './viewParts'

/** Units per page of the unit list. */
export const EXAMPLE_UNITS_PAGE = 12

const SELECT =
  'w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-zinc-900 sm:w-auto sm:max-w-xs dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100'
const ALL = ''

export function ExamplesPanel({
  projectId,
  run,
  estimates,
}: {
  projectId: string
  run: AnalysisRun
  /** The estimates to offer contrasts from (e.g. the filtered ones). */
  estimates: readonly AnalysisEstimate[]
}) {
  const { t } = useI18n()
  const designKeys = useMemo(() => specDesigns(run), [run])
  const groups = useMemo(
    () => groupByContrast(estimates.filter((e) => !isJointTest(e))),
    [estimates],
  )
  const [contrast, setContrast] = useState<string | null>(null)
  const group = groups.find((g) => g.key === contrast) ?? groups[0] ?? null
  const systems = useMemo(
    () =>
      [
        ...new Set(
          (group?.estimates ?? [])
            .map(systemOf)
            .filter((s): s is string => s !== null),
        ),
      ].sort(),
    [group],
  )
  const [pickedSystem, setSystem] = useState<string>(ALL)
  // The system filter keeps only systems of the chosen contrast.
  const system = systems.includes(pickedSystem) ? pickedSystem : ALL
  const [design, setDesign] = useState<string | null>(null)
  const designKey =
    design && designKeys.includes(design) ? design : (designKeys[0] ?? null)
  const [offset, setOffset] = useState(0)
  const pageKey = `${designKey}\u0000${offset}`
  // The last unit page answered, with the request it answers.
  const [loaded, setLoaded] = useState<{
    key: string
    page: VariantUnitPage | null
    error: 'forbidden' | 'failed' | null
  } | null>(null)
  const page = loaded?.key === pageKey ? loaded.page : null
  const pageError = loaded?.key === pageKey ? loaded.error : null
  const [pickedUnit, setUnit] = useState<string | null>(null)
  const unit =
    page && pickedUnit && page.items.some((i) => i.unit === pickedUnit)
      ? pickedUnit
      : (page?.items[0]?.unit ?? null)
  const [designs, setDesigns] = useState<VariantDesignRow[]>([])

  useEffect(() => {
    let cancelled = false
    variantViewsAPI
      .listDesigns(projectId)
      .then((rows) => !cancelled && setDesigns(rows))
      .catch(() => !cancelled && setDesigns([]))
    return () => {
      cancelled = true
    }
  }, [projectId])

  useEffect(() => {
    if (!designKey) return
    let cancelled = false
    const key = `${designKey}\u0000${offset}`
    variantViewsAPI
      .listUnits(projectId, designKey, EXAMPLE_UNITS_PAGE, offset)
      .then((p) => !cancelled && setLoaded({ key, page: p, error: null }))
      .catch((e: unknown) => {
        if (cancelled) return
        setLoaded({
          key,
          page: null,
          error: statusOf(e) === 403 ? 'forbidden' : 'failed',
        })
      })
    return () => {
      cancelled = true
    }
  }, [projectId, designKey, offset])

  const factorNames = useMemo(
    () =>
      (designs.find((d) => d.key === designKey)?.spec.factors ?? []).map(
        (f) => f.name,
      ),
    [designs, designKey],
  )
  const focus = useMemo(
    () =>
      group
        ? focusForContrast(
            run.normalized_spec,
            {
              estimand_id: group.estimandId,
              contrast_id: group.contrastId,
            },
            factorNames,
          )
        : {},
    [group, run.normalized_spec, factorNames],
  )

  if (!designKey || groups.length === 0) return null

  const total = page?.total ?? 0
  const label = (key: string) => {
    const g = groups.find((x) => x.key === key)
    return g ? contrastLabel(g.estimates[0]) : key
  }

  // Without full content rights every design's units answer 403: the
  // pickers would change nothing, so only the reason is shown.
  if (pageError === 'forbidden') {
    return (
      <div className="min-w-0" data-testid="examples-panel">
        <Notice tone="info">{t('analysis.views.unit.forbidden')}</Notice>
      </div>
    )
  }

  return (
    <div className="min-w-0 space-y-4" data-testid="examples-panel">
      <div className="flex flex-wrap items-end gap-3">
        {groups.length > 1 && (
          <label className="flex w-full min-w-0 flex-col gap-1 text-xs font-medium text-zinc-500 sm:w-auto">
            {t('analysis.views.examples.contrast')}
            <select
              className={SELECT}
              value={group?.key ?? ''}
              onChange={(e) => setContrast(e.target.value)}
              name="examples-contrast"
              data-testid="examples-contrast"
            >
              {groups.map((g) => (
                <option key={g.key} value={g.key}>
                  {label(g.key)}
                </option>
              ))}
            </select>
          </label>
        )}
        {systems.length > 0 && (
          <label className="flex w-full min-w-0 flex-col gap-1 text-xs font-medium text-zinc-500 sm:w-auto">
            {t('analysis.views.examples.system')}
            <select
              className={SELECT}
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              name="examples-system"
              data-testid="examples-system"
            >
              <option value={ALL}>
                {t('analysis.views.examples.allSystems')}
              </option>
              {systems.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        )}
        {designKeys.length > 1 && (
          <label className="flex w-full min-w-0 flex-col gap-1 text-xs font-medium text-zinc-500 sm:w-auto">
            {t('analysis.views.examples.design')}
            <select
              className={SELECT}
              value={designKey}
              onChange={(e) => {
                setDesign(e.target.value)
                setOffset(0)
                setUnit(null)
              }}
              name="examples-design"
              data-testid="examples-design"
            >
              {designKeys.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {pageError && (
        <Notice tone="error">{t('analysis.views.examples.loadFailed')}</Notice>
      )}

      {page && (
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            <span>
              {t('analysis.views.examples.units', {
                from: total === 0 ? 0 : offset + 1,
                to: offset + page.items.length,
                total,
              })}
            </span>
            {total > EXAMPLE_UNITS_PAGE && (
              <span className="flex gap-3">
                <button
                  type="button"
                  className="font-medium text-emerald-700 hover:underline disabled:cursor-not-allowed disabled:text-zinc-400 disabled:no-underline dark:text-emerald-400"
                  disabled={offset === 0}
                  onClick={() =>
                    setOffset(Math.max(0, offset - EXAMPLE_UNITS_PAGE))
                  }
                >
                  {t('analysis.views.examples.previous')}
                </button>
                <button
                  type="button"
                  className="font-medium text-emerald-700 hover:underline disabled:cursor-not-allowed disabled:text-zinc-400 disabled:no-underline dark:text-emerald-400"
                  disabled={offset + EXAMPLE_UNITS_PAGE >= total}
                  onClick={() => setOffset(offset + EXAMPLE_UNITS_PAGE)}
                >
                  {t('analysis.views.examples.next')}
                </button>
              </span>
            )}
          </div>
          {page.items.length === 0 ? (
            <Notice>{t('analysis.views.examples.noUnits')}</Notice>
          ) : (
            <div
              className="flex flex-wrap gap-2"
              role="group"
              aria-label={t('analysis.views.examples.unitsAria')}
            >
              {page.items.map((item) => (
                <button
                  key={item.unit}
                  type="button"
                  onClick={() => setUnit(item.unit)}
                  aria-pressed={item.unit === unit}
                  className={clsx(
                    'max-w-[14rem] truncate rounded-full px-3 py-1 font-mono text-xs ring-1 ring-inset',
                    item.unit === unit
                      ? 'bg-zinc-900 text-white ring-zinc-900 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/30'
                      : 'text-zinc-700 ring-zinc-300 hover:bg-zinc-50 dark:text-zinc-300 dark:ring-zinc-700 dark:hover:bg-zinc-800',
                  )}
                  title={t('analysis.views.examples.unitTitle', {
                    unit: item.unit,
                    count: item.task_count,
                  })}
                  data-testid="examples-unit"
                >
                  {item.unit}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {unit && !pageError && (
        <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <VariantUnitLoader
            key={`${designKey}\u0000${unit}\u0000${system}`}
            projectId={projectId}
            designKey={designKey}
            unit={unit}
            system={system || null}
            focus={focus}
          />
        </div>
      )}
    </div>
  )
}
