'use client'

/**
 * The report's Analyses section: per analysis run the author picked, the
 * author's title and text, the run's metadata, its multiplicity families
 * and warnings, and its exhibits (forest plots and tables), numbered across
 * the report like a paper's figures and tables.
 *
 * Numbers come from the snapshot only (`snapshot.analyses`, copied on
 * publish or refresh); titles, texts and captions are the author's live
 * prose (`content.sections.analyses`), matched by run and exhibit id.
 */

import type { AnalysesSection as AnalysesContent } from '@/lib/api/reports'
import { exhibitEstimates } from '@/lib/reports/analyses'
import { formatCount, formatDate } from '@/lib/reports/format'
import type { ReportAnalysesSnapshot } from '@/types/report'
import Link from 'next/link'
import { AnalysisExhibit } from './AnalysisExhibit'
import type { TranslateFn } from './chartTheme'
import { HashValue } from './records'
import { Prose, ReportSection, SubHeading } from './ReportSection'

const KNOWN_METHODS = new Set(['holm', 'bonferroni', 'bh'])

/** Whether a snapshot has anything for the Analyses section to show. */
export function hasAnalyses(
  analyses: ReportAnalysesSnapshot | null | undefined,
): boolean {
  return (analyses?.runs?.length ?? 0) > 0
}

export function AnalysesSection({
  analyses,
  content,
  locale,
  t,
  runHref,
}: {
  analyses: ReportAnalysesSnapshot | null | undefined
  content?: AnalysesContent | null
  locale: string
  t: TranslateFn
  /** Link to a run's page, for readers who may open it (authors). */
  runHref?: ((runId: string) => string) | null
}) {
  if (!analyses || !hasAnalyses(analyses)) return null
  const prose = new Map((content?.runs ?? []).map((r) => [r.run_id, r]))
  let figures = 0
  let tables = 0
  return (
    <ReportSection title={t('reports.view.analyses.title')} id="analyses">
      {content?.custom_text && (
        <div className="mb-6">
          <Prose>{content.custom_text}</Prose>
        </div>
      )}
      <div className="space-y-10">
        {analyses.runs.map((run) => {
          const runProse = prose.get(run.id)
          const exhibitProse = new Map(
            (runProse?.exhibits ?? []).map((e) => [e.id, e]),
          )
          const completed = formatDate(run.completed_at, locale)
          return (
            <article
              key={run.id}
              className="min-w-0"
              data-testid="report-analysis-run"
              data-run-id={run.id}
            >
              <SubHeading>{runProse?.title || run.name}</SubHeading>
              <div className="-mt-1 mb-3 space-y-1 text-xs text-zinc-500 dark:text-zinc-400">
                <p>
                  {t('reports.view.analyses.runMeta', {
                    name: run.name,
                    date: completed || '–',
                    rows: formatCount(run.frame_rows ?? 0, locale),
                    estimates: formatCount(run.estimates_count, locale),
                    engine: run.engine_version,
                  })}
                </p>
                <p className="flex flex-wrap items-start gap-x-2">
                  <span>{t('reports.view.analyses.specHash')}</span>
                  <HashValue
                    value={run.spec_hash}
                    label={t('reports.view.records.copyHash')}
                  />
                </p>
              </div>
              {runProse?.text && <Prose>{runProse.text}</Prose>}
              {run.families.length > 0 && (
                <p
                  className="mt-3 text-sm text-zinc-700 dark:text-zinc-300"
                  data-testid="report-analysis-families"
                >
                  <span className="font-medium">
                    {t('reports.view.analyses.families')}
                  </span>{' '}
                  {run.families
                    .map((f) =>
                      t('reports.view.analyses.family', {
                        family: f.family,
                        method:
                          f.method && KNOWN_METHODS.has(f.method)
                            ? t(`analysis.methods.${f.method}`)
                            : (f.method ?? '–'),
                        size: formatCount(f.size ?? 0, locale),
                      }),
                    )
                    .join('; ')}
                </p>
              )}
              {run.warnings.length > 0 && (
                <div
                  className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-200"
                  data-testid="report-analysis-warnings"
                >
                  <p className="font-medium">
                    {t('reports.view.analyses.warnings')}
                  </p>
                  <ul className="mt-1 list-disc pl-5 [overflow-wrap:anywhere]">
                    {run.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
              {run.truncated && (
                <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('reports.view.analyses.truncated')}
                </p>
              )}
              {run.exhibits.map((exhibit) => {
                const label =
                  exhibit.type === 'forest'
                    ? t('reports.view.analyses.figure', { n: ++figures })
                    : t('reports.view.analyses.table', { n: ++tables })
                const text = exhibitProse.get(exhibit.id)
                return (
                  <AnalysisExhibit
                    key={exhibit.id}
                    type={exhibit.type}
                    estimates={exhibitEstimates(run, exhibit.positions)}
                    band={exhibit.band}
                    label={label}
                    title={text?.title}
                    caption={text?.caption}
                    t={t}
                  />
                )
              })}
              {runHref && (
                <p className="mt-4 text-sm print:hidden">
                  <Link
                    href={runHref(run.id)}
                    className="font-medium text-emerald-700 hover:underline dark:text-emerald-400"
                  >
                    {t('reports.view.analyses.openRun')}
                  </Link>
                </p>
              )}
            </article>
          )
        })}
      </div>
    </ReportSection>
  )
}
