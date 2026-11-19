'use client'

/**
 * The Agreement and validity block of the statistics panel, the one home of
 * agreement on the evaluations page:
 *
 * - Analyses: the codes the selected run read (`analysis_runs.codes`: kind,
 *   ref, version, hash), each with the validation the run accepted and that
 *   validation's stored agreement (kappa, observed and chance agreement,
 *   precision, recall and F1 per category), and below them every
 *   validation of the project's answers. A run without codes shows no
 *   block.
 * - Metrics: the agreement between LLM judges that graded the same items
 *   (`judge_agreement_by_model_metric` of the statistics response). No
 *   judge pair, no block.
 *
 * Each block is one component, so an edition can leave it out as a whole.
 */

import { CopyValueButton } from '@/components/analysis/RunProvenance'
import {
  CodeValidationAgreement,
  codeKindKey,
  codeLabel,
  shortHash,
  validationAgreementFromMetrics,
} from '@/components/evaluation/CodeValidationAgreement'
import { Badge } from '@/components/shared/Badge'
import { useI18n } from '@/contexts/I18nContext'
import {
  statusOf,
  type AnalysisCodeRecord,
  type AnalysisRun,
} from '@/lib/api/analysis'
import {
  codingAPI,
  type CodeValidationDetail,
  type CodeValidationSummary,
} from '@/lib/api/coding'
import { formatDecimal } from '@/lib/i18n/locales'
import { formatCount } from '@/lib/reports/format'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { Block } from './blocks'

const DASH = '-'

/** Inter-judge agreement of one (model, config, metric), as the statistics
 *  endpoint returns it. */
export interface JudgeAgreementEntry {
  n_judges: number
  n_items: number
  fleiss_kappa?: number | null
  cohens_kappa_pairwise?: Record<string, number>
  pearson_r_pairwise?: Record<string, number>
  percent_agreement?: number | null
  mean_absolute_deviation?: number | null
}

function useFormat() {
  const { locale } = useI18n()
  return {
    dec: (v: number | null | undefined, digits = 2) =>
      v === null || v === undefined ? DASH : formatDecimal(v, locale, digits),
    pct: (v: number | null | undefined) =>
      v === null || v === undefined
        ? DASH
        : `${formatDecimal(v * 100, locale, 1)} %`,
    count: (v: number | null | undefined) =>
      v === null || v === undefined ? DASH : formatCount(v, locale),
  }
}

function HashValue({ hash }: { hash: string | null | undefined }) {
  const { t } = useI18n()
  if (!hash) return <span>{DASH}</span>
  return (
    <span className="inline-flex items-center gap-1">
      <code className="font-mono text-xs" title={hash}>
        {shortHash(hash)}
      </code>
      <CopyValueButton
        value={hash}
        label={t('evaluation.agreementValidity.copyHash')}
      />
    </span>
  )
}

/** Page size of the project's validation list (the endpoint's maximum). */
const VALIDATION_PAGE = 200

type DetailState =
  | { state: 'loading' }
  | { state: 'ready'; validation: CodeValidationDetail }
  | { state: 'unavailable' }
  | { state: 'failed' }

