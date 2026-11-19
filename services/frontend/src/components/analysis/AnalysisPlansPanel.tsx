'use client'

/**
 * The project's analysis plans: named analysis specs saved with the
 * evaluation configuration (`evaluation_config.analysis_plans`). The API
 * validates every spec with the analysis engine and stores the hash of its
 * normalized form, the hash a run started from the plan records, so a run
 * names the plan it used by hash. A plan can be added, edited, deleted and
 * started as a run.
 *
 * Every save sends the whole list (lists replace as a whole), built on the
 * plans as stored right before the save, so a plan another editor saved in
 * the meantime is kept.
 */

import { AnalysisSpecForm } from '@/components/analysis/NewAnalysisRunForm'
import { CopyValueButton } from '@/components/analysis/RunProvenance'
import { Button } from '@/components/shared/Button'
import { ConfirmationDialog } from '@/components/shared/ConfirmationDialog'
import { Dialog } from '@/components/shared/Dialog'
import { useI18n } from '@/contexts/I18nContext'
import { shortHash } from '@/lib/analysis/results'
import {
  analysisAPI,
  type AnalysisPlan,
  type AnalysisPlanDraft,
} from '@/lib/api/analysis'
import { formatDateTime } from '@/lib/reports/format'
import { useCallback, useEffect, useState } from 'react'

type Editor = { mode: 'new' } | { mode: 'edit'; plan: AnalysisPlan }

const draftOf = (plan: AnalysisPlan): AnalysisPlanDraft => ({
  id: plan.id,
  name: plan.name,
  spec: plan.spec,
})

export interface AnalysisPlansPanelProps {
  projectId: string
  /** Design keys for the starting spec of a new plan. */
  designKeys: readonly string[]
  /** Open the start dialog with this plan. */
  onStartPlan: (planId: string) => void
  /** Called with the plans after every load and save. */
  onPlansChange?: (plans: AnalysisPlan[]) => void
}

