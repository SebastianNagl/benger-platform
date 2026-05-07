/**
 * Judge agreement heatmap (multi-run feature).
 *
 * Renders pairwise inter-judge agreement when ≥2 distinct judge_model_ids
 * scored the same items. The heatmap uses the same recharts/Plotly visual
 * pattern as `SignificanceHeatmap.tsx`. For numeric metrics this is the
 * Pearson correlation coefficient between judge means; for categorical
 * metrics it's Cohen's kappa.
 *
 * Hidden by the parent when fewer than 2 judges produced rows for the
 * selected metric (rendering a 1×1 self-correlation matrix is just noise).
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import dynamic from 'next/dynamic'
import { useMemo } from 'react'

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false })

export interface JudgeAgreementHeatmapProps {
  /** Distinct judge model ids — order is preserved as the matrix axes. */
  judgeModelIds: string[]
  metric: string
  /**
   * Pairwise scores keyed by `${judgeA}__${judgeB}` → number in [-1, 1] for
   * Pearson, [0, 1] for kappa. The endpoint emits a single triangle; the
   * component mirrors it across the diagonal automatically.
   */
  pairwise: Record<string, number>
  /** "pearson" → bipolar diverging palette; "kappa" → sequential 0..1. */
  scoreType: 'pearson' | 'kappa'
  /** Optional headline number (e.g. Fleiss kappa across all judges). */
  fleissKappa?: number | null
  height?: number
}

function buildMatrix(
  judges: string[],
  pairwise: Record<string, number>,
): { z: (number | null)[][]; text: string[][] } {
  const n = judges.length
  const z: (number | null)[][] = Array(n)
    .fill(null)
    .map(() => Array(n).fill(null))
  const text: string[][] = Array(n)
    .fill(null)
    .map(() => Array(n).fill(''))

  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      if (i === j) {
        z[i][j] = 1
        text[i][j] = '1.00'
        continue
      }
      const ja = judges[i]
      const jb = judges[j]
      const v = pairwise[`${ja}__${jb}`] ?? pairwise[`${jb}__${ja}`]
      if (v !== undefined && v !== null && !Number.isNaN(v)) {
        z[i][j] = v
        text[i][j] = v.toFixed(3)
      }
    }
  }
  return { z, text }
}

export function JudgeAgreementHeatmap({
  judgeModelIds,
  metric,
  pairwise,
  scoreType,
  fleissKappa,
  height = 360,
}: JudgeAgreementHeatmapProps) {
  const { t } = useI18n()

  // Strip null/empty/duplicate judge ids before rendering. The agreement
  // endpoint can return a judge id of `null` for deterministic-metric
  // catch-all judge_runs, and historical evals (pre-migration-044) carry
  // unrecovered NULLs too — surfacing those as a "None" axis label looks
  // like a UI bug. Dedupe also defends against the agreement helper
  // emitting the same model twice when two run_index values exist for
  // the same judge — the heatmap groups by model name, not (model, run).
  const cleanedJudges = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const id of judgeModelIds) {
      const s = (id ?? '').toString().trim()
      if (!s || s === 'null' || s === 'None' || seen.has(s)) continue
      seen.add(s)
      out.push(s)
    }
    return out
  }, [judgeModelIds])

  const { z, text } = useMemo(
    () => buildMatrix(cleanedJudges, pairwise),
    [cleanedJudges, pairwise],
  )

  if (cleanedJudges.length < 2) {
    // Either parent didn't filter, or we filtered the set below 2 here.
    // Either way there's no meaningful pairwise heatmap to render.
    return null
  }

  // Pearson is bipolar (-1..1, RdBu); kappa is sequential (0..1, Blues).
  const colorscale = scoreType === 'pearson' ? 'RdBu' : 'Blues'
  const zmin = scoreType === 'pearson' ? -1 : 0
  const zmax = 1

  return (
    <div className="rounded border border-zinc-200 bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mb-2 flex items-baseline justify-between">
        <h4 className="text-sm font-semibold text-zinc-900 dark:text-white">
          {scoreType === 'pearson'
            ? t('eval.judgeAgreement.titlePearson', 'Inter-Judge-Korrelation (Pearson)')
            : t('eval.judgeAgreement.titleKappa', 'Inter-Judge-Übereinstimmung (κ)')}
          <span className="ml-2 font-mono text-xs text-zinc-500">{metric}</span>
        </h4>
        {fleissKappa !== null && fleissKappa !== undefined && (
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            Fleiss κ = <span className="font-mono">{fleissKappa.toFixed(3)}</span>
          </span>
        )}
      </div>
      <Plot
        data={[
          {
            z,
            x: cleanedJudges,
            y: cleanedJudges,
            type: 'heatmap',
            colorscale,
            zmin,
            zmax,
            hoverongaps: false,
            text: text as any,
            texttemplate: '%{text}',
            textfont: { size: 11 },
            colorbar: {
              // Plotly v2+ requires title as a ColorBarTitle object, not a
              // bare string — `text` is the actual label field.
              title: { text: scoreType === 'pearson' ? 'r' : 'κ' },
              thickness: 12,
            },
          },
        ]}
        layout={{
          height,
          margin: { l: 100, r: 50, t: 10, b: 80 },
          xaxis: { tickangle: -30 },
          yaxis: { autorange: 'reversed' },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
      />
    </div>
  )
}
