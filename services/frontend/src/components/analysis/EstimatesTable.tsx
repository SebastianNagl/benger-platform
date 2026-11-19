'use client'

/**
 * The estimates of an analysis run as a table: one row per estimate in
 * engine order with estimate, standard error, confidence interval, p-value,
 * the first family with its adjusted p-value, the first equivalence test and
 * the sample. A row expands to every equivalence test, every family
 * membership (with MDE), the test statistic and the inference conventions.
 */

import { Badge } from '@/components/shared/Badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { useI18n } from '@/contexts/I18nContext'
import {
  familiesOf,
  formatInterval,
  formatLevel,
  formatNumber,
  formatP,
  inFamily,
  MISSING,
  scopeDescription,
} from '@/lib/analysis/results'
import type { AnalysisEstimate } from '@/lib/api/analysis'
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import { Fragment, useMemo, useState } from 'react'

const ALL = '__all__'

/** Estimate statuses the engine writes (services/shared/analysis). */
const KNOWN_STATUSES = new Set([
  'ok',
  'error',
  'degenerate',
  'not_estimable',
  'negative_variance',
])

/** Multiplicity methods the engine knows. */
const KNOWN_METHODS = new Set(['holm', 'bonferroni', 'bh'])

const exact = (v: number | null | undefined) =>
  typeof v === 'number' && Number.isFinite(v) ? String(v) : undefined

function EquivalenceCell({ estimate }: { estimate: AnalysisEstimate }) {
  const { t, locale } = useI18n()
  const first = estimate.tost?.[0]
  if (!first) return <span className="text-zinc-400">{MISSING}</span>
  const bounds = formatInterval(first.lower, first.upper, locale, 3)
  const more = (estimate.tost?.length ?? 0) - 1
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      {first.equivalent === true ? (
        <Badge variant="success">{t('analysis.estimates.equivalent')}</Badge>
      ) : first.equivalent === false ? (
        <Badge variant="secondary">
          {t('analysis.estimates.notEquivalent')}
        </Badge>
      ) : (
        <span className="text-zinc-400">{MISSING}</span>
      )}
      <span className="font-mono text-[11px] text-zinc-500 dark:text-zinc-400">
        {bounds}
        {more > 0 &&
          ` ${t('analysis.estimates.moreBoundSets', { count: more })}`}
      </span>
    </span>
  )
}

