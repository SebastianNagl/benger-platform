'use client'

/**
 * The project's variant designs as a table: key, status, version, tasks and
 * the frozen content hash, with the actions Check (assignments, balance and
 * span invariance, without changing anything) and Freeze (records the
 * content hash and makes the tasks read-only), and the import of an exported
 * design document as a new draft. Every number shown after an action is the
 * route's answer; nothing is computed here.
 */

import { CopyValueButton } from '@/components/analysis/RunProvenance'
import { Badge } from '@/components/shared/Badge'
import { Button } from '@/components/shared/Button'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { useI18n } from '@/contexts/I18nContext'
import { MISSING, shortHash } from '@/lib/analysis/results'
import {
  variantDesignRefusalOf,
  variantDesignsAPI,
  type VariantDesign,
  type VariantDesignProblem,
  type VariantDesignRefusal,
  type VariantDesignReport,
} from '@/lib/api/variantDesigns'
import { useCallback, useEffect, useRef, useState } from 'react'

type Outcome =
  | { kind: 'checked'; report: VariantDesignReport; contentHash: string }
  | { kind: 'frozen'; report: VariantDesignReport; contentHash: string | null }
  | { kind: 'refused'; refusal: VariantDesignRefusal }
  | { kind: 'error'; message: string }

type ImportState =
  | { kind: 'none' }
  | { kind: 'imported'; key: string }
  | { kind: 'refused'; message: string; problems: VariantDesignProblem[] }

const SECTIONS = ['assignments', 'balance', 'invariance'] as const
const MAX_SHOWN_PROBLEMS = 10

/** Refusal codes the table words itself; others show the route's message. */
const REFUSAL_CODES = new Set([
  'variant_design_checks_failed',
  'variant_design_frozen',
  'variant_design_exists',
  'variant_design_invalid',
  'variant_design_format',
  'variant_design_not_found',
])

function problemText(problem: VariantDesignProblem): string {
  const where =
    typeof problem.path === 'string' && problem.path ? `${problem.path}: ` : ''
  return `${where}${problem.message}`
}

