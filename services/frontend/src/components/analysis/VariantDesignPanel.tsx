'use client'

/**
 * Variant design panel: one design with its factor tree (unit, factors with
 * role, variation and levels, slot factors, outcomes, gold and invariance
 * bindings), its status and task count, its content hash (the one a freeze
 * recorded, compared with a hash a run or report recorded when given), its
 * spec hash, and the assignment, balance and invariance checks on request.
 *
 * `VariantDesignPanel` renders a loaded design from its props;
 * `VariantDesignsLoader` loads a project's designs (optionally only some
 * keys) and checks them through the platform's check route.
 */

import { useI18n } from '@/contexts/I18nContext'
import { levelText } from '@/lib/analysis/labels'
import { MISSING } from '@/lib/analysis/results'
import { statusOf } from '@/lib/api/analysis'
import {
  variantViewsAPI,
  type DesignCheckReport,
  type VariantDesignRow,
  type VariantFactor,
} from '@/lib/api/variantViews'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/20/solid'
import { useEffect, useState } from 'react'
import { Field, Notice, ShortHash, ViewPanel } from './viewParts'

/** Most levels a factor lists before it says how many there are. */
const LEVELS_SHOWN = 8

function levelsText(f: VariantFactor): string {
  if (f.levels) {
    return (
      f.levels.slice(0, LEVELS_SHOWN).map(levelText).join(', ') +
      (f.levels.length > LEVELS_SHOWN ? ` … (${f.levels.length})` : '')
    )
  }
  if (f.minimum !== undefined || f.maximum !== undefined) {
    return `${f.minimum ?? ''} … ${f.maximum ?? ''}`
  }
  return ''
}

/** A translated value with the raw one as the fallback for unknown values. */
function useKnown() {
  const { t } = useI18n()
  return (key: string, value: string) => {
    const text = t(key)
    return typeof text === 'string' && text !== key ? text : value
  }
}