/** One code of the run with the validation it accepted. */
function RunCode({
  record,
  detail,
}: {
  record: AnalysisCodeRecord
  detail: DetailState | undefined
}) {
  const { t } = useI18n()
  const { dec, pct, count } = useFormat()
  const accepted = record.validation
  const metrics = detail?.state === 'ready' ? detail.validation.metrics : null
  return (
    <section
      className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
      data-testid="run-code"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="font-mono text-sm font-semibold [overflow-wrap:anywhere] text-zinc-900 dark:text-white">
          {record.measure}
        </h4>
        <div className="flex flex-wrap gap-1">
          <Badge variant="secondary">{t(codeKindKey(record.kind))}</Badge>
          {accepted ? (
            <Badge variant="success">
              {t('evaluation.agreementValidity.validated')}
            </Badge>
          ) : (
            <Badge variant="warning">
              {t('evaluation.agreementValidity.notValidated')}
            </Badge>
          )}
        </div>
      </div>
      <dl className="mt-2 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_minmax(0,1fr)]">
        <dt className="text-zinc-500 dark:text-zinc-400">
          {t('evaluation.agreementValidity.code')}
        </dt>
        <dd className="font-mono [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
          {codeLabel(record.ref, record.version, t)}
        </dd>
        <dt className="text-zinc-500 dark:text-zinc-400">
          {t('evaluation.agreementValidity.hash')}
        </dt>
        <dd className="text-zinc-800 dark:text-zinc-200">
          <HashValue hash={record.hash} />
        </dd>
        {typeof record.missing === 'number' && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">
              {t('evaluation.agreementValidity.missingRows')}
            </dt>
            <dd className="text-zinc-800 tabular-nums dark:text-zinc-200">
              {typeof record.rows === 'number'
                ? t('evaluation.agreementValidity.missingOfRows', {
                    missing: count(record.missing),
                    rows: count(record.rows),
                  })
                : count(record.missing)}
            </dd>
          </>
        )}
        {(record.confirmatory_estimands?.length ?? 0) > 0 && (
          <>
            <dt className="text-zinc-500 dark:text-zinc-400">
              {t('evaluation.agreementValidity.confirmatory')}
            </dt>
            <dd className="font-mono [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
              {record.confirmatory_estimands!.join(', ')}
            </dd>
          </>
        )}
      </dl>

      {accepted ? (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-zinc-600 dark:text-zinc-300">
            {t('evaluation.agreementValidity.accepted', {
              control: accepted.control,
              kappa: dec(accepted.kappa),
              agreement: pct(accepted.observed_agreement),
              compared: count(accepted.compared),
            })}{' '}
            <Link
              href={`/projects/${encodeURIComponent(accepted.coding_project_id)}`}
              className="text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
            >
              {t('evaluation.agreementValidity.openCodingProject')}
            </Link>
          </p>
          {detail?.state === 'loading' && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              {t('evaluation.agreementValidity.loadingDetail')}
            </p>
          )}
          {detail?.state === 'unavailable' && (
            <p
              className="text-xs text-zinc-500 dark:text-zinc-400"
              data-testid="validation-detail-unavailable"
            >
              {t('evaluation.agreementValidity.detailUnavailable')}
            </p>
          )}
          {detail?.state === 'failed' && (
            <p
              className="text-xs text-zinc-500 dark:text-zinc-400"
              data-testid="validation-detail-failed"
            >
              {t('evaluation.agreementValidity.detailFailed')}
            </p>
          )}
          {metrics && (
            <CodeValidationAgreement
              data={validationAgreementFromMetrics(metrics)}
            />
          )}
        </div>
      ) : (
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          {t('evaluation.agreementValidity.notValidatedHint')}
        </p>
      )}
    </section>
  )
}

// Columns of the project's validations from `sm` up; below it each
// validation stacks and its numbers carry their own labels.
const VALIDATION_COLUMNS =
  'sm:grid-cols-[minmax(0,2fr)_minmax(0,1.6fr)_6.5rem_3.5rem_5.5rem_5rem]'
const JUDGE_COLUMNS =
  'sm:grid-cols-[minmax(0,2fr)_3.5rem_3.5rem_4.5rem_5.5rem_5.5rem_minmax(0,2fr)]'
const headCell =
  'text-xs font-medium tracking-wider text-zinc-500 uppercase dark:text-zinc-400'

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 sm:block sm:text-right">
      <span className="text-xs text-zinc-500 sm:hidden dark:text-zinc-400">
        {label}
      </span>
      <span className="font-mono text-xs whitespace-nowrap text-zinc-800 dark:text-zinc-200">
        {value}
      </span>
    </div>
  )
}

