'use client'

/**
 * Forest plot of one contrast across its scopes (pooled first, then every
 * scope level), with a picker for the contrast and for the optional
 * equivalence band. The band choices are the bound sets the spec declared
 * for the contrast (TOST); with a band shown, every row also draws the
 * interval the equivalence decision uses (the TOST level, 90 % by default).
 */

import {
  ForestPlot,
  type ForestPlotRow,
} from '@/components/analysis/ForestPlot'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import {
  commonNullValue,
  equivalenceBands,
  formatInterval,
  formatLevel,
  groupByContrast,
  scopeDescription,
  tostFor,
  type ContrastGroup,
} from '@/lib/analysis/results'
import type { AnalysisEstimate } from '@/lib/api/analysis'
import { useMemo, useState } from 'react'

const NO_BAND = 'none'

const hasEstimate = (e: AnalysisEstimate) =>
  typeof e.estimate === 'number' && Number.isFinite(e.estimate)

/** Contrast groups worth plotting: at least one finite estimate. */
export function plottableGroups(
  estimates: readonly AnalysisEstimate[],
): ContrastGroup[] {
  return groupByContrast(estimates).filter((g) => g.estimates.some(hasEstimate))
}

export function groupLabel(group: ContrastGroup): string {
  return group.contrastId && group.contrastId !== group.estimandId
    ? `${group.estimandId} · ${group.contrastId}`
    : group.estimandId
}

export function ContrastForestPlot({
  estimates,
}: {
  estimates: readonly AnalysisEstimate[]
}) {
  const { t, locale } = useI18n()
  const groups = useMemo(() => plottableGroups(estimates), [estimates])
  const [selected, setSelected] = useState<string | null>(null)
  const group = groups.find((g) => g.key === selected) ?? groups[0] ?? null
  const bands = useMemo(
    () => (group ? equivalenceBands(group.estimates) : []),
    [group],
  )
  // Per contrast: the chosen band index, or NO_BAND. Default: the first
  // declared bound set, when the contrast declares one.
  const [bandChoice, setBandChoice] = useState<Record<string, string>>({})
  const choice =
    (group && bandChoice[group.key]) ?? (bands.length > 0 ? '0' : NO_BAND)
  const band =
    choice === NO_BAND
      ? null
      : (bands.find((b) => String(b.index) === choice) ?? null)

  if (!group) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        {t('analysis.forest.empty')}
      </p>
    )
  }

  const rows: ForestPlotRow[] = group.estimates.map((e) => {
    const scope = scopeDescription(e)
    const tost = band ? tostFor(e, band.index) : null
    return {
      id: String(e.position),
      label: scope ?? t('analysis.scope.pooled'),
      emphasis: scope === null,
      estimate: hasEstimate(e) ? e.estimate : null,
      lower: e.ci_lower,
      upper: e.ci_upper,
      inner:
        tost &&
        typeof tost.ci_lower === 'number' &&
        typeof tost.ci_upper === 'number'
          ? { lower: tost.ci_lower, upper: tost.ci_upper }
          : null,
      note: hasEstimate(e)
        ? null
        : e.message || t(`analysis.forest.noEstimate`),
    }
  })
  const ciLevel = group.estimates.find((e) => e.ci_level)?.ci_level ?? null
  const outcome = group.estimates.find((e) => e.outcome)?.outcome ?? undefined
  const bandLabel = band
    ? t('analysis.forest.bandLabel', {
        bounds: formatInterval(band.lower, band.upper, locale),
      })
    : undefined

  return (
    <div data-testid="contrast-forest-plot">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-zinc-500" id="forest-contrast-label">
          {t('analysis.forest.contrast')}
        </label>
        <Select value={group.key} onValueChange={setSelected}>
          <SelectTrigger
            className="w-72 max-w-full"
            aria-labelledby="forest-contrast-label"
            data-testid="forest-contrast-select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {groups.map((g) => (
              <SelectItem key={g.key} value={g.key}>
                {groupLabel(g)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {bands.length > 0 && (
          <>
            <label className="text-xs text-zinc-500" id="forest-band-label">
              {t('analysis.forest.band')}
            </label>
            <Select
              value={choice}
              onValueChange={(value) =>
                setBandChoice((prev) => ({ ...prev, [group.key]: value }))
              }
            >
              <SelectTrigger
                className="w-56"
                aria-labelledby="forest-band-label"
                data-testid="forest-band-select"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_BAND}>
                  {t('analysis.forest.noBand')}
                </SelectItem>
                {bands.map((b) => (
                  <SelectItem key={`band-${b.index}`} value={String(b.index)}>
                    {formatInterval(b.lower, b.upper, locale)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        )}
      </div>
      <ForestPlot
        rows={rows}
        nullValue={commonNullValue(group.estimates) ?? 0}
        band={
          band
            ? { lower: band.lower, upper: band.upper, label: bandLabel }
            : null
        }
        ariaLabel={t('analysis.forest.ariaLabel', {
          contrast: groupLabel(group),
        })}
        axisLabel={outcome}
        legend={{
          interval: t('analysis.forest.legendInterval', {
            level: formatLevel(ciLevel, locale),
          }),
          inner: band
            ? t('analysis.forest.legendInner', {
                level: formatLevel(band.level, locale),
              })
            : undefined,
          band: bandLabel,
        }}
      />
    </div>
  )
}
