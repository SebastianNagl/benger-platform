import { formatCount, formatNumber, formatRate } from '@/lib/reports/format'
import type {
  ReportHumanEvaluations,
  ReportLikertDimension,
} from '@/types/report'
import clsx from 'clsx'
import type { TranslateFn } from './chartTheme'
import { MISSING, NUM, RecordTable, TD, TH } from './records'
import { Prose, ReportSection, SubHeading } from './ReportSection'

/** Whether a snapshot holds any human evaluation to show. */
export function hasHumanEvaluations(
  human: ReportHumanEvaluations | undefined | null,
): boolean {
  return Boolean(
    human &&
    (human.likert.dimensions.length > 0 || human.preference.comparisons > 0),
  )
}

function MeanSd({
  mean,
  std,
  locale,
}: {
  mean: number | null
  std: number | null
  locale: string
}) {
  if (mean === null) return <>{MISSING}</>
  return (
    <>
      {formatNumber(mean, locale, 2, 2)}
      {std !== null && (
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {' '}
          ± {formatNumber(std, locale, 2, 2)}
        </span>
      )}
    </>
  )
}

/** Ratings per scale point as a stacked bar, with the counts as its label. */
function RatingBar({
  dimension,
  scale,
  t,
}: {
  dimension: ReportLikertDimension
  scale: number[]
  t: TranslateFn
}) {
  const total = dimension.distribution.reduce((a, b) => a + b, 0)
  const label = scale
    .map((point, i) =>
      t('reports.view.records.ratingCount', {
        point,
        count: dimension.distribution[i] ?? 0,
      }),
    )
    .join(', ')
  return (
    <div className="min-w-32" role="img" aria-label={label} title={label}>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
        {scale.map((point, i) => {
          const n = dimension.distribution[i] ?? 0
          if (!total || !n) return null
          return (
            <div
              key={point}
              data-print-keep
              style={{ width: `${(n / total) * 100}%` }}
              className={clsx(
                'h-full',
                [
                  'bg-zinc-400 dark:bg-zinc-500',
                  'bg-emerald-200 dark:bg-emerald-900',
                  'bg-emerald-300 dark:bg-emerald-700',
                  'bg-emerald-500 dark:bg-emerald-500',
                  'bg-emerald-700 dark:bg-emerald-300',
                ][Math.min(i, 4)],
              )}
            />
          )
        })}
      </div>
      <div className="mt-1 text-xs whitespace-nowrap text-zinc-500 tabular-nums dark:text-zinc-400">
        {scale
          .map((point, i) =>
            t('reports.view.records.ratingCount', {
              point,
              count: dimension.distribution[i] ?? 0,
            }),
          )
          .join(' · ')}
      </div>
    </div>
  )
}

