'use client'

/**
 * The statistics blocks of an analysis run, shown in the evaluations page's
 * statistics panel for the Analyses result type:
 *
 * - Inference: every multiplicity family with its adjustment method and the
 *   adjusted p-values of its members, the equivalence tests (TOST) with
 *   their bounds and decisions, the minimum detectable effects and the joint
 *   (Wald) tests.
 * - Fit: the run's warnings and the engine's per-fit summaries.
 *
 * Every number is a stored estimate of the run; nothing is recomputed.
 */

import { RunFits } from '@/components/analysis/RunSpecAndFits'
import { Badge } from '@/components/shared/Badge'
import { useI18n } from '@/contexts/I18nContext'
import {
  familiesOf,
  formatInterval,
  formatLevel,
  formatNumber,
  formatP,
  MISSING,
  scopeDescription,
} from '@/lib/analysis/results'
import type {
  AnalysisAdjustment,
  AnalysisEstimate,
  AnalysisRun,
} from '@/lib/api/analysis'
import { contrastLabel, isJointTest } from '@/lib/results/intervalRows'
import type { ReactNode } from 'react'

/** Multiplicity methods with a translated name. */
const KNOWN_METHODS = new Set(['holm', 'bonferroni', 'bh'])

const th =
  'px-3 py-2 text-left text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'
const td = 'px-3 py-2 text-zinc-800 dark:text-zinc-200'
const num =
  'px-3 py-2 text-right font-mono text-xs whitespace-nowrap text-zinc-800 dark:text-zinc-200'

function Block({
  title,
  description,
  children,
  testId,
}: {
  title: string
  description?: string
  children: ReactNode
  testId?: string
}) {
  return (
    <section
      className="rounded-lg border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
      data-testid={testId}
    >
      <h3 className="text-lg font-semibold text-zinc-900 dark:text-white">
        {title}
      </h3>
      {description && (
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {description}
        </p>
      )}
      <div className="mt-4 space-y-5">{children}</div>
    </section>
  )
}

function SubBlock({
  title,
  children,
  testId,
}: {
  title: string
  children: ReactNode
  testId?: string
}) {
  return (
    <div data-testid={testId}>
      <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {title}
      </h4>
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
        {children}
      </div>
    </div>
  )
}

function Table({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-800">
      <thead className="bg-zinc-50 dark:bg-zinc-900/40">
        <tr>{head}</tr>
      </thead>
      <tbody className="divide-y divide-zinc-100 bg-white dark:divide-zinc-800 dark:bg-zinc-950">
        {children}
      </tbody>
    </table>
  )
}

function useMethodName() {
  const { t } = useI18n()
  return (method: string) =>
    KNOWN_METHODS.has(method) ? t(`analysis.methods.${method}`) : method
}

/** The membership of `estimate` in `family` (adjustments, else the first). */
function membership(
  estimate: AnalysisEstimate,
  family: string,
): Pick<
  AnalysisAdjustment,
  'method' | 'size' | 'p_adjusted' | 'mde' | 'group'
> | null {
  const adjustment = (estimate.adjustments ?? []).find(
    (a) => a.family === family,
  )
  if (adjustment) return adjustment
  if (estimate.family === family) {
    return { method: '', size: 0, p_adjusted: estimate.p_adjusted, group: [] }
  }
  return null
}

function Where({ estimate }: { estimate: AnalysisEstimate }) {
  const { t } = useI18n()
  const scope = scopeDescription(estimate)
  return (
    <td className={`${td} max-w-[18rem] min-w-[9rem]`}>
      <div className="font-medium [overflow-wrap:anywhere]">
        {contrastLabel(estimate)}
      </div>
      <div className="text-xs [overflow-wrap:anywhere] text-zinc-500 dark:text-zinc-400">
        {scope ?? t('analysis.scope.pooled')}
      </div>
    </td>
  )
}

type Member = {
  e: AnalysisEstimate
  m: NonNullable<ReturnType<typeof membership>>
}

/**
 * The adjustment groups of every family: a family split by columns
 * (`split_by`) adjusts each group on its own, so each group is listed (and
 * counted) separately, labelled with its group values.
 */