function EstimateDetails({ estimate }: { estimate: AnalysisEstimate }) {
  const { t, locale } = useI18n()
  const facts: [string, string][] = [
    [t('analysis.estimates.detail.estimator'), estimate.estimator],
    [t('analysis.estimates.detail.outcome'), estimate.outcome ?? MISSING],
    [t('analysis.estimates.detail.kind'), estimate.kind ?? MISSING],
    [
      t('analysis.estimates.detail.statistic'),
      formatNumber(estimate.statistic, locale),
    ],
    [
      t('analysis.estimates.detail.df'),
      estimate.df === null || estimate.df === undefined
        ? t('analysis.estimates.detail.dfNormal')
        : String(estimate.df),
    ],
    [
      t('analysis.estimates.detail.nullValue'),
      formatNumber(estimate.null_value, locale),
    ],
    [
      t('analysis.estimates.detail.ciLevel'),
      formatLevel(estimate.ci_level, locale),
    ],
    [
      t('analysis.estimates.detail.kParams'),
      estimate.k_params === null || estimate.k_params === undefined
        ? MISSING
        : String(estimate.k_params),
    ],
  ]
  if (estimate.mde) {
    facts.push([
      t('analysis.estimates.detail.mde', {
        power: formatLevel(estimate.mde.power, locale),
      }),
      formatNumber(estimate.mde.value, locale),
    ])
  }
  return (
    <div className="space-y-4 text-xs" data-testid="estimate-details">
      {estimate.message && (
        <p className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300">
          {estimate.message}
        </p>
      )}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
        {facts.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-zinc-500 dark:text-zinc-400">{label}</dt>
            <dd className="truncate font-mono text-zinc-800 dark:text-zinc-200">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      {estimate.tost && estimate.tost.length > 0 && (
        <div>
          <h4 className="mb-1 font-medium text-zinc-700 dark:text-zinc-300">
            {t('analysis.estimates.detail.tostTitle')}
          </h4>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left">
              <thead className="text-zinc-500 dark:text-zinc-400">
                <tr>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.detail.bounds')}
                  </th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.detail.tostInterval')}
                  </th>
                  <th className="py-1 pr-4 font-medium">p (TOST)</th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.equivalence')}
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono text-zinc-800 dark:text-zinc-200">
                {estimate.tost.map((tost, i) => (
                  <tr key={i}>
                    <td className="py-1 pr-4">
                      {formatInterval(tost.lower, tost.upper, locale)}
                    </td>
                    <td className="py-1 pr-4">
                      {formatInterval(tost.ci_lower, tost.ci_upper, locale)}{' '}
                      <span className="text-zinc-500">
                        ({formatLevel(tost.level, locale)})
                      </span>
                    </td>
                    <td className="py-1 pr-4" title={exact(tost.p_tost)}>
                      {formatP(tost.p_tost, locale)}
                    </td>
                    <td className="py-1 pr-4 font-sans">
                      {tost.equivalent === true
                        ? t('analysis.estimates.equivalent')
                        : tost.equivalent === false
                          ? t('analysis.estimates.notEquivalent')
                          : MISSING}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {estimate.adjustments && estimate.adjustments.length > 0 && (
        <div>
          <h4 className="mb-1 font-medium text-zinc-700 dark:text-zinc-300">
            {t('analysis.estimates.detail.familiesTitle')}
          </h4>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left">
              <thead className="text-zinc-500 dark:text-zinc-400">
                <tr>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.family')}
                  </th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.detail.method')}
                  </th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.detail.group')}
                  </th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.detail.size')}
                  </th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.pAdjusted')}
                  </th>
                  <th className="py-1 pr-4 font-medium">
                    {t('analysis.estimates.detail.familyMde')}
                  </th>
                </tr>
              </thead>
              <tbody className="font-mono text-zinc-800 dark:text-zinc-200">
                {estimate.adjustments.map((a, i) => (
                  <tr key={`${a.family}-${i}`}>
                    <td className="py-1 pr-4">{a.family}</td>
                    <td className="py-1 pr-4">
                      {KNOWN_METHODS.has(a.method)
                        ? t(`analysis.methods.${a.method}`)
                        : a.method}
                    </td>
                    <td className="py-1 pr-4">
                      {a.group.length > 0 ? a.group.join(', ') : MISSING}
                    </td>
                    <td className="py-1 pr-4">{a.size}</td>
                    <td className="py-1 pr-4" title={exact(a.p_adjusted)}>
                      {formatP(a.p_adjusted, locale)}
                    </td>
                    <td className="py-1 pr-4">
                      {a.mde ? formatNumber(a.mde.value, locale) : MISSING}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {estimate.conventions && (
        <div>
          <h4 className="mb-1 font-medium text-zinc-700 dark:text-zinc-300">
            {t('analysis.estimates.detail.conventions')}
          </h4>
          <pre className="max-h-64 overflow-auto rounded bg-zinc-100 p-2 font-mono text-[11px] leading-relaxed text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200">
            {JSON.stringify(estimate.conventions, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export interface EstimatesTableProps {
  estimates: readonly AnalysisEstimate[]
}

export function EstimatesTable({ estimates }: EstimatesTableProps) {
  const { t, locale } = useI18n()
  const [estimandFilter, setEstimandFilter] = useState<string>(ALL)
  const [familyFilter, setFamilyFilter] = useState<string>(ALL)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  const estimandIds = useMemo(
    () => [...new Set(estimates.map((e) => e.estimand_id))],
    [estimates],
  )
  const families = useMemo(() => familiesOf(estimates), [estimates])
  const visible = useMemo(
    () =>
      estimates.filter(
        (e) =>
          (estimandFilter === ALL || e.estimand_id === estimandFilter) &&
          (familyFilter === ALL || inFamily(e, familyFilter)),
      ),
    [estimates, estimandFilter, familyFilter],
  )

  const toggle = (position: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(position)) next.delete(position)
      else next.add(position)
      return next
    })

  const th =
    'px-3 py-2 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'
  const num = 'px-3 py-2 text-right font-mono text-xs whitespace-nowrap'

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <label className="text-xs text-zinc-500" id="estimates-estimand-label">
          {t('analysis.estimates.filterEstimand')}
        </label>
        <Select value={estimandFilter} onValueChange={setEstimandFilter}>
          <SelectTrigger
            className="w-48"
            aria-labelledby="estimates-estimand-label"
            data-testid="estimates-estimand-filter"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('analysis.estimates.all')}</SelectItem>
            {estimandIds.map((id) => (
              <SelectItem key={id} value={id}>
                {id}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {families.length > 0 && (
          <>
            <label
              className="text-xs text-zinc-500"
              id="estimates-family-label"
            >
              {t('analysis.estimates.filterFamily')}
            </label>
            <Select value={familyFilter} onValueChange={setFamilyFilter}>
              <SelectTrigger
                className="w-48"
                aria-labelledby="estimates-family-label"
                data-testid="estimates-family-filter"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>
                  {t('analysis.estimates.all')}
                </SelectItem>
                {families.map((id) => (
                  <SelectItem key={id} value={id}>
                    {id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        )}
        <span className="ml-auto text-xs text-zinc-500">
          {t('analysis.estimates.count', {
            shown: visible.length,
            total: estimates.length,
          })}
        </span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        <table
          className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800"
          data-testid="estimates-table"
        >
          <thead className="bg-zinc-50 dark:bg-zinc-900/40">
            <tr>
              <th className="w-8 px-2 py-2">
                <span className="sr-only">
                  {t('analysis.estimates.details')}
                </span>
              </th>
              <th className={th}>{t('analysis.estimates.estimand')}</th>
              <th className={th}>{t('analysis.estimates.scope')}</th>
              <th className={`${th} text-right`}>
                {t('analysis.estimates.estimate')}
              </th>
              <th className={`${th} text-right`}>
                {t('analysis.estimates.se')}
              </th>
              <th className={`${th} text-right`}>
                {t('analysis.estimates.ci')}
              </th>
              <th className={`${th} text-right`}>p</th>
              <th className={th}>{t('analysis.estimates.family')}</th>
              <th className={`${th} text-right`}>
                {t('analysis.estimates.pAdjusted')}
              </th>
              <th className={th}>{t('analysis.estimates.equivalence')}</th>
              <th className={`${th} text-right`}>
                {t('analysis.estimates.n')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
            {visible.length === 0 && (
              <tr>
                <td
                  colSpan={11}
                  className="px-3 py-6 text-center text-xs text-zinc-500"
                >
                  {t('analysis.estimates.empty')}
                </td>
              </tr>
            )}
            {visible.map((e) => {
              const open = expanded.has(e.position)
              const scope = scopeDescription(e)
              const failed = e.status !== 'ok'
              const extraFamilies = (e.adjustments?.length ?? 0) - 1
              return (
                <Fragment key={e.position}>
                  <tr
                    className="cursor-pointer align-top hover:bg-zinc-50 dark:hover:bg-zinc-900/40"
                    onClick={() => toggle(e.position)}
                    data-testid="estimate-row"
                    data-position={e.position}
                  >
                    <td className="px-2 py-2">
                      <button
                        type="button"
                        aria-expanded={open}
                        aria-label={t('analysis.estimates.details')}
                        className="rounded p-0.5 text-zinc-500 hover:text-zinc-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 dark:hover:text-white"
                        onClick={(ev) => {
                          ev.stopPropagation()
                          toggle(e.position)
                        }}
                      >
                        {open ? (
                          <ChevronDownIcon className="h-4 w-4" />
                        ) : (
                          <ChevronRightIcon className="h-4 w-4" />
                        )}
                      </button>
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-zinc-900 dark:text-white">
                        {e.estimand_id}
                      </div>
                      {e.contrast_id && e.contrast_id !== e.estimand_id && (
                        <div className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
                          {e.contrast_id}
                        </div>
                      )}
                      {failed && (
                        <Badge
                          variant={
                            e.status === 'error' ? 'destructive' : 'warning'
                          }
                          className="mt-1"
                        >
                          {KNOWN_STATUSES.has(e.status)
                            ? t(`analysis.estimateStatus.${e.status}`)
                            : e.status}
                        </Badge>
                      )}
                    </td>
                    <td className="max-w-[16rem] px-3 py-2 text-xs break-words text-zinc-700 dark:text-zinc-300">
                      {scope ?? t('analysis.scope.pooled')}
                    </td>
                    <td className={num} title={exact(e.estimate)}>
                      {formatNumber(e.estimate, locale)}
                    </td>
                    <td className={num} title={exact(e.std_error)}>
                      {formatNumber(e.std_error, locale)}
                    </td>
                    <td
                      className={num}
                      title={
                        e.ci_level ? formatLevel(e.ci_level, locale) : undefined
                      }
                    >
                      {formatInterval(e.ci_lower, e.ci_upper, locale)}
                    </td>
                    <td className={num} title={exact(e.p_value)}>
                      {formatP(e.p_value, locale)}
                    </td>
                    <td className="px-3 py-2 text-xs whitespace-nowrap">
                      {e.family ? (
                        <span className="inline-flex flex-col">
                          <span className="font-medium text-zinc-800 dark:text-zinc-200">
                            {e.family}
                          </span>
                          <span className="text-zinc-500 dark:text-zinc-400">
                            {e.adjustments?.[0]
                              ? KNOWN_METHODS.has(e.adjustments[0].method)
                                ? t(
                                    `analysis.methods.${e.adjustments[0].method}`,
                                  )
                                : e.adjustments[0].method
                              : ''}
                            {extraFamilies > 0 &&
                              ` ${t('analysis.estimates.moreFamilies', { count: extraFamilies })}`}
                          </span>
                        </span>
                      ) : (
                        <span className="text-zinc-400">{MISSING}</span>
                      )}
                    </td>
                    <td className={num} title={exact(e.p_adjusted)}>
                      {formatP(e.p_adjusted, locale)}
                    </td>
                    <td className="px-3 py-2">
                      <EquivalenceCell estimate={e} />
                    </td>
                    <td className={num}>
                      {e.n_obs ?? MISSING}
                      {e.n_clusters && e.n_clusters.length > 0 && (
                        <div className="text-zinc-500 dark:text-zinc-400">
                          {t('analysis.estimates.clusters', {
                            clusters: e.n_clusters.join(' × '),
                          })}
                        </div>
                      )}
                    </td>
                  </tr>
                  {open && (
                    <tr className="bg-zinc-50/60 dark:bg-zinc-900/30">
                      <td />
                      <td colSpan={10} className="px-3 pt-2 pb-4">
                        <EstimateDetails estimate={e} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
