'use client'

/**
 * The validations behind the report's analyses, shown in the Annotation
 * section: each code an Analyses run read with the validation it accepted
 * (the code's kind, ref, version and hash, the coding scheme control, the
 * runs and measures reading it) and the validation's agreement, frozen in
 * the snapshot (`snapshot.analyses.code_validations`).
 */

import {
  CodeValidationAgreement,
  codeKindKey,
  codeLabel,
  validationAgreementFromReport,
} from '@/components/evaluation/CodeValidationAgreement'
import { formatDate } from '@/lib/reports/format'
import type {
  ReportAnalysesSnapshot,
  ReportCodeValidation,
} from '@/types/report'
import type { TranslateFn } from './chartTheme'
import { HashValue } from './records'
import { SubHeading } from './ReportSection'

/** The validations a snapshot's Analyses section holds, or none. */
export function codeValidationsOf(
  analyses: ReportAnalysesSnapshot | null | undefined,
): ReportCodeValidation[] {
  return Array.isArray(analyses?.code_validations)
    ? analyses.code_validations
    : []
}

export function CodeValidations({
  analyses,
  locale,
  t,
}: {
  analyses: ReportAnalysesSnapshot | null | undefined
  locale: string
  t: TranslateFn
}) {
  const validations = codeValidationsOf(analyses)
  if (validations.length === 0) return null
  const runNames = new Map((analyses?.runs ?? []).map((r) => [r.id, r.name]))
  return (
    <div className="mt-6 first:mt-0" data-testid="report-code-validations">
      <SubHeading>{t('reports.view.codeValidations.title')}</SubHeading>
      <p className="-mt-1 mb-4 text-sm text-zinc-600 dark:text-zinc-300">
        {t('reports.view.codeValidations.intro')}
      </p>
      <div className="space-y-5">
        {validations.map((v) => {
          const usedBy = v.used_by
            .map((u) =>
              t('reports.view.codeValidations.usedByEntry', {
                run: runNames.get(u.run_id) ?? u.run_id,
                measure: u.measure ?? '-',
              }),
            )
            .join('; ')
          const completed = formatDate(v.completed_at, locale)
          return (
            <article
              key={v.id}
              className="min-w-0 rounded-md border border-zinc-200 p-4 dark:border-zinc-800"
              data-testid="report-code-validation"
            >
              <h4 className="text-sm font-semibold [overflow-wrap:anywhere] text-zinc-900 dark:text-white">
                {v.name || v.code_ref || v.id}
              </h4>
              <dl className="mt-2 mb-3 grid grid-cols-1 gap-x-4 gap-y-1 text-xs sm:grid-cols-[auto_minmax(0,1fr)]">
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('reports.view.codeValidations.code')}
                </dt>
                <dd className="[overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
                  {t(codeKindKey(v.code_kind))}
                  {v.code_ref || v.code_version ? (
                    <>
                      {' · '}
                      <span className="font-mono">
                        {codeLabel(v.code_ref, v.code_version, t)}
                      </span>
                    </>
                  ) : null}
                </dd>
                <dt className="text-zinc-500 dark:text-zinc-400">
                  {t('reports.view.codeValidations.hash')}
                </dt>
                <dd className="min-w-0">
                  <HashValue
                    value={v.code_hash}
                    label={t('reports.view.records.copyHash')}
                  />
                </dd>
                {v.control && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {t('reports.view.codeValidations.control')}
                    </dt>
                    <dd className="font-mono [overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
                      {v.control}
                    </dd>
                  </>
                )}
                {usedBy && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {t('reports.view.codeValidations.usedBy')}
                    </dt>
                    <dd className="[overflow-wrap:anywhere] text-zinc-800 dark:text-zinc-200">
                      {usedBy}
                    </dd>
                  </>
                )}
                {completed && (
                  <>
                    <dt className="text-zinc-500 dark:text-zinc-400">
                      {t('reports.view.codeValidations.completed')}
                    </dt>
                    <dd className="text-zinc-800 dark:text-zinc-200">
                      {completed}
                    </dd>
                  </>
                )}
              </dl>
              <CodeValidationAgreement
                data={validationAgreementFromReport(v)}
              />
              {!v.detail && (
                <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('reports.view.codeValidations.recordedOnly')}
                </p>
              )}
            </article>
          )
        })}
      </div>
    </div>
  )
}