/** Human evaluation results: Likert ratings and preference comparisons. */
export function HumanEvaluationSection({
  human,
  locale,
  t,
}: {
  human: ReportHumanEvaluations | undefined | null
  locale: string
  t: TranslateFn
}) {
  if (!human || !hasHumanEvaluations(human)) return null
  const { likert, preference } = human
  const scaleMin = likert.scale[0] ?? 1
  const scaleMax = likert.scale[likert.scale.length - 1] ?? 5

  // Models × dimensions matrix of mean ratings.
  const modelIds: string[] = []
  const modelLabels: Record<string, string> = {}
  for (const d of likert.dimensions) {
    for (const m of d.by_model) {
      if (!(m.model_id in modelLabels)) {
        modelIds.push(m.model_id)
        modelLabels[m.model_id] = m.label
      }
    }
  }
  modelIds.sort((a, b) => modelLabels[a].localeCompare(modelLabels[b]))

  return (
    <ReportSection
      title={t('reports.view.records.humanEvaluation')}
      id="human-evaluation"
    >
      {likert.dimensions.length > 0 && (
        <div className="mb-8" data-testid="likert">
          <SubHeading>
            {t('reports.view.records.likertTitle', {
              min: scaleMin,
              max: scaleMax,
            })}
          </SubHeading>
          <Prose>
            {t('reports.view.records.likertSummary', {
              ratings: formatCount(likert.rating_count, locale),
              evaluators: formatCount(likert.evaluator_count, locale),
            })}
          </Prose>
          <div className="mt-3">
            <RecordTable
              testId="likert-dimensions"
              head={
                <>
                  <th scope="col" className={TH}>
                    {t('reports.view.records.dimension')}
                  </th>
                  <th scope="col" className={clsx(TH, NUM)}>
                    {t('reports.view.records.meanSd')}
                  </th>
                  <th scope="col" className={clsx(TH, NUM)}>
                    n
                  </th>
                  <th scope="col" className={TH}>
                    {t('reports.view.records.ratingDistribution', {
                      min: scaleMin,
                      max: scaleMax,
                    })}
                  </th>
                </>
              }
            >
              {likert.dimensions.map((d) => (
                <tr key={d.dimension} data-testid="likert-row">
                  <td className={clsx(TD, 'min-w-44 align-top')}>
                    <div className="font-medium text-zinc-900 dark:text-white">
                      {d.dimension}
                    </div>
                    {d.description && (
                      <div className="text-xs text-zinc-500 dark:text-zinc-400">
                        {d.description}
                      </div>
                    )}
                  </td>
                  <td className={clsx(TD, NUM, 'align-top whitespace-nowrap')}>
                    <MeanSd mean={d.mean} std={d.std} locale={locale} />
                  </td>
                  <td className={clsx(TD, NUM, 'align-top')}>
                    {formatCount(d.n, locale)}
                  </td>
                  <td className={clsx(TD, 'align-top')}>
                    <RatingBar dimension={d} scale={likert.scale} t={t} />
                  </td>
                </tr>
              ))}
            </RecordTable>
          </div>

          {modelIds.length > 0 && (
            <div className="mt-4">
              <RecordTable
                testId="likert-models"
                head={
                  <>
                    <th scope="col" className={TH}>
                      {t('reports.view.model')}
                    </th>
                    {likert.dimensions.map((d) => (
                      <th
                        key={d.dimension}
                        scope="col"
                        className={clsx(TH, NUM)}
                      >
                        {d.dimension}
                      </th>
                    ))}
                  </>
                }
              >
                {modelIds.map((id) => (
                  <tr key={id} data-testid="likert-model-row">
                    <td className={clsx(TD, 'font-medium')}>
                      {modelLabels[id]}
                    </td>
                    {likert.dimensions.map((d) => {
                      const cell = d.by_model.find((m) => m.model_id === id)
                      return (
                        <td
                          key={d.dimension}
                          className={clsx(TD, NUM, 'whitespace-nowrap')}
                        >
                          {cell ? (
                            <>
                              {cell.mean === null
                                ? MISSING
                                : formatNumber(cell.mean, locale, 2, 2)}
                              <span className="text-xs text-zinc-500 dark:text-zinc-400">
                                {' '}
                                (n = {formatCount(cell.n, locale)})
                              </span>
                            </>
                          ) : (
                            MISSING
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </RecordTable>
            </div>
          )}
        </div>
      )}

      {preference.comparisons > 0 && (
        <div data-testid="preference">
          <SubHeading>{t('reports.view.records.preferenceTitle')}</SubHeading>
          <Prose>
            {t('reports.view.records.preferenceSummary', {
              comparisons: formatCount(preference.comparisons, locale),
              evaluators: formatCount(preference.evaluator_count, locale),
              ties: formatCount(preference.ties, locale),
            })}
          </Prose>
          {preference.models.length > 0 && (
            <div className="mt-3">
              <RecordTable
                testId="preference-models"
                head={
                  <>
                    <th scope="col" className={TH}>
                      {t('reports.view.model')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.winRate')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.wins')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.losses')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.ties')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.comparisons')}
                    </th>
                  </>
                }
              >
                {preference.models.map((m) => (
                  <tr key={m.model_id} data-testid="preference-row">
                    <td className={clsx(TD, 'font-medium')}>{m.label}</td>
                    <td className={clsx(TD, NUM, 'font-semibold')}>
                      {formatRate(m.win_rate, locale)}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(m.wins, locale)}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(m.losses, locale)}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(m.ties, locale)}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(m.comparisons, locale)}
                    </td>
                  </tr>
                ))}
              </RecordTable>
            </div>
          )}
          {preference.pairs.length > 0 && (
            <div className="mt-4">
              <RecordTable
                testId="preference-pairs"
                head={
                  <>
                    <th scope="col" className={TH}>
                      {t('reports.view.records.pair')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.firstWins')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.ties')}
                    </th>
                    <th scope="col" className={clsx(TH, NUM)}>
                      {t('reports.view.records.secondWins')}
                    </th>
                  </>
                }
              >
                {preference.pairs.map((p) => (
                  <tr key={`${p.model_a}|${p.model_b}`}>
                    <td className={TD}>
                      {t('reports.view.records.pairLabel', {
                        a: p.label_a,
                        b: p.label_b,
                      })}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(p.a_wins, locale)}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(p.ties, locale)}
                    </td>
                    <td className={clsx(TD, NUM)}>
                      {formatCount(p.b_wins, locale)}
                    </td>
                  </tr>
                ))}
              </RecordTable>
            </div>
          )}
        </div>
      )}
    </ReportSection>
  )
}