function FactorItem({ factor }: { factor: VariantFactor }) {
  const known = useKnown()
  const role = factor.role ?? 'manipulated'
  const varies = factor.varies ?? 'within_unit'
  const levels = levelsText(factor)
  return (
    <li className="ml-4 min-w-0 border-l border-zinc-200 pl-3 dark:border-zinc-700">
      <span className="font-mono break-all text-zinc-900 dark:text-zinc-100">
        {factor.name}
      </span>
      <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
        {[
          known(`analysis.views.design.role.${role}`, role),
          known(`analysis.views.design.varies.${varies}`, varies),
          factor.source && factor.source !== 'task'
            ? known(
                `analysis.views.design.source.${factor.source}`,
                factor.source,
              )
            : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      </span>
      {levels && (
        <p className="text-xs break-words text-zinc-600 dark:text-zinc-400">
          {levels}
        </p>
      )}
    </li>
  )
}

function FactorTree({ design }: { design: VariantDesignRow }) {
  const { t } = useI18n()
  const spec = design.spec
  const slotFactors = spec.slots?.factors ?? []
  const binding = (label: string, names: string[]) =>
    names.length > 0 && (
      <li className="text-xs break-words text-zinc-600 dark:text-zinc-400">
        {label}: <span className="font-mono">{names.join(', ')}</span>
      </li>
    )
  return (
    <ul className="min-w-0 space-y-1 text-sm" data-testid="design-factor-tree">
      <li className="font-medium text-zinc-800 dark:text-zinc-200">
        {t('analysis.views.design.unit', { name: spec.unit?.name ?? MISSING })}
      </li>
      {(spec.factors ?? []).map((f) => (
        <FactorItem key={f.name} factor={f} />
      ))}
      {slotFactors.length > 0 && (
        <li className="pt-1 text-xs font-medium text-zinc-700 dark:text-zinc-300">
          {t('analysis.views.design.slots', {
            count: spec.slots?.count ?? MISSING,
          })}
        </li>
      )}
      {slotFactors.map((f) => (
        <FactorItem key={`slot-${f.name}`} factor={f} />
      ))}
      {binding(
        t('analysis.views.design.outcomes'),
        (spec.outcomes ?? []).map((o) => o.name),
      )}
      {binding(
        t('analysis.views.design.gold'),
        (spec.gold ?? []).map((g) => g.name),
      )}
      {binding(
        t('analysis.views.design.invariance'),
        spec.invariance?.fields ?? [],
      )}
    </ul>
  )
}

function CheckResult({ result }: { result: DesignCheckReport }) {
  const { t } = useI18n()
  const r = result.report
  const sections = [
    ['assignments', r.assignments],
    ['balance', r.balance],
    ['invariance', r.invariance],
  ] as const
  return (
    <div className="mt-2 space-y-1 text-xs" data-testid="design-check">
      {sections.map(([name, s]) => (
        <p key={name} className="flex items-center gap-1.5">
          {s.ok ? (
            <CheckCircleIcon
              className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400"
              aria-hidden="true"
            />
          ) : (
            <ExclamationTriangleIcon
              className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
              aria-hidden="true"
            />
          )}
          <span className="text-zinc-700 dark:text-zinc-300">
            {t(`analysis.views.check.${name}`)}:{' '}
            {s.ok
              ? t('analysis.views.design.checkOk')
              : t('analysis.views.design.checkProblems', {
                  count: s.problem_count,
                })}
          </span>
        </p>
      ))}
      <p className="text-zinc-500 dark:text-zinc-400">
        {t('analysis.views.design.checkCounts', {
          tasks: r.task_count,
          units: r.unit_count,
          pairs: r.invariance.checked_pairs ?? 0,
        })}
      </p>
    </div>
  )
}

export interface VariantDesignPanelProps {
  design: VariantDesignRow
  /** A content hash recorded elsewhere (a run, a report) to compare with. */
  recordedHash?: string | null
  /** Runs the design's checks; without it there is no check button. */
  onCheck?: () => Promise<DesignCheckReport>
}

/** One design from its data (no fetching). */
export function VariantDesignPanel({
  design,
  recordedHash,
  onCheck,
}: VariantDesignPanelProps) {
  const { t } = useI18n()
  const known = useKnown()
  const [check, setCheck] = useState<DesignCheckReport | null>(null)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const run = async () => {
    if (!onCheck) return
    setChecking(true)
    setError(null)
    try {
      setCheck(await onCheck())
    } catch (e) {
      setError((e as Error)?.message || t('analysis.views.design.checkFailed'))
    } finally {
      setChecking(false)
    }
  }
  const compared = recordedHash !== undefined && recordedHash !== null
  const matches = compared && design.content_hash === recordedHash
  return (
    <ViewPanel
      title={
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-mono">{design.key}</span>
          {design.spec.title && (
            <span className="font-normal text-zinc-500 dark:text-zinc-400">
              {design.spec.title}
            </span>
          )}
        </span>
      }
      testId="variant-design-panel"
    >
      <div className="grid min-w-0 gap-4 md:grid-cols-2">
        <FactorTree design={design} />
        <dl className="min-w-0 space-y-2">
          <Field label={t('analysis.views.design.status')}>
            {known(
              `analysis.views.design.statusValue.${design.status}`,
              design.status,
            )}
            {design.task_count !== undefined && (
              <span className="ml-2 text-xs text-zinc-500 dark:text-zinc-400">
                {t('analysis.views.design.tasks', {
                  count: design.task_count,
                })}
              </span>
            )}
          </Field>
          {compared && (
            <Field label={t('analysis.views.design.recordedHash')}>
              <ShortHash value={recordedHash} />
            </Field>
          )}
          <Field label={t('analysis.views.design.contentHash')}>
            <span className="inline-flex flex-wrap items-center gap-1.5">
              <ShortHash value={design.content_hash} />
              {compared &&
                (matches ? (
                  <span
                    className="inline-flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400"
                    data-testid="design-hash-match"
                  >
                    <CheckCircleIcon className="h-4 w-4" aria-hidden="true" />
                    {t('analysis.views.design.hashMatch')}
                  </span>
                ) : (
                  <span
                    className="inline-flex items-center gap-1 text-xs text-red-700 dark:text-red-400"
                    data-testid="design-hash-mismatch"
                  >
                    <ExclamationTriangleIcon
                      className="h-4 w-4"
                      aria-hidden="true"
                    />
                    {t('analysis.views.design.hashMismatch')}
                  </span>
                ))}
            </span>
          </Field>
          <Field label={t('analysis.views.design.specHash')}>
            <ShortHash value={design.spec_sha256} />
          </Field>
          {onCheck && (
            <div>
              <button
                type="button"
                onClick={run}
                disabled={checking}
                className="text-xs font-medium text-emerald-700 hover:underline disabled:opacity-60 dark:text-emerald-400"
                data-testid="design-run-check"
              >
                {checking
                  ? t('analysis.views.design.checking')
                  : t('analysis.views.design.runCheck')}
              </button>
              {error && (
                <p className="mt-1 text-xs text-red-700 dark:text-red-400">
                  {error}
                </p>
              )}
              {check && <CheckResult result={check} />}
            </div>
          )}
        </dl>
      </div>
    </ViewPanel>
  )
}

/**
 * The variant designs of a project (only `keys` when given), loaded and
 * checkable. Renders nothing for viewers who may not read designs.
 */
export function VariantDesignsLoader({
  projectId,
  keys,
}: {
  projectId: string
  keys?: readonly string[]
}) {
  const { t } = useI18n()
  const keyList = (keys ?? []).join('\u0000')
  const requestKey = `${projectId}\u0001${keyList}`
  // The last answer, with the request it answers (loading until it matches).
  const [loaded, setLoaded] = useState<{
    key: string
    state: 'hidden' | 'error' | 'ready'
    designs: VariantDesignRow[]
  } | null>(null)
  const state = loaded?.key === requestKey ? loaded.state : 'loading'
  const designs = loaded?.key === requestKey ? loaded.designs : null

  useEffect(() => {
    let cancelled = false
    const key = `${projectId}\u0001${keyList}`
    variantViewsAPI
      .listDesigns(projectId)
      .then((rows) => {
        if (cancelled) return
        const wanted = keyList ? keyList.split('\u0000') : null
        setLoaded({
          key,
          state: 'ready',
          designs: wanted ? rows.filter((d) => wanted.includes(d.key)) : rows,
        })
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setLoaded({
          key,
          state:
            statusOf(e) === 403 || statusOf(e) === 404 ? 'hidden' : 'error',
          designs: [],
        })
      })
    return () => {
      cancelled = true
    }
  }, [projectId, keyList])

  if (state === 'hidden') return null
  if (state === 'error') {
    return <Notice tone="error">{t('analysis.views.design.loadFailed')}</Notice>
  }
  if (state === 'loading' || !designs) {
    return (
      <p className="text-sm text-zinc-500 dark:text-zinc-400" role="status">
        {t('analysis.views.design.loading')}
      </p>
    )
  }
  if (designs.length === 0) {
    return <Notice>{t('analysis.views.design.none')}</Notice>
  }
  return (
    <div className="space-y-3" data-testid="variant-designs">
      {designs.map((d) => (
        <VariantDesignPanel
          key={d.key}
          design={d}
          onCheck={() => variantViewsAPI.checkDesign(projectId, d.key)}
        />
      ))}
    </div>
  )
}