function familyGroups(
  estimates: readonly AnalysisEstimate[],
  families: readonly string[],
): { key: string; label: string; members: Member[] }[] {
  const out: { key: string; label: string; members: Member[] }[] = []
  for (const family of families) {
    const groups = new Map<string, Member[]>()
    for (const e of estimates) {
      const m = membership(e, family)
      if (!m) continue
      const key = (m.group ?? []).join('\u0000')
      const list = groups.get(key)
      if (list) list.push({ e, m })
      else groups.set(key, [{ e, m }])
    }
    for (const [key, members] of groups) {
      const group = members[0].m.group ?? []
      out.push({
        key: `${family}\u0001${key}`,
        label: group.length > 0 ? `${family} · ${group.join(', ')}` : family,
        members,
      })
    }
  }
  return out
}

function Families({ estimates }: { estimates: readonly AnalysisEstimate[] }) {
  const { t, locale } = useI18n()
  const methodName = useMethodName()
  const families = familiesOf(estimates)
  if (families.length === 0) return null
  return (
    <div className="space-y-4" data-testid="analysis-families">
      {familyGroups(estimates, families).map(({ key, label, members }) => {
        const method = members.find((x) => x.m.method)?.m.method
        const size = members.find((x) => x.m.size)?.m.size ?? members.length
        const mde = members.find((x) => x.m.mde)?.m.mde
        return (
          <SubBlock
            key={key}
            title={t('evaluation.statisticalResults.analysis.familyTitle', {
              family: label,
              method: method ? methodName(method) : MISSING,
              size,
            })}
            testId="analysis-family"
          >
            <Table
              head={
                <>
                  <th className={th}>
                    {t('evaluation.statisticalResults.analysis.contrast')}
                  </th>
                  <th className={`${th} text-right`}>
                    {t('analysis.estimates.estimate')}
                  </th>
                  <th className={`${th} text-right`}>p</th>
                  <th className={`${th} text-right`}>
                    {t('analysis.estimates.pAdjusted')}
                  </th>
                </>
              }
            >
              {members.map(({ e, m }) => (
                <tr key={e.position} data-testid="analysis-family-member">
                  <Where estimate={e} />
                  <td className={num}>{formatNumber(e.estimate, locale)}</td>
                  <td className={num}>{formatP(e.p_value, locale)}</td>
                  <td className={num}>{formatP(m.p_adjusted, locale)}</td>
                </tr>
              ))}
            </Table>
            {mde && (
              <p className="border-t border-zinc-200 px-3 py-2 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                {t('evaluation.statisticalResults.analysis.familyMde', {
                  value: formatNumber(mde.value, locale),
                  power: formatLevel(mde.power, locale),
                  alpha: formatNumber(mde.alpha, locale),
                })}
              </p>
            )}
          </SubBlock>
        )
      })}
    </div>
  )
}

function Equivalence({
  estimates,
}: {
  estimates: readonly AnalysisEstimate[]
}) {
  const { t, locale } = useI18n()
  const rows = estimates.flatMap((e) =>
    (e.tost ?? []).map((tost, index) => ({ e, tost, index })),
  )
  if (rows.length === 0) return null
  return (
    <SubBlock
      title={t('analysis.estimates.detail.tostTitle')}
      testId="analysis-tost"
    >
      <Table
        head={
          <>
            <th className={th}>
              {t('evaluation.statisticalResults.analysis.contrast')}
            </th>
            <th className={`${th} text-right`}>
              {t('analysis.estimates.detail.bounds')}
            </th>
            <th className={`${th} text-right`}>
              {t('analysis.estimates.detail.tostInterval')}
            </th>
            <th className={`${th} text-right`}>p (TOST)</th>
            <th className={th}>{t('analysis.estimates.equivalence')}</th>
          </>
        }
      >
        {rows.map(({ e, tost, index }) => (
          <tr key={`${e.position}-${index}`} data-testid="analysis-tost-row">
            <Where estimate={e} />
            <td className={num}>
              {formatInterval(tost.lower, tost.upper, locale)}
            </td>
            <td className={num}>
              {formatInterval(tost.ci_lower, tost.ci_upper, locale)}{' '}
              <span className="text-zinc-500">
                ({formatLevel(tost.level, locale)})
              </span>
            </td>
            <td className={num}>{formatP(tost.p_tost, locale)}</td>
            <td className={td}>
              {tost.equivalent === true ? (
                <Badge variant="success">
                  {t('analysis.estimates.equivalent')}
                </Badge>
              ) : tost.equivalent === false ? (
                <Badge variant="secondary">
                  {t('analysis.estimates.notEquivalent')}
                </Badge>
              ) : (
                MISSING
              )}
            </td>
          </tr>
        ))}
      </Table>
    </SubBlock>
  )
}