function ReportView({
  report,
  contentHash,
  hashLabel,
}: {
  report: VariantDesignReport
  contentHash: string | null
  hashLabel: string
}) {
  const { t } = useI18n()
  const cells = report.balance?.expected_cells_per_unit
  const pairs = report.invariance?.checked_pairs
  return (
    <div className="space-y-2 text-sm" data-testid="variant-design-report">
      <p
        className={
          report.ok
            ? 'font-medium text-emerald-700 dark:text-emerald-400'
            : 'font-medium text-red-700 dark:text-red-400'
        }
        role="status"
      >
        {report.ok
          ? t('analysis.designs.checksPassed')
          : t('analysis.designs.checksFailed')}
      </p>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-zinc-600 dark:text-zinc-400">
        <div className="flex gap-1">
          <dt>{t('analysis.designs.units')}</dt>
          <dd className="font-medium text-zinc-800 dark:text-zinc-200">
            {report.unit_count}
          </dd>
        </div>
        <div className="flex gap-1">
          <dt>{t('analysis.designs.tasks')}</dt>
          <dd className="font-medium text-zinc-800 dark:text-zinc-200">
            {report.task_count}
          </dd>
        </div>
        <div className="flex gap-1">
          <dt>{t('analysis.designs.cellsPerUnit')}</dt>
          <dd className="font-medium text-zinc-800 dark:text-zinc-200">
            {cells ?? MISSING}
          </dd>
        </div>
        {pairs !== undefined && (
          <div className="flex gap-1">
            <dt>{t('analysis.designs.checkedPairs')}</dt>
            <dd className="font-medium text-zinc-800 dark:text-zinc-200">
              {pairs}
            </dd>
          </div>
        )}
        {contentHash && (
          <div className="flex items-center gap-1">
            <dt>{hashLabel}</dt>
            <dd className="inline-flex items-center gap-1">
              <code
                className="font-mono text-zinc-800 dark:text-zinc-200"
                title={contentHash}
              >
                {shortHash(contentHash)}
              </code>
              <CopyValueButton
                value={contentHash}
                label={t('analysis.provenance.copy', { what: hashLabel })}
              />
            </dd>
          </div>
        )}
      </dl>
      <ul className="space-y-1">
        {SECTIONS.map((section) => {
          const part = report[section]
          if (!part) return null
          return (
            <li key={section}>
              <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                {t(`analysis.designs.section.${section}`)}:{' '}
              </span>
              <span
                className={
                  part.ok
                    ? 'text-xs text-emerald-700 dark:text-emerald-400'
                    : 'text-xs text-red-700 dark:text-red-400'
                }
              >
                {part.ok
                  ? t('analysis.designs.sectionOk')
                  : part.problem_count === 1
                    ? t('analysis.designs.sectionProblem')
                    : t('analysis.designs.sectionProblems', {
                        count: part.problem_count,
                      })}
              </span>
              {!part.ok && part.problems.length > 0 && (
                <ul className="mt-0.5 list-disc pl-5 font-mono text-xs break-words text-zinc-700 dark:text-zinc-300">
                  {part.problems.slice(0, MAX_SHOWN_PROBLEMS).map((p, i) => (
                    <li key={i}>{problemText(p)}</li>
                  ))}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function useRefusalText() {
  const { t } = useI18n()
  return (refusal: VariantDesignRefusal) =>
    REFUSAL_CODES.has(refusal.code)
      ? t(`analysis.designs.refusal.${refusal.code}`)
      : refusal.message
}

function OutcomeView({ outcome }: { outcome: Outcome }) {
  const { t } = useI18n()
  const refusalText = useRefusalText()
  if (outcome.kind === 'checked')
    return (
      <ReportView
        report={outcome.report}
        contentHash={outcome.contentHash}
        hashLabel={t('analysis.designs.wouldFreezeWith')}
      />
    )
  if (outcome.kind === 'frozen')
    return (
      <div className="space-y-2">
        <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
          {t('analysis.designs.frozenNow')}
        </p>
        <ReportView
          report={outcome.report}
          contentHash={outcome.contentHash}
          hashLabel={t('analysis.designs.contentHash')}
        />
      </div>
    )
  if (outcome.kind === 'refused')
    return (
      <div className="space-y-2" role="alert">
        <p className="text-sm text-red-700 dark:text-red-400">
          {refusalText(outcome.refusal)}
        </p>
        {outcome.refusal.report && (
          <ReportView
            report={outcome.refusal.report}
            contentHash={null}
            hashLabel={t('analysis.designs.contentHash')}
          />
        )}
        {!outcome.refusal.report && outcome.refusal.problems.length > 0 && (
          <ul className="list-disc pl-5 font-mono text-xs break-words text-red-700 dark:text-red-300">
            {outcome.refusal.problems
              .slice(0, MAX_SHOWN_PROBLEMS)
              .map((p, i) => (
                <li key={i}>{problemText(p)}</li>
              ))}
          </ul>
        )}
      </div>
    )
  return (
    <p className="text-sm text-red-700 dark:text-red-400" role="alert">
      {outcome.message}
    </p>
  )
}

export interface VariantDesignsTableProps {
  projectId: string
  /** Called with the designs after every load and change. */
  onDesignsChange?: (designs: VariantDesign[]) => void
}

export function VariantDesignsTable({
  projectId,
  onDesignsChange,
}: VariantDesignsTableProps) {
  const { t } = useI18n()
  const [designs, setDesigns] = useState<VariantDesign[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({})
  const [busy, setBusy] = useState<Record<string, 'check' | 'freeze'>>({})
  const [confirmFreeze, setConfirmFreeze] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)
  const [importState, setImportState] = useState<ImportState>({
    kind: 'none',
  })
  const refusalText = useRefusalText()
  const fileInput = useRef<HTMLInputElement>(null)
  const changed = useRef(onDesignsChange)
  useEffect(() => {
    changed.current = onDesignsChange
  }, [onDesignsChange])

  const show = useCallback((next: VariantDesign[]) => {
    setDesigns(next)
    changed.current?.(next)
  }, [])

  const load = useCallback(async () => {
    try {
      show(await variantDesignsAPI.list(projectId))
      setLoadError(null)
    } catch {
      setLoadError(t('analysis.designs.loadFailed'))
      setDesigns([])
    }
    // t is stable per locale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, show])

  useEffect(() => {
    setDesigns(null)
    setOutcomes({})
    void load()
  }, [load])

  const failure = (error: unknown, fallback: string): Outcome => {
    const refusal = variantDesignRefusalOf(error)
    if (refusal) return { kind: 'refused', refusal }
    return { kind: 'error', message: (error as Error)?.message || fallback }
  }

  const check = async (key: string) => {
    setBusy((b) => ({ ...b, [key]: 'check' }))
    try {
      const result = await variantDesignsAPI.check(projectId, key)
      setOutcomes((o) => ({
        ...o,
        [key]: {
          kind: 'checked',
          report: result.report,
          contentHash: result.content_hash,
        },
      }))
    } catch (error) {
      setOutcomes((o) => ({
        ...o,
        [key]: failure(error, t('analysis.designs.checkFailed')),
      }))
    } finally {
      setBusy(({ [key]: _done, ...rest }) => rest)
    }
  }

  const freeze = async (key: string) => {
    setBusy((b) => ({ ...b, [key]: 'freeze' }))
    try {
      const result = await variantDesignsAPI.freeze(projectId, key)
      setOutcomes((o) => ({
        ...o,
        [key]: {
          kind: 'frozen',
          report: result.report,
          contentHash: result.design.content_hash,
        },
      }))
      // The list reads the stored state back (status, hash, version).
      await load()
    } catch (error) {
      setOutcomes((o) => ({
        ...o,
        [key]: failure(error, t('analysis.designs.freezeFailed')),
      }))
    } finally {
      setBusy(({ [key]: _done, ...rest }) => rest)
    }
  }

  const importFile = async (file: File) => {
    setImporting(true)
    setImportState({ kind: 'none' })
    try {
      let document: unknown
      try {
        document = JSON.parse(await file.text())
      } catch (error) {
        setImportState({
          kind: 'refused',
          message: t('analysis.designs.importInvalidJson', {
            error: (error as Error).message,
          }),
          problems: [],
        })
        return
      }
      const created = await variantDesignsAPI.importDocument(
        projectId,
        document,
      )
      setImportState({ kind: 'imported', key: created.key })
      await load()
    } catch (error) {
      const refusal = variantDesignRefusalOf(error)
      setImportState({
        kind: 'refused',
        message: refusal
          ? refusalText(refusal)
          : (error as Error)?.message || t('analysis.designs.importFailed'),
        problems: refusal?.problems ?? [],
      })
    } finally {
      setImporting(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  return (
    <div className="space-y-3" data-testid="variant-designs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
            {t('analysis.designs.title')}
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            {t('analysis.designs.description')}
          </p>
        </div>
        <div>
          <input
            ref={fileInput}
            type="file"
            accept=".json,application/json"
            className="sr-only"
            tabIndex={-1}
            aria-hidden="true"
            data-testid="variant-design-import-input"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void importFile(file)
            }}
          />
          <Button
            variant="outline"
            className="text-sm"
            disabled={importing}
            onClick={() => fileInput.current?.click()}
            data-testid="variant-design-import"
          >
            {importing
              ? t('analysis.designs.importing')
              : t('analysis.designs.import')}
          </Button>
        </div>
      </div>

      {importState.kind === 'imported' && (
        <p
          className="text-sm text-emerald-700 dark:text-emerald-400"
          role="status"
        >
          {t('analysis.designs.imported', { key: importState.key })}
        </p>
      )}
      {importState.kind === 'refused' && (
        <div
          className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"
          role="alert"
        >
          <p>{importState.message}</p>
          {importState.problems.length > 0 && (
            <ul className="mt-1 list-disc pl-5 font-mono text-xs break-words">
              {importState.problems.slice(0, MAX_SHOWN_PROBLEMS).map((p, i) => (
                <li key={i}>{problemText(p)}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {loadError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {loadError}
        </p>
      )}
      {designs === null ? (
        <p className="text-sm text-zinc-500" role="status">
          {t('analysis.run.loading')}
        </p>
      ) : designs.length === 0 && !loadError ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('analysis.designs.empty')}
        </p>
      ) : designs.length > 0 ? (
        <div
          // relative: the sr-only header is absolutely positioned and would
          // otherwise widen the page past this scroll container.
          className="relative overflow-x-auto rounded-md border border-zinc-200 dark:border-zinc-700"
        >
          <table className="min-w-full divide-y divide-zinc-200 text-sm dark:divide-zinc-700">
            <thead className="bg-zinc-50 dark:bg-zinc-800/60">
              <tr className="text-left text-xs font-medium text-zinc-500 dark:text-zinc-400">
                <th scope="col" className="px-3 py-2">
                  {t('analysis.designs.col.key')}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t('analysis.designs.col.status')}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t('analysis.designs.col.version')}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t('analysis.designs.col.units')}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t('analysis.designs.col.cells')}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  {t('analysis.designs.col.tasks')}
                </th>
                <th scope="col" className="px-3 py-2">
                  {t('analysis.designs.col.contentHash')}
                </th>
                <th scope="col" className="px-3 py-2 text-right">
                  <span className="sr-only">
                    {t('analysis.designs.col.actions')}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-700">
              {designs.map((design) => {
                const frozen = design.status === 'frozen'
                const title =
                  typeof design.spec?.title === 'string'
                    ? design.spec.title
                    : null
                return (
                  <tr
                    key={design.key}
                    data-testid={`variant-design-${design.key}`}
                  >
                    <td className="px-3 py-2 align-top">
                      <code className="font-mono text-xs text-zinc-900 dark:text-zinc-100">
                        {design.key}
                      </code>
                      {title && (
                        <div className="text-xs text-zinc-500 dark:text-zinc-400">
                          {title}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 align-top">
                      <Badge variant={frozen ? 'success' : 'secondary'}>
                        {frozen
                          ? t('analysis.designs.status.frozen')
                          : t('analysis.designs.status.draft')}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right align-top text-zinc-700 tabular-nums dark:text-zinc-300">
                      {design.version}
                    </td>
                    <td className="px-3 py-2 text-right align-top text-zinc-700 tabular-nums dark:text-zinc-300">
                      {design.unit_count ?? MISSING}
                    </td>
                    <td className="px-3 py-2 text-right align-top text-zinc-700 tabular-nums dark:text-zinc-300">
                      {design.cell_count ?? MISSING}
                    </td>
                    <td className="px-3 py-2 text-right align-top text-zinc-700 tabular-nums dark:text-zinc-300">
                      {design.task_count ?? MISSING}
                    </td>
                    <td className="px-3 py-2 align-top">
                      {design.content_hash ? (
                        <span className="inline-flex items-center gap-1">
                          <code
                            className="font-mono text-xs text-zinc-800 dark:text-zinc-200"
                            title={design.content_hash}
                          >
                            {shortHash(design.content_hash)}
                          </code>
                          <CopyValueButton
                            value={design.content_hash}
                            label={t('analysis.provenance.copy', {
                              what: t('analysis.designs.contentHash'),
                            })}
                          />
                        </span>
                      ) : (
                        <span className="text-zinc-400">{MISSING}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right align-top">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="outline"
                          className="px-2 py-1 text-xs"
                          disabled={Boolean(busy[design.key])}
                          onClick={() => void check(design.key)}
                          aria-label={t('analysis.designs.checkNamed', {
                            key: design.key,
                          })}
                        >
                          {busy[design.key] === 'check'
                            ? t('analysis.designs.checking')
                            : t('analysis.designs.check')}
                        </Button>
                        {!frozen && (
                          <Button
                            variant="outline"
                            className="px-2 py-1 text-xs"
                            disabled={Boolean(busy[design.key])}
                            onClick={() => setConfirmFreeze(design.key)}
                            aria-label={t('analysis.designs.freezeNamed', {
                              key: design.key,
                            })}
                          >
                            {busy[design.key] === 'freeze'
                              ? t('analysis.designs.freezing')
                              : t('analysis.designs.freeze')}
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      {/* What the routes answered, below the table so a report stays
      readable where the table scrolls sideways (phones). */}
      {(designs ?? [])
        .filter((design) => outcomes[design.key])
        .map((design) => (
          <section
            key={design.key}
            aria-label={design.key}
            className="rounded-md border border-zinc-200 bg-zinc-50/60 px-3 py-3 dark:border-zinc-700 dark:bg-zinc-800/30"
            data-testid={`variant-design-outcome-${design.key}`}
          >
            <p className="mb-2 font-mono text-xs font-medium text-zinc-900 dark:text-zinc-100">
              {design.key}
            </p>
            <OutcomeView outcome={outcomes[design.key]} />
          </section>
        ))}

      <ConfirmationDialog
        isOpen={confirmFreeze !== null}
        onClose={() => setConfirmFreeze(null)}
        onConfirm={() => {
          if (confirmFreeze) void freeze(confirmFreeze)
        }}
        title={t('analysis.designs.freezeTitle', { key: confirmFreeze ?? '' })}
        message={t('analysis.designs.freezeMessage')}
        confirmText={t('analysis.designs.freeze')}
        variant="warning"
      />
    </div>
  )
}
