import clsx from 'clsx'
import { formatCount, formatGradePoints, formatMetricValue, formatRate } from '@/lib/reports/format'
import type { RankedRow } from '@/lib/reports/select'
import type { ReportMetricScale } from '@/types/report'
import type { TranslateFn } from './chartTheme'
import { QuietNote, SubHeading } from './ReportSection'

export interface MetricColumn {
  id: string
  label: string
  scale: ReportMetricScale
}

interface RankingTableProps {
  title: string
  rows: RankedRow[]
  primary: MetricColumn
  /** Present when the primary metric has a 0-18 companion. */
  gradeMetric?: string | null
  /** Additional per-metric columns (already filtered; never hidden companions). */
  otherColumns?: MetricColumn[]
  /** Header of the subject column ("Modell" / "Teilnehmende"). */
  subjectHeader: string
  locale: string
  t: TranslateFn
  testId?: string
}

function RankBadge({ rank }: { rank: number }) {
  const podium = rank <= 3
  return (
    <span
      data-testid="rank-badge"
      className={clsx(
        'inline-flex h-7 min-w-7 items-center justify-center rounded-full px-2 text-xs font-semibold tabular-nums',
        rank === 1 && 'bg-emerald-600 text-white dark:bg-emerald-500 dark:text-zinc-950',
        rank === 2 && 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
        rank === 3 && 'bg-zinc-200 text-zinc-800 dark:bg-zinc-700 dark:text-zinc-100',
        !podium && 'text-zinc-500 dark:text-zinc-400',
      )}
    >
      {rank}
    </span>
  )
}

const TH = 'px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400'
const TD = 'px-3 py-2 text-sm text-zinc-800 dark:text-zinc-200'
const NUM = 'text-right tabular-nums'

/** Ranked table of subjects for one config; ranks come from the rows, never from position. */
export function RankingTable({
  title,
  rows,
  primary,
  gradeMetric,
  otherColumns = [],
  subjectHeader,
  locale,
  t,
  testId = 'ranking-table',
}: RankingTableProps) {
  const hasPassRate = rows.some((r) => r.primary.pass_rate !== null && r.primary.pass_rate !== undefined)
  const hasGrade = Boolean(gradeMetric) && rows.some((r) => gradeMetric && r.metrics[gradeMetric])

  return (
    <div className="mb-8" data-testid={testId}>
      <SubHeading>{title}</SubHeading>
      {rows.length === 0 ? (
        <QuietNote>
          {t('reports.view.noSeries', 'Für diese Metrik liegen keine Werte vor.')}
        </QuietNote>
      ) : (
        <div className="overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-800">
          <table className="min-w-full divide-y divide-zinc-200 dark:divide-zinc-800">
            <thead className="bg-zinc-50 dark:bg-zinc-900/60">
              <tr>
                <th scope="col" className={clsx(TH, 'w-14')}>
                  {t('reports.view.rank', 'Rang')}
                </th>
                <th scope="col" className={TH}>
                  {subjectHeader}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {primary.label}
                </th>
                {hasGrade && (
                  <th scope="col" className={clsx(TH, NUM)}>
                    {t('reports.view.gradePoints', 'Notenpunkte')}
                  </th>
                )}
                {hasPassRate && (
                  <th scope="col" className={clsx(TH, NUM)}>
                    {t('reports.view.passRate', 'Bestanden')}
                  </th>
                )}
                <th scope="col" className={clsx(TH, NUM)}>
                  n
                </th>
                {otherColumns.map((col) => (
                  <th key={col.id} scope="col" className={clsx(TH, NUM)}>
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-900">
              {rows.map((row) => (
                <tr key={row.subject.id} data-testid="ranking-row" data-subject={row.subject.id}>
                  <td className={TD}>
                    <RankBadge rank={row.rank} />
                  </td>
                  <td className={TD}>
                    <div className="font-medium text-zinc-900 dark:text-white">{row.subject.label}</div>
                    {row.subject.provider && (
                      <div className="text-xs text-zinc-500 dark:text-zinc-400">{row.subject.provider}</div>
                    )}
                  </td>
                  <td className={clsx(TD, NUM, 'font-semibold')}>
                    {formatMetricValue(row.primary.mean, primary.scale, locale)}
                  </td>
                  {hasGrade && (
                    <td className={clsx(TD, NUM)}>
                      {formatGradePoints(gradeMetric ? row.metrics[gradeMetric]?.mean : null, locale)}
                    </td>
                  )}
                  {hasPassRate && (
                    <td className={clsx(TD, NUM)}>{formatRate(row.primary.pass_rate, locale)}</td>
                  )}
                  <td className={clsx(TD, NUM)}>{formatCount(row.primary.n, locale)}</td>
                  {otherColumns.map((col) => (
                    <td key={col.id} className={clsx(TD, NUM)}>
                      {formatMetricValue(row.metrics[col.id]?.mean, col.scale, locale)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