function Mde({ estimates }: { estimates: readonly AnalysisEstimate[] }) {
  const { t, locale } = useI18n()
  const rows = estimates.filter((e) => e.mde)
  if (rows.length === 0) return null
  return (
    <SubBlock
      title={t('evaluation.statisticalResults.analysis.mdeTitle')}
      testId="analysis-mde"
    >
      <Table
        head={
          <>
            <th className={th}>
              {t('evaluation.statisticalResults.analysis.contrast')}
            </th>
            <th className={`${th} text-right`}>
              {t('evaluation.statisticalResults.analysis.mde')}
            </th>
            <th className={`${th} text-right`}>
              {t('evaluation.statisticalResults.analysis.power')}
            </th>
            <th className={`${th} text-right`}>α</th>
            <th className={`${th} text-right`}>
              {t('analysis.estimates.detail.size')}
            </th>
          </>
        }
      >
        {rows.map((e) => (
          <tr key={e.position} data-testid="analysis-mde-row">
            <Where estimate={e} />
            <td className={num}>{formatNumber(e.mde!.value, locale)}</td>
            <td className={num}>{formatLevel(e.mde!.power, locale)}</td>
            <td className={num}>{formatNumber(e.mde!.alpha, locale)}</td>
            <td className={num}>{e.mde!.tests}</td>
          </tr>
        ))}
      </Table>
    </SubBlock>
  )
}

function JointTests({ estimates }: { estimates: readonly AnalysisEstimate[] }) {
  const { t, locale } = useI18n()
  const rows = estimates.filter(isJointTest)
  if (rows.length === 0) return null
  return (
    <SubBlock
      title={t('evaluation.statisticalResults.analysis.jointTitle')}
      testId="analysis-joint-tests"
    >
      <Table
        head={
          <>
            <th className={th}>
              {t('evaluation.statisticalResults.analysis.test')}
            </th>
            <th className={`${th} text-right`}>χ²</th>
            <th className={`${th} text-right`}>
              {t('analysis.estimates.detail.df')}
            </th>
            <th className={`${th} text-right`}>p</th>
            <th className={`${th} text-right`}>
              {t('analysis.estimates.pAdjusted')}
            </th>
          </>
        }
      >
        {rows.map((e) => (
          <tr key={e.position} data-testid="analysis-joint-row">
            <Where estimate={e} />
            <td className={num}>{formatNumber(e.statistic, locale)}</td>
            <td className={num}>{e.df ?? MISSING}</td>
            <td className={num}>{formatP(e.p_value, locale)}</td>
            <td className={num}>{formatP(e.p_adjusted, locale)}</td>
          </tr>
        ))}
      </Table>
    </SubBlock>
  )
}

/** Families, equivalence tests, MDEs and joint tests of the estimates. */
export function AnalysisInferenceBlock({
  estimates,
}: {
  estimates: readonly AnalysisEstimate[]
}) {
  const { t } = useI18n()
  const hasAny =
    familiesOf(estimates).length > 0 ||
    estimates.some((e) => (e.tost?.length ?? 0) > 0 || e.mde || isJointTest(e))
  return (
    <Block
      title={t('evaluation.statisticalResults.analysis.inferenceTitle')}
      description={t(
        'evaluation.statisticalResults.analysis.inferenceDescription',
      )}
      testId="analysis-inference-block"
    >
      {hasAny ? (
        <>
          <Families estimates={estimates} />
          <Equivalence estimates={estimates} />
          <Mde estimates={estimates} />
          <JointTests estimates={estimates} />
        </>
      ) : (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('evaluation.statisticalResults.analysis.noInference')}
        </p>
      )}
    </Block>
  )
}

/** The run's warnings and per-fit summaries. */
export function AnalysisFitBlock({ run }: { run: AnalysisRun }) {
  const { t } = useI18n()
  const warnings = run.warnings ?? []
  const fits = run.fits ?? []
  return (
    <Block
      title={t('evaluation.statisticalResults.analysis.fitTitle')}
      description={t('analysis.fits.description')}
      testId="analysis-fit-block"
    >
      {warnings.length > 0 && (
        <div
          className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-900/20 dark:text-amber-300"
          data-testid="analysis-fit-warnings"
        >
          <p className="font-medium">
            {t('analysis.run.warnings', { count: warnings.length })}
          </p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {warnings.map((w, i) => (
              <li key={i} className="break-words">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}
      {fits.length > 0 ? (
        <RunFits fits={fits} />
      ) : (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('analysis.fits.empty')}
        </p>
      )}
    </Block>
  )
}
