import { formatCount, formatNumber, formatRate } from '@/lib/reports/format'
import type { ReportGenerationSection } from '@/types/report'
import clsx from 'clsx'
import type { TranslateFn } from './chartTheme'
import { MISSING, NUM, RecordTable, TD, TH } from './records'
import { SubHeading } from './ReportSection'

/** Per-model generation counts and outcome rates, inside the Generation section. */
export function GenerationDetails({
  generation,
  locale,
  t,
}: {
  generation: ReportGenerationSection | undefined
  locale: string
  t: TranslateFn
}) {
  if (!generation || generation.models.length === 0) return null
  const anyParsed = generation.models.some((m) => m.parse_attempted > 0)
  // Refusal, retry and request record shares exist only in a snapshot
  // built with variant_experiments.
  const fidelity = generation.models.some((m) => m.refusal_rate !== undefined)
  const rate = (value: number | null | undefined) =>
    formatRate(value ?? null, locale)
  return (
    <div className="mt-6" data-testid="generation-details">
      <SubHeading>{t('reports.view.records.generationPerModel')}</SubHeading>
      <RecordTable
        testId="generation-table"
        head={
          <>
            <th scope="col" className={TH}>
              {t('reports.view.model')}
            </th>
            <th scope="col" className={clsx(TH, NUM)}>
              {t('reports.view.records.generations')}
            </th>
            <th scope="col" className={clsx(TH, NUM)}>
              {t('reports.view.records.runsPerTask')}
            </th>
            {fidelity && (
              <th scope="col" className={clsx(TH, NUM)}>
                {t('reports.view.records.refusals')}
              </th>
            )}
            {anyParsed && (
              <th scope="col" className={clsx(TH, NUM)}>
                {t('reports.view.records.parseFailures')}
              </th>
            )}
            {fidelity && (
              <>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.records.retries')}
                </th>
                <th scope="col" className={clsx(TH, NUM)}>
                  {t('reports.view.records.requestRecords')}
                </th>
              </>
            )}
            <th scope="col" className={TH}>
              {t('reports.view.records.structures')}
            </th>
          </>
        }
      >
        {generation.models.map((m) => (
          <tr
            key={m.model_id}
            data-testid="generation-row"
            data-model={m.model_id}
          >
            <td className={clsx(TD, 'min-w-40 align-top')}>
              <div className="font-medium text-zinc-900 dark:text-white">
                {m.label}
              </div>
              {m.provider && (
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {m.provider}
                </div>
              )}
            </td>
            <td className={clsx(TD, NUM, 'align-top')}>
              {formatCount(m.generations, locale)}
              {m.failed > 0 && (
                <div className="text-xs text-zinc-500 dark:text-zinc-400">
                  {t('reports.view.records.failedCount', {
                    count: formatCount(m.failed, locale),
                  })}
                </div>
              )}
            </td>
            <td className={clsx(TD, NUM, 'align-top')}>
              {m.runs_per_task === null
                ? MISSING
                : formatNumber(m.runs_per_task, locale, 1)}
            </td>
            {fidelity && (
              <td className={clsx(TD, NUM, 'align-top')}>
                {rate(m.refusal_rate)}
              </td>
            )}
            {anyParsed && (
              <td className={clsx(TD, NUM, 'align-top')}>
                {rate(m.parse_failure_rate)}
              </td>
            )}
            {fidelity && (
              <>
                <td className={clsx(TD, NUM, 'align-top')}>
                  {rate(m.retry_rate)}
                </td>
                <td className={clsx(TD, NUM, 'align-top')}>
                  {rate(m.request_record_share)}
                </td>
              </>
            )}
            <td className={clsx(TD, 'align-top')}>
              {m.structures.length === 0
                ? MISSING
                : m.structures
                    .map((s) => s.key ?? t('reports.view.records.noStructure'))
                    .join(', ')}
            </td>
          </tr>
        ))}
      </RecordTable>
      <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
        {t('reports.view.records.generationRatesHint')}
      </p>
    </div>
  )
}