export function AnalysisPlansPanel({
  projectId,
  designKeys,
  onStartPlan,
  onPlansChange,
}: AnalysisPlansPanelProps) {
  const { t, locale } = useI18n()
  const [plans, setPlans] = useState<AnalysisPlan[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [editor, setEditor] = useState<Editor | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<AnalysisPlan | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const show = useCallback(
    (next: AnalysisPlan[]) => {
      setPlans(next)
      onPlansChange?.(next)
    },
    [onPlansChange],
  )

  useEffect(() => {
    let cancelled = false
    setPlans(null)
    analysisAPI
      .listPlans(projectId)
      .then((saved) => {
        if (cancelled) return
        setLoadError(null)
        show(saved)
      })
      .catch(() => {
        if (cancelled) return
        setLoadError(t('analysis.plans.loadFailed'))
        setPlans([])
      })
    return () => {
      cancelled = true
    }
    // t is stable per locale; show changes with the host callback only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  /** Apply `change` to the plans as stored now and save the result. */
  const saveWith = async (
    change: (stored: AnalysisPlanDraft[]) => AnalysisPlanDraft[],
  ) => {
    const stored = (await analysisAPI.listPlans(projectId)).map(draftOf)
    show(await analysisAPI.savePlans(projectId, change(stored)))
  }

  const savePlan = async (spec: unknown, name: string) => {
    const current = editor
    if (!current) return
    if (current.mode === 'edit') {
      const id = current.plan.id
      await saveWith((stored) =>
        stored.some((p) => p.id === id)
          ? stored.map((p) => (p.id === id ? { id, name, spec } : p))
          : [...stored, { id, name, spec }],
      )
    } else {
      await saveWith((stored) => [...stored, { name, spec }])
    }
    setEditor(null)
  }

  const deletePlan = async (plan: AnalysisPlan) => {
    setDeleteError(null)
    try {
      await saveWith((stored) => stored.filter((p) => p.id !== plan.id))
    } catch (error) {
      setDeleteError(
        (error as Error)?.message || t('analysis.plans.deleteFailed'),
      )
    }
  }

  return (
    <div className="space-y-3" data-testid="analysis-plans">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">
            {t('analysis.plans.title')}
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            {t('analysis.plans.description')}
          </p>
        </div>
        <Button
          variant="outline"
          className="text-sm"
          onClick={() => setEditor({ mode: 'new' })}
          data-testid="analysis-plan-new"
        >
          {t('analysis.plans.new')}
        </Button>
      </div>

      {loadError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {loadError}
        </p>
      )}
      {deleteError && (
        <p className="text-sm text-red-600 dark:text-red-400" role="alert">
          {deleteError}
        </p>
      )}
      {plans === null ? (
        <p className="text-sm text-zinc-500" role="status">
          {t('analysis.run.loading')}
        </p>
      ) : plans.length === 0 && !loadError ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {t('analysis.plans.empty')}
        </p>
      ) : (
        <ul className="divide-y divide-zinc-200 rounded-md border border-zinc-200 dark:divide-zinc-700 dark:border-zinc-700">
          {plans.map((plan) => (
            <li
              key={plan.id}
              className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-3 py-2"
              data-testid={`analysis-plan-${plan.id}`}
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {plan.name}
                </p>
                <p className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="inline-flex items-center gap-1">
                    {t('analysis.plans.hash')}
                    <code
                      className="font-mono text-zinc-800 dark:text-zinc-200"
                      title={plan.spec_hash}
                    >
                      {shortHash(plan.spec_hash)}
                    </code>
                    <CopyValueButton
                      value={plan.spec_hash}
                      label={t('analysis.provenance.copy', {
                        what: t('analysis.plans.hash'),
                      })}
                    />
                  </span>
                  {plan.saved_at && (
                    <span>
                      {t('analysis.plans.savedAt', {
                        date: formatDateTime(plan.saved_at, locale),
                      })}
                    </span>
                  )}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="primary"
                  className="px-2 py-1 text-xs"
                  onClick={() => onStartPlan(plan.id)}
                  aria-label={t('analysis.plans.startNamed', {
                    name: plan.name,
                  })}
                >
                  {t('analysis.plans.start')}
                </Button>
                <Button
                  variant="outline"
                  className="px-2 py-1 text-xs"
                  onClick={() => setEditor({ mode: 'edit', plan })}
                  aria-label={t('analysis.plans.editNamed', {
                    name: plan.name,
                  })}
                >
                  {t('analysis.plans.edit')}
                </Button>
                <Button
                  variant="outline"
                  className="px-2 py-1 text-xs"
                  onClick={() => setConfirmDelete(plan)}
                  aria-label={t('analysis.plans.deleteNamed', {
                    name: plan.name,
                  })}
                >
                  {t('analysis.plans.delete')}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        isOpen={editor !== null}
        onClose={() => setEditor(null)}
        title={
          editor?.mode === 'edit'
            ? t('analysis.plans.editTitle')
            : t('analysis.plans.newTitle')
        }
        className="max-w-2xl"
      >
        <div data-testid="analysis-plan-editor">
          <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
            {t('analysis.plans.editorDescription')}
          </p>
          {editor && (
            <AnalysisSpecForm
              key={editor.mode === 'edit' ? editor.plan.id : 'new'}
              initialSpec={
                editor.mode === 'edit'
                  ? JSON.stringify(editor.plan.spec, null, 2)
                  : undefined
              }
              initialName={editor.mode === 'edit' ? editor.plan.name : ''}
              designKeys={designKeys}
              nameLabel={t('analysis.plans.name')}
              namePlaceholder={t('analysis.plans.namePlaceholder')}
              nameRequired
              submitLabel={t('analysis.plans.save')}
              submittingLabel={t('analysis.plans.saving')}
              submitTestId="analysis-plan-save"
              failedMessage={t('analysis.plans.saveFailed')}
              planHash={editor.mode === 'edit' ? editor.plan.spec_hash : null}
              onSubmit={savePlan}
            />
          )}
        </div>
      </Dialog>

      <ConfirmationDialog
        isOpen={confirmDelete !== null}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => {
          if (confirmDelete) void deletePlan(confirmDelete)
        }}
        title={t('analysis.plans.deleteTitle', {
          name: confirmDelete?.name ?? '',
        })}
        message={t('analysis.plans.deleteMessage')}
        confirmText={t('analysis.plans.delete')}
        variant="danger"
      />
    </div>
  )
}
