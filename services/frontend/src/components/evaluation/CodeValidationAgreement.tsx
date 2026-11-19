/**
 * The agreement of one code validation (presentation only): Cohen's kappa
 * of the automatic code against the human reference with its Landis and
 * Koch band, observed and chance agreement, the compared items, precision,
 * recall and F1 per category (the human reference as truth) and the
 * agreement between the human coders.
 *
 * Plain props, so the evaluations page (a live validation) and the report
 * viewer (a validation frozen in the snapshot) render the same view. Every
 * number is the stored one; nothing is recomputed here.
 */

'use client'

import { kappaBand } from '@/components/evaluation/AnnotatorAgreement'
import { useI18n } from '@/contexts/I18nContext'
import type {
  BetweenCoders,
  CategoryAgreement,
  CodeValidationMetrics,
} from '@/lib/api/coding'
import { formatDecimal } from '@/lib/i18n/locales'
import { formatCount } from '@/lib/reports/format'
import type { ReportCodeValidation } from '@/types/report'

/** The numbers the view shows, from either source. */
export interface ValidationAgreementData {
  kappa: number | null
  observedAgreement: number | null
  expectedAgreement: number | null
  compared: number | null
  items: number | null
  ties: number | null
  missingAutomatic: number | null
  /** How a missing automatic code counts: `category` or `exclude`. */
  missing: string | null
  categories: string[]
  perCategory: Record<string, CategoryAgreement>
  betweenCoders: BetweenCoders | null
}

/** The view of a stored validation's `metrics`. */
export function validationAgreementFromMetrics(
  metrics: CodeValidationMetrics,
): ValidationAgreementData {
  const main = metrics.automatic_vs_reference ?? ({} as never)
  const between = metrics.between_coders
  return {
    kappa: main.kappa ?? null,
    observedAgreement: main.observed_agreement ?? null,
    expectedAgreement: main.expected_agreement ?? null,
    compared: metrics.compared ?? null,
    items: metrics.items ?? null,
    ties: metrics.ties ?? null,
    missingAutomatic: metrics.missing_automatic ?? null,
    missing: metrics.missing ?? null,
    categories: metrics.categories ?? [],
    perCategory: main.per_category ?? {},
    betweenCoders: between
      ? {
          coders: between.coders ?? null,
          items: between.items ?? null,
          fleiss_kappa: between.fleiss_kappa ?? null,
          percent_agreement: between.percent_agreement ?? null,
        }
      : null,
  }
}

/** The view of a validation frozen in a report snapshot. Without the
 *  stored row's detail it shows what the run accepted. */
export function validationAgreementFromReport(
  v: ReportCodeValidation,
): ValidationAgreementData {
  return {
    kappa: v.agreement?.kappa ?? v.kappa,
    observedAgreement: v.agreement?.observed_agreement ?? v.observed_agreement,
    expectedAgreement: v.agreement?.expected_agreement ?? null,
    compared: v.counts?.compared ?? v.compared,
    items: v.counts?.items ?? null,
    ties: v.counts?.ties ?? null,
    missingAutomatic: v.counts?.missing_automatic ?? null,
    missing: v.counts?.missing ?? null,
    categories: v.categories ?? [],
    perCategory: v.per_category ?? {},
    betweenCoders: v.between_coders ?? null,
  }
}

const DASH = '-'

