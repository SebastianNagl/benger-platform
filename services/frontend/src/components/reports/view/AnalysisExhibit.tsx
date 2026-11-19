'use client'

/**
 * One exhibit of the report's Analyses section: the estimates an author
 * chose from an analysis run, drawn as a forest plot (one per contrast,
 * with the chosen equivalence band) or as the estimates table. The viewer
 * feeds it the estimates copied into the snapshot, the editor's preview the
 * live estimates of the run; both draw with the analysis components the
 * run page uses.
 */

import {
  bandAt,
  ContrastForest,
  groupLabel,
  plottableGroups,
} from '@/components/analysis/ContrastForestPlot'
import { EstimatesTable } from '@/components/analysis/EstimatesTable'
import type { AnalysisEstimate } from '@/lib/api/analysis'
import type { ReportExhibitType } from '@/types/report'
import { useMemo } from 'react'
import type { TranslateFn } from './chartTheme'
import { QuietNote } from './ReportSection'

export interface AnalysisExhibitProps {
  type: ReportExhibitType
  estimates: readonly Omit<AnalysisEstimate, 'id'>[]
  /** Bound set a forest draws (index into `tost`), or none. */
  band: number | null
  /** Numbered label, e.g. "Figure 1" or "Table 2". */
  label: string
  title?: string | null
  caption?: string | null
  t: TranslateFn
}

export function AnalysisExhibit({
  type,
  estimates,
  band,
  label,
  title,
  caption,
  t,
}: AnalysisExhibitProps) {
  const rows = estimates as readonly AnalysisEstimate[]
  const groups = useMemo(
    () => (type === 'forest' ? plottableGroups(rows) : []),
    [type, rows],
  )
  let body
  if (rows.length === 0) {
    body = <QuietNote>{t('reports.view.analyses.noEstimates')}</QuietNote>
  } else if (type === 'forest') {
    body =
      groups.length === 0 ? (
        <QuietNote>{t('analysis.forest.empty')}</QuietNote>
      ) : (
        <div className="space-y-5">
          {groups.map((group) => (
            <div key={group.key} className="break-inside-avoid-page">
              <p className="mb-1 font-mono text-xs [overflow-wrap:anywhere] text-zinc-600 dark:text-zinc-400">
                {groupLabel(group)}
              </p>
              <ContrastForest group={group} band={bandAt(group, band)} />
            </div>
          ))}
        </div>
      )
  } else {
    body = <EstimatesTable estimates={rows} compact />
  }
  return (
    <figure
      className="mt-5 min-w-0"
      data-testid="report-analysis-exhibit"
      data-exhibit-type={type}
    >
      <figcaption className="mb-2 text-sm text-zinc-900 dark:text-white">
        <span className="font-semibold">{label}</span>
        {title ? <span>{`: ${title}`}</span> : null}
      </figcaption>
      {body}
      {caption && (
        <p className="mt-2 text-xs leading-5 whitespace-pre-line text-zinc-600 dark:text-zinc-400">
          {caption}
        </p>
      )}
    </figure>
  )
}
