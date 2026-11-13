/**
 * MergeResultsModal - merge the results of a full project export into this
 * project.
 *
 * The workflow it serves: the project was exported, imported on another
 * deployment (or as a copy here), a new model was generated and evaluated on
 * that copy, and the copy was exported again. Merging that file adds the new
 * generations and evaluations to this project's existing tasks and skips the
 * results the project already holds, so the new model appears next to the
 * others. The server refuses the file, importing nothing, when its tasks are
 * not this project's (`merge_task_mismatch`).
 *
 * Custom models get a new id on every deployment; the optional model id rows
 * translate an id in the file to the id of the same model here.
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { projectsAPI } from '@/lib/api/projects'
import { logger } from '@/lib/utils/logger'
import { PlusIcon, XMarkIcon } from '@heroicons/react/24/outline'
import React, { useState } from 'react'

interface MergeResultsModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  onMergeComplete?: () => void
}

interface ModelRow {
  source: string
  target: string
}

interface MergeSummary {
  matchedTasks: number
  added: Record<string, number>
  skipped: Record<string, number>
  modelsAdded: string[]
}

/** Code the import worker prefixes to a refused merge's error message. */
const MERGE_TASK_MISMATCH = 'merge_task_mismatch'

const ACCEPTED_FILES = '.json,.ndjson,.gz,.zip'

export function MergeResultsModal({
  isOpen,
  onClose,
  projectId,
  onMergeComplete,
}: MergeResultsModalProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [rows, setRows] = useState<ModelRow[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<MergeSummary | null>(null)

  const reset = () => {
    setFile(null)
    setRows([])
    setRunning(false)
    setError(null)
    setSummary(null)
  }

  const close = () => {
    if (running) return
    reset()
    onClose()
  }

  const modelIdMap = (): Record<string, string> => {
    const map: Record<string, string> = {}
    for (const row of rows) {
      const source = row.source.trim()
      const target = row.target.trim()
      if (source && target) map[source] = target
    }
    return map
  }

  const incompleteRow = rows.some(
    (row) => Boolean(row.source.trim()) !== Boolean(row.target.trim()),
  )

  const updateRow = (index: number, patch: Partial<ModelRow>) => {
    setRows((current) =>
      current.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    )
  }

  const handleMerge = async () => {
    if (!file) return
    setRunning(true)
    setError(null)
    setSummary(null)
    try {
      const status = await projectsAPI.runMergeImportJob(
        projectId,
        file,
        undefined,
        { modelIdMap: modelIdMap() },
      )
      const stats = status.result?.statistics || {}
      setSummary({
        matchedTasks: stats.matched_tasks ?? 0,
        added: stats.added_counts || {},
        skipped: stats.skipped_present_counts || {},
        modelsAdded: stats.models_added_to_project || [],
      })
      addToast(t('projects.mergeImport.success'), 'success')
      onMergeComplete?.()
    } catch (err: any) {
      logger.error('Merge import failed', err)
      const message: string = err?.message || ''
      setError(
        message.includes(MERGE_TASK_MISMATCH)
          ? t('projects.mergeImport.taskMismatch')
          : message || t('projects.mergeImport.failed'),
      )
    } finally {
      setRunning(false)
    }
  }

  const added = summary?.added || {}
  const skipped = summary?.skipped || {}

  return (
    <Dialog
      isOpen={isOpen}
      onClose={close}
      title={t('projects.mergeImport.title')}
    >
      <div className="space-y-4" data-testid="merge-results-modal">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {t('projects.mergeImport.description')}
        </p>

        <div>
          <label
            htmlFor="merge-results-file"
            className="mb-1 block text-sm font-medium text-zinc-900 dark:text-white"
          >
            {t('projects.mergeImport.fileLabel')}
          </label>
          <input
            id="merge-results-file"
            type="file"
            accept={ACCEPTED_FILES}
            disabled={running}
            onChange={(e) => {
              setFile(e.target.files?.[0] || null)
              setError(null)
              setSummary(null)
            }}
            className="block w-full text-sm text-zinc-700 file:mr-3 file:rounded-md file:border-0 file:bg-zinc-100 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-zinc-200 dark:text-zinc-300 dark:file:bg-zinc-800 dark:hover:file:bg-zinc-700"
            data-testid="merge-results-file"
          />
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {t('projects.mergeImport.fileHint')}
          </p>
        </div>

        <div>
          <div className="mb-1 text-sm font-medium text-zinc-900 dark:text-white">
            {t('projects.mergeImport.modelMapTitle')}
          </div>
          <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
            {t('projects.mergeImport.modelMapHint')}
          </p>
          {rows.map((row, index) => (
            <div key={index} className="mb-2 flex items-center gap-2">
              <input
                type="text"
                value={row.source}
                disabled={running}
                onChange={(e) => updateRow(index, { source: e.target.value })}
                placeholder={t('projects.mergeImport.sourceModel')}
                aria-label={t('projects.mergeImport.sourceModel')}
                className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
                data-testid={`merge-model-source-${index}`}
              />
              <span aria-hidden="true" className="text-zinc-400">
                →
              </span>
              <input
                type="text"
                value={row.target}
                disabled={running}
                onChange={(e) => updateRow(index, { target: e.target.value })}
                placeholder={t('projects.mergeImport.targetModel')}
                aria-label={t('projects.mergeImport.targetModel')}
                className="min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
                data-testid={`merge-model-target-${index}`}
              />
              <button
                type="button"
                disabled={running}
                onClick={() =>
                  setRows((current) => current.filter((_, i) => i !== index))
                }
                title={t('projects.mergeImport.removeModel')}
                aria-label={t('projects.mergeImport.removeModel')}
                className="rounded p-1 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
          ))}
          <Button
            variant="outline"
            onClick={() =>
              setRows((current) => [...current, { source: '', target: '' }])
            }
            disabled={running}
            data-testid="merge-add-model"
          >
            <PlusIcon className="mr-1 h-4 w-4" />
            {t('projects.mergeImport.addModel')}
          </Button>
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
            data-testid="merge-results-error"
          >
            {error}
          </div>
        )}

        {summary && (
          <div
            className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
            data-testid="merge-results-summary"
          >
            <p>
              {t('projects.mergeImport.summaryAdded', {
                tasks: summary.matchedTasks,
                generations: added.generations ?? 0,
                evaluations: added.evaluations ?? 0,
                rows: added.task_evaluations ?? 0,
              })}
            </p>
            <p>
              {t('projects.mergeImport.summarySkipped', {
                generations: skipped.generations ?? 0,
                evaluations: skipped.evaluations ?? 0,
              })}
            </p>
            {summary.modelsAdded.length > 0 && (
              <p>
                {t('projects.mergeImport.summaryModels', {
                  models: summary.modelsAdded.join(', '),
                })}
              </p>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={close} disabled={running}>
            {summary ? t('common.close') : t('common.cancel')}
          </Button>
          {!summary && (
            <Button
              onClick={handleMerge}
              disabled={!file || running || incompleteRow}
              data-testid="merge-results-submit"
            >
              {running
                ? t('projects.mergeImport.running')
                : t('projects.mergeImport.submit')}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  )
}