/** How the note on items without an automatic code reads. */
function missingKey(missing: string | null, one: boolean): string {
  if (missing === 'exclude') {
    return one
      ? 'evaluation.agreementValidity.missingExcludedOne'
      : 'evaluation.agreementValidity.missingExcluded'
  }
  return one
    ? 'evaluation.agreementValidity.missingCategoryOne'
    : 'evaluation.agreementValidity.missingCategory'
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

const th =
  'px-3 py-2 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'
const cell =
  'px-3 py-1.5 text-right font-mono text-xs whitespace-nowrap text-zinc-800 dark:text-zinc-200'

export function CodeValidationAgreement({
  data,
}: {
  data: ValidationAgreementData
}) {
  const { t, locale } = useI18n()
  const dec = (v: number | null | undefined, digits = 2) =>
    v === null || v === undefined ? DASH : formatDecimal(v, locale, digits)
  const pct = (v: number | null | undefined) =>
    v === null || v === undefined
      ? DASH
      : `${formatDecimal(v * 100, locale, 1)} %`
  const count = (v: number | null | undefined) =>
    v === null || v === undefined ? DASH : formatCount(v, locale)
  const categories = data.categories.filter((c) => data.perCategory[c])
  const between = data.betweenCoders

  return (
    <div className="space-y-3" data-testid="code-validation-agreement">
      <dl className="grid grid-cols-1 gap-2 min-[420px]:grid-cols-2 sm:grid-cols-4">
        <Stat
          label={t('evaluation.agreementValidity.kappa')}
          value={dec(data.kappa)}
          hint={
            data.kappa === null
              ? undefined
              : t(
                  `evaluation.annotatorAgreement.bands.${kappaBand(data.kappa)}`,
                )
          }
          testId="validation-kappa"
        />
        <Stat
          label={t('evaluation.agreementValidity.observed')}
          value={pct(data.observedAgreement)}
          testId="validation-observed"
        />
        <Stat
          label={t('evaluation.agreementValidity.expected')}
          value={pct(data.expectedAgreement)}
          testId="validation-expected"
        />
        <Stat
          label={t('evaluation.agreementValidity.compared')}
          value={count(data.compared)}
          hint={
            data.items === null
              ? undefined
              : t('evaluation.agreementValidity.ofItems', {
                  items: count(data.items),
                })
          }
          testId="validation-compared"
        />
      </dl>

      {categories.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table
            className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800"
            data-testid="validation-categories"
          >
            <thead className="bg-zinc-50 dark:bg-zinc-900/40">
              <tr>
                <th className={th}>
                  {t('evaluation.agreementValidity.category')}
                </th>
                <th className={`${th} text-right`}>
                  {t('evaluation.agreementValidity.support')}
                </th>
                <th className={`${th} text-right`}>
                  {t('evaluation.agreementValidity.precision')}
                </th>
                <th className={`${th} text-right`}>
                  {t('evaluation.agreementValidity.recall')}
                </th>
                <th className={`${th} text-right`}>F1</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
              {categories.map((c) => {
                const m = data.perCategory[c]
                return (
                  <tr key={c} data-testid="validation-category-row">
                    <td className="max-w-[14rem] px-3 py-1.5 font-mono text-xs [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
                      {c}
                    </td>
                    <td className={cell}>{count(m.support)}</td>
                    <td className={cell}>{dec(m.precision)}</td>
                    <td className={cell}>{dec(m.recall)}</td>
                    <td className={cell}>{dec(m.f1)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <ul className="space-y-0.5 text-xs text-zinc-500 dark:text-zinc-400">
        {(data.ties ?? 0) > 0 && (
          <li>
            {data.ties === 1
              ? t('evaluation.agreementValidity.tiesOne')
              : t('evaluation.agreementValidity.ties', {
                  count: count(data.ties),
                })}
          </li>
        )}
        {(data.missingAutomatic ?? 0) > 0 && (
          <li>
            {t(missingKey(data.missing, data.missingAutomatic === 1), {
              count: count(data.missingAutomatic),
            })}
          </li>
        )}
        {between && (between.coders ?? 0) >= 2 && (
          <li data-testid="validation-between-coders">
            {t(
              between.items === 1
                ? 'evaluation.agreementValidity.betweenCodersOne'
                : 'evaluation.agreementValidity.betweenCoders',
              {
                coders: count(between.coders),
                items: count(between.items),
                kappa: dec(between.fleiss_kappa),
                agreement: pct(between.percent_agreement),
              },
            )}
          </li>
        )}
      </ul>
    </div>
  )
}

/** A short form of a 64-character hash. */
export function shortHash(hash: string | null | undefined): string {
  return hash ? hash.slice(0, 12) : DASH
}

/** A code's ref with its version, unless the ref already names it. */
export function codeLabel(
  ref: string | null | undefined,
  version: string | null | undefined,
  t: (key: string, vars?: Record<string, string | number>) => string,
): string {
  if (!ref)
    return version
      ? t('evaluation.agreementValidity.version', { version })
      : DASH
  if (!version || ref.includes(`@${version}`)) return ref
  return `${ref} (${t('evaluation.agreementValidity.version', { version })})`
}

/** The translation key of a code kind (text pattern, coder, judge code). */
export function codeKindKey(kind: string | null | undefined): string {
  return `evaluation.agreementValidity.kinds.${
    kind === 'text_pattern' || kind === 'coder' || kind === 'judge_code'
      ? kind
      : 'other'
  }`
}