function ProjectValidations({
  validations,
  usedIds,
}: {
  validations: CodeValidationSummary[]
  usedIds: Set<string>
}) {
  const { t } = useI18n()
  const { dec, pct, count } = useFormat()
  const observed = t('evaluation.agreementValidity.observed')
  const compared = t('evaluation.agreementValidity.compared')
  return (
    <div data-testid="project-code-validations">
      <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {t('evaluation.agreementValidity.projectValidations', {
          count: count(validations.length),
        })}
      </h4>
      <p className="-mt-1 mb-2 text-xs text-zinc-500 dark:text-zinc-400">
        {t('evaluation.agreementValidity.projectValidationsHint')}
      </p>
      <div className="rounded-lg border border-zinc-200 dark:border-zinc-800">
        <div
          className={`hidden gap-3 border-b border-zinc-200 bg-zinc-50 px-3 py-2 sm:grid dark:border-zinc-800 dark:bg-zinc-900/40 ${VALIDATION_COLUMNS}`}
          aria-hidden="true"
        >
          <span className={headCell}>
            {t('evaluation.agreementValidity.name')}
          </span>
          <span className={headCell}>
            {t('evaluation.agreementValidity.code')}
          </span>
          <span className={headCell}>
            {t('evaluation.agreementValidity.status')}
          </span>
          <span className={`${headCell} text-right normal-case`}>κ</span>
          <span className={`${headCell} text-right`}>{observed}</span>
          <span className={`${headCell} text-right`}>{compared}</span>
        </div>
        <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {validations.map((v) => (
            <li
              key={v.id}
              className={`grid grid-cols-1 gap-1.5 px-3 py-2.5 text-sm sm:items-center sm:gap-3 ${VALIDATION_COLUMNS}`}
              data-testid="project-code-validation"
            >
              <div className="min-w-0">
                <div className="font-medium [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
                  {v.name}
                </div>
                <div className="text-xs [overflow-wrap:anywhere] text-zinc-500 dark:text-zinc-400">
                  <Link
                    href={`/projects/${encodeURIComponent(v.project_id)}`}
                    className="underline-offset-2 hover:underline"
                  >
                    {v.coding_project_title || v.project_id}
                  </Link>
                  {' · '}
                  {v.control}
                </div>
                {usedIds.has(v.id) && (
                  <Badge variant="outline" className="mt-1">
                    {t('evaluation.agreementValidity.usedByRun')}
                  </Badge>
                )}
              </div>
              <div className="min-w-0">
                <div className="text-xs text-zinc-800 dark:text-zinc-200">
                  {t(codeKindKey(v.code_kind))}
                </div>
                <div className="font-mono text-xs [overflow-wrap:anywhere] text-zinc-500 dark:text-zinc-400">
                  {v.code_ref ?? DASH}
                </div>
              </div>
              <div>
                <ValidationStatus status={v.status} />
              </div>
              <Figure label="κ" value={dec(v.kappa)} />
              <Figure label={observed} value={pct(v.observed_agreement)} />
              <Figure label={compared} value={count(v.n_compared)} />
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function ValidationStatus({ status }: { status: string }) {
  const { t } = useI18n()
  const known = ['pending', 'running', 'completed', 'failed'].includes(status)
  const variant =
    status === 'completed'
      ? 'success'
      : status === 'failed'
        ? 'destructive'
        : 'secondary'
  return (
    <Badge variant={variant}>
      {known ? t(`evaluation.agreementValidity.statuses.${status}`) : status}
    </Badge>
  )
}

/** Codes of a run, or none. */
export function runCodes(run: AnalysisRun): AnalysisCodeRecord[] {
  return Array.isArray(run.codes)
    ? run.codes.filter(
        (c): c is AnalysisCodeRecord =>
          Boolean(c) && typeof c === 'object' && typeof c.measure === 'string',
      )
    : []
}

/**
 * The run's codes with their validations and the project's validations.
 * Renders nothing for a run without codes.
 */
export function RunAgreementBlock({ run }: { run: AnalysisRun }) {
  const { t } = useI18n()
  const codes = runCodes(run)
  const validationIds = Array.from(
    new Set(
      codes
        .map((c) => c.validation?.id)
        .filter((id): id is string => typeof id === 'string' && id !== ''),
    ),
  )
  const idsKey = validationIds.join(',')
  const [details, setDetails] = useState<{
    key: string
    byId: Record<string, DetailState>
  }>({ key: '', byId: {} })
  const [listed, setListed] = useState<{
    projectId: string
    items: CodeValidationSummary[]
  } | null>(null)
  const hasCodes = codes.length > 0

  useEffect(() => {
    if (!idsKey) return
    let cancelled = false
    // Results are keyed by the run's validation ids, so a run switch never
    // shows the previous run's detail; an id without a result is loading.
    const settle = (id: string, result: DetailState) =>
      setDetails((prev) => ({
        key: idsKey,
        byId: { ...(prev.key === idsKey ? prev.byId : {}), [id]: result },
      }))
    for (const id of idsKey.split(',')) {
      codingAPI
        .getValidation(id)
        .then((validation) => {
          if (!cancelled) settle(id, { state: 'ready', validation })
        })
        .catch((err) => {
          if (cancelled) return
          // A coding project the reader cannot open hides its detail; the
          // numbers the run recorded stay on screen.
          const status = statusOf(err)
          if (status === 404 || status === 403) {
            settle(id, { state: 'unavailable' })
          } else {
            console.warn('Code validation unavailable', err)
            settle(id, { state: 'failed' })
          }
        })
    }
    return () => {
      cancelled = true
    }
  }, [idsKey])

  useEffect(() => {
    if (!hasCodes) return
    let cancelled = false
    const loadAll = async () => {
      const items: CodeValidationSummary[] = []
      for (;;) {
        const page = await codingAPI.listAnswerValidations(
          run.project_id,
          VALIDATION_PAGE,
          items.length,
        )
        const batch = page?.items ?? []
        items.push(...batch)
        const total = page?.total ?? 0
        if (batch.length < VALIDATION_PAGE || items.length >= total) {
          return items
        }
      }
    }
    loadAll()
      .then((items) => {
        if (!cancelled) setListed({ projectId: run.project_id, items })
      })
      .catch((err) => {
        // The list is optional: a failed read hides it.
        console.warn('Code validations unavailable', err)
      })
    return () => {
      cancelled = true
    }
  }, [hasCodes, run.project_id])

  if (!hasCodes) return null
  const byId = details.key === idsKey ? details.byId : {}
  const project = listed?.projectId === run.project_id ? listed : null
  return (
    <Block
      title={t('evaluation.agreementValidity.title')}
      description={t('evaluation.agreementValidity.runDescription')}
      testId="agreement-validity-block"
    >
      <div className="space-y-3" data-testid="run-codes">
        <h4 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {t('evaluation.agreementValidity.runCodes', {
            count: codes.length,
          })}
        </h4>
        {codes.map((record) => (
          <RunCode
            key={record.measure}
            record={record}
            detail={
              record.validation
                ? (byId[record.validation.id] ?? { state: 'loading' })
                : undefined
            }
          />
        ))}
      </div>
      {project && project.items.length > 0 && (
        <ProjectValidations
          validations={project.items}
          usedIds={new Set(validationIds)}
        />
      )}
    </Block>
  )
}

/** `model|config|metric` (or `model|metric`) of a statistics key. */
function splitKey(key: string): {
  model: string
  config: string | null
  metric: string
} {
  const parts = key.split('|')
  if (parts.length >= 3) {
    return {
      model: parts[0],
      config: parts[1],
      metric: parts.slice(2).join('|'),
    }
  }
  return { model: parts[0], config: null, metric: parts[1] ?? '' }
}

function pairs(entry: JudgeAgreementEntry): Array<[string, number]> {
  const cohens = entry.cohens_kappa_pairwise ?? {}
  const pearson = entry.pearson_r_pairwise ?? {}
  const source = Object.keys(pearson).length > 0 ? pearson : cohens
  return Object.entries(source)
}

/**
 * Agreement between the LLM judges that graded the same items, per model
 * and metric configuration. Renders nothing without a judge pair.
 */
export function JudgeAgreementBlock({
  agreement,
}: {
  agreement: Record<string, JudgeAgreementEntry> | null | undefined
}) {
  const { t } = useI18n()
  const { dec, pct, count } = useFormat()
  const entries = Object.entries(agreement ?? {}).filter(
    ([, v]) => v && v.n_judges >= 2,
  )
  if (entries.length === 0) return null
  const labels = {
    modelMetric: t('evaluation.agreementValidity.modelMetric'),
    judges: t('evaluation.agreementValidity.judges'),
    items: t('evaluation.agreementValidity.items'),
    fleiss: t('evaluation.annotatorAgreement.fleissKappa'),
    allAgree: t('evaluation.agreementValidity.allAgree'),
    mad: t('evaluation.annotatorAgreement.meanAbsoluteDeviation'),
    pairs: t('evaluation.agreementValidity.judgePairs'),
  }
  return (
    <Block
      title={t('evaluation.agreementValidity.title')}
      description={t('evaluation.agreementValidity.judgeDescription')}
      testId="judge-agreement-block"
    >
      <div data-testid="judge-agreement">
        <h4 className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          {t('evaluation.agreementValidity.judgeTitle')}
        </h4>
        <div className="rounded-lg border border-zinc-200 dark:border-zinc-800">
          <div
            className={`hidden gap-3 border-b border-zinc-200 bg-zinc-50 px-3 py-2 sm:grid dark:border-zinc-800 dark:bg-zinc-900/40 ${JUDGE_COLUMNS}`}
            aria-hidden="true"
          >
            <span className={headCell}>{labels.modelMetric}</span>
            <span className={`${headCell} text-right`}>{labels.judges}</span>
            <span className={`${headCell} text-right`}>{labels.items}</span>
            <span className={`${headCell} text-right`}>{labels.fleiss}</span>
            <span className={`${headCell} text-right`}>{labels.allAgree}</span>
            <span className={`${headCell} text-right`}>{labels.mad}</span>
            <span className={headCell}>{labels.pairs}</span>
          </div>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {entries.map(([key, entry]) => {
              const { model, config, metric } = splitKey(key)
              const numeric =
                Object.keys(entry.pearson_r_pairwise ?? {}).length > 0
              return (
                <li
                  key={key}
                  className={`grid grid-cols-1 gap-1.5 px-3 py-2.5 text-sm sm:items-start sm:gap-3 ${JUDGE_COLUMNS}`}
                  data-testid="judge-agreement-row"
                >
                  <div className="min-w-0">
                    <div className="font-medium [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
                      {model}
                    </div>
                    <div className="font-mono text-xs [overflow-wrap:anywhere] text-zinc-500 dark:text-zinc-400">
                      {metric}
                      {config && config !== 'unknown' ? ` · ${config}` : ''}
                    </div>
                  </div>
                  <Figure label={labels.judges} value={count(entry.n_judges)} />
                  <Figure label={labels.items} value={count(entry.n_items)} />
                  <Figure
                    label={labels.fleiss}
                    value={dec(entry.fleiss_kappa)}
                  />
                  <Figure
                    label={labels.allAgree}
                    value={pct(entry.percent_agreement)}
                  />
                  <Figure
                    label={labels.mad}
                    value={dec(entry.mean_absolute_deviation)}
                  />
                  <div className="min-w-0 text-xs text-zinc-800 dark:text-zinc-200">
                    <span className="text-zinc-500 sm:hidden dark:text-zinc-400">
                      {labels.pairs}
                    </span>
                    <ul className="space-y-0.5">
                      {pairs(entry).map(([pair, value]) => (
                        <li key={pair} className="[overflow-wrap:anywhere]">
                          <span className="font-mono">
                            {pair.split('__').join(' / ')}
                          </span>
                          {': '}
                          <span className="tabular-nums">
                            {numeric ? 'r' : 'κ'} = {dec(value)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      </div>
    </Block>
  )
}
