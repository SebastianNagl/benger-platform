/**
 * Inter-annotator agreement per control (presentation only).
 *
 * Plain props, so the evaluations page (live numbers) and the report viewer
 * (numbers frozen in the snapshot) render the same view. Choices and rating
 * controls show Fleiss' kappa, the mean of the pairwise Cohen's kappas and
 * percent agreement; number controls show the mean pairwise Pearson's r and
 * the mean absolute deviation. Each control lists its annotator pairs in a
 * collapsible table. The parent hides the component when no task has two
 * annotators (`hasAgreement`).
 */

'use client'

import { useI18n } from '@/contexts/I18nContext'
import type {
  AnnotatorAgreementSummary,
  ControlAgreement,
} from '@/lib/api/agreement'
import { formatDecimal } from '@/lib/i18n/locales'
import { formatCount } from '@/lib/reports/format'

/** Landis and Koch (1977) bands, the reading `bg_statistics` uses. */
export type KappaBand =
  'poor' | 'slight' | 'fair' | 'moderate' | 'substantial' | 'almostPerfect'

export function kappaBand(kappa: number): KappaBand {
  if (kappa < 0) return 'poor'
  if (kappa < 0.2) return 'slight'
  if (kappa < 0.4) return 'fair'
  if (kappa < 0.6) return 'moderate'
  if (kappa < 0.8) return 'substantial'
  return 'almostPerfect'
}

interface AnnotatorAgreementProps {
  agreement: AnnotatorAgreementSummary
}

function Stat({
  label,
  value,
  hint,
  testId,
}: {
  label: string
  value: string
  hint?: string
  testId?: string
}) {
  return (
    <div
      className="min-w-0 rounded-md bg-zinc-50 px-3 py-2 dark:bg-zinc-800/60"
      data-testid={testId}
    >
      <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold text-zinc-900 tabular-nums dark:text-white">
        {value}
      </dd>
      {hint && (
        <dd className="text-xs text-zinc-500 dark:text-zinc-400">{hint}</dd>
      )}
    </div>
  )
}

function ControlBlock({ control }: { control: ControlAgreement }) {
  const { t, locale } = useI18n()
  const dash = '-'
  const num = (v: number | null | undefined, digits = 2) =>
    v === null || v === undefined ? dash : formatDecimal(v, locale, digits)
  const pct = (v: number | null | undefined) =>
    v === null || v === undefined
      ? dash
      : `${formatDecimal(v * 100, locale, 1)} %`
  const band = (v: number | null | undefined) =>
    v === null || v === undefined
      ? undefined
      : t(`evaluation.annotatorAgreement.bands.${kappaBand(v)}`)
  const numeric = control.score_type === 'numeric'
  const typeLabel = t(
    `evaluation.annotatorAgreement.types.${
      ['choices', 'rating', 'number'].includes(control.type)
        ? control.type
        : 'other'
    }`,
  )

  return (
    <section
      className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700"
      data-testid={`agreement-control-${control.control}`}
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="font-mono text-sm font-semibold break-all text-zinc-900 dark:text-white">
          {control.control}
        </h4>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {t('evaluation.annotatorAgreement.controlMeta', {
            type: typeLabel,
            tasks: formatCount(control.n_items, locale),
            annotators: formatCount(control.n_annotators, locale),
          })}
        </p>
      </div>

      <dl className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-2 sm:grid-cols-3">
        {numeric ? (
          <>
            <Stat
              label={t('evaluation.annotatorAgreement.pearsonMean')}
              value={num(control.pearson_r_mean)}
              testId="agreement-pearson"
            />
            <Stat
              label={t('evaluation.annotatorAgreement.meanAbsoluteDeviation')}
              value={num(control.mean_absolute_deviation)}
              testId="agreement-mad"
            />
          </>
        ) : (
          <>
            <Stat
              label={t('evaluation.annotatorAgreement.fleissKappa')}
              value={num(control.fleiss_kappa)}
              hint={band(control.fleiss_kappa)}
              testId="agreement-fleiss"
            />
            <Stat
              label={t('evaluation.annotatorAgreement.cohensKappaMean')}
              value={num(control.cohens_kappa_mean)}
              hint={band(control.cohens_kappa_mean)}
              testId="agreement-cohen"
            />
            <Stat
              label={t('evaluation.annotatorAgreement.percentAgreement')}
              value={pct(control.percent_agreement)}
              testId="agreement-percent"
            />
          </>
        )}
      </dl>

      {control.multi_select && (
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          {t('evaluation.annotatorAgreement.multiSelectNote')}
        </p>
      )}

      {control.pairs.length > 0 && (
        <details className="group mt-3">
          <summary className="cursor-pointer text-sm font-medium text-zinc-700 select-none dark:text-zinc-300">
            {t('evaluation.annotatorAgreement.pairs', {
              count: formatCount(control.pairs_total, locale),
            })}
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[20rem] text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-700 dark:text-zinc-400">
                  <th className="py-1.5 pr-3 font-medium">
                    {t('evaluation.annotatorAgreement.annotatorA')}
                  </th>
                  <th className="py-1.5 pr-3 font-medium">
                    {t('evaluation.annotatorAgreement.annotatorB')}
                  </th>
                  <th className="py-1.5 pr-3 text-right font-medium">
                    {t('evaluation.annotatorAgreement.sharedTasks')}
                  </th>
                  <th className="py-1.5 text-right font-medium">
                    {numeric
                      ? t('evaluation.annotatorAgreement.pearson')
                      : t('evaluation.annotatorAgreement.cohensKappa')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {control.pairs.map((p) => (
                  <tr
                    key={`${p.annotator_a}|${p.annotator_b}`}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="py-1.5 pr-3 text-zinc-800 dark:text-zinc-200">
                      {p.annotator_a}
                    </td>
                    <td className="py-1.5 pr-3 text-zinc-800 dark:text-zinc-200">
                      {p.annotator_b}
                    </td>
                    <td className="py-1.5 pr-3 text-right text-zinc-600 tabular-nums dark:text-zinc-400">
                      {formatCount(p.n_items, locale)}
                    </td>
                    <td className="py-1.5 text-right text-zinc-900 tabular-nums dark:text-white">
                      {num(numeric ? p.pearson_r : p.cohens_kappa)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {control.pairs_total > control.pairs.length && (
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              {t('evaluation.annotatorAgreement.pairsTruncated', {
                shown: formatCount(control.pairs.length, locale),
                total: formatCount(control.pairs_total, locale),
              })}
            </p>
          )}
        </details>
      )}
    </section>
  )
}

export function AnnotatorAgreement({ agreement }: AnnotatorAgreementProps) {
  const { t, locale } = useI18n()
  const unsupported = agreement.unsupported_controls ?? []
  return (
    <div className="space-y-4" data-testid="annotator-agreement">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        {t('evaluation.annotatorAgreement.summary', {
          tasks: formatCount(agreement.overlap_task_count, locale),
          annotators: formatCount(agreement.annotator_count, locale),
        })}
      </p>
      {agreement.controls.map((control) => (
        <ControlBlock key={control.control} control={control} />
      ))}
      {unsupported.length > 0 && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {t('evaluation.annotatorAgreement.unsupported', {
            controls: unsupported.map((c) => c.control).join(', '),
          })}
        </p>
      )}
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        {t('evaluation.annotatorAgreement.methodNote')}
      </p>
    </div>
  )
}
