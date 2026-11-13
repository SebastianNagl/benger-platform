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
 * Custom models get a new id on every deployment. The dialog first uploads
 * the file and asks the server for a preview (nothing is written), which
 * lists every model id of the file and whether it exists here; an id that
 * does not must be mapped to a model of this installation before the merge
 * (the server refuses it otherwise, `merge_unknown_models`).
 */

'use client'

import { Button } from '@/components/shared/Button'
import { Dialog } from '@/components/shared/Dialog'
import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import {
  projectsAPI,
  type MergePreview,
  type MergePreviewModel,
} from '@/lib/api/projects'
import { logger } from '@/lib/utils/logger'
import React, { useState } from 'react'

interface MergeResultsModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  onMergeComplete?: () => void
}

interface MergeSummary {
  matchedTasks: number
  added: Record<string, number>
  skipped: Record<string, number>
  modelsAdded: string[]
}

/** Codes the server gives a refused merge (job error_code or detail.code). */
const MERGE_TASK_MISMATCH = 'merge_task_mismatch'
const MERGE_UNKNOWN_MODELS = 'merge_unknown_models'

const ACCEPTED_FILES = '.json,.ndjson,.gz,.zip'

function errorCode(err: any): string | null {
  const detail = err?.response?.data?.detail
  if (detail && typeof detail === 'object' && typeof detail.code === 'string') {
    return detail.code
  }
  if (typeof err?.code === 'string') return err.code
  const message: string = err?.message || ''
  if (message.includes(MERGE_TASK_MISMATCH)) return MERGE_TASK_MISMATCH
  if (message.includes(MERGE_UNKNOWN_MODELS)) return MERGE_UNKNOWN_MODELS
  return null
}

/** A file model the merge refuses until it is mapped. */
const needsMapping = (model: MergePreviewModel) =>
  !model.known && model.rows_added > 0

export function MergeResultsModal({
  isOpen,
  onClose,
  projectId,
  onMergeComplete,
}: MergeResultsModalProps) {
  const { t } = useI18n()
  const { addToast } = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [objectKey, setObjectKey] = useState<string | null>(null)
  const [preview, setPreview] = useState<MergePreview | null>(null)
  // Source model id in the file -> model id here ('' = leave as it is).
  const [targets, setTargets] = useState<Record<string, string>>({})
  const [checking, setChecking] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<MergeSummary | null>(null)
  const busy = checking || running

  const reset = () => {
    setFile(null)
    setObjectKey(null)
    setPreview(null)
    setTargets({})
    setChecking(false)
    setRunning(false)
    setError(null)
    setSummary(null)
  }

  const close = () => {
    if (busy) return
    reset()
    onClose()
  }

  const describeError = (err: any, fallback: string): string => {
    const code = errorCode(err)
    if (code === MERGE_TASK_MISMATCH)
      return t('projects.mergeImport.taskMismatch')
    if (code === MERGE_UNKNOWN_MODELS)
      return t('projects.mergeImport.unknownModels')
    return err?.message || fallback
  }

  const modelIdMap = (): Record<string, string> => {
    const map: Record<string, string> = {}
    for (const [source, target] of Object.entries(targets)) {
      if (target && target !== source) map[source] = target
    }
    return map
  }

  const unmapped = (preview?.models || []).filter(
    (model) => needsMapping(model) && !targets[model.source_model_id],
  )

  const handleCheck = async () => {
    if (!file) return
    setChecking(true)
    setError(null)
    try {
      const key =
        objectKey || (await projectsAPI.uploadImportFile(projectId, file))
      setObjectKey(key)
      const result = await projectsAPI.previewMergeImport(projectId, key)
      setPreview(result)
      setTargets(
        Object.fromEntries(result.models.map((m) => [m.source_model_id, ''])),
      )
    } catch (err: any) {
      logger.error('Merge preview failed', err)
      setError(describeError(err, t('projects.mergeImport.checkFailed')))
    } finally {
      setChecking(false)
    }
  }

  const handleMerge = async () => {
    if (!file || !objectKey) return
    setRunning(true)
    setError(null)
    setSummary(null)
    try {
      const status = await projectsAPI.runMergeImportJob(
        projectId,
        file,
        undefined,
        {
          modelIdMap: modelIdMap(),
          objectKey,
        },
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
      setError(describeError(err, t('projects.mergeImport.failed')))
    } finally {
      setRunning(false)
    }
  }

  const modelName = (id: string): string =>
    preview?.available_models.find((m) => m.id === id)?.name ||
    preview?.models.find((m) => m.model_id === id)?.name ||
    id

  const added = summary?.added || {}
  const skipped = summary?.skipped || {}
  const willAdd = preview?.added_counts || {}

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
            disabled={busy}
            onChange={(e) => {
              setFile(e.target.files?.[0] || null)
              setObjectKey(null)
              setPreview(null)
              setTargets({})
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

        {preview && !summary && (
          <div data-testid="merge-preview">
            <p className="mb-2 text-sm text-zinc-700 dark:text-zinc-300">
              {t('projects.mergeImport.previewAdds', {
                tasks: preview.matched_tasks,
                generations: willAdd.generations ?? 0,
                evaluations: willAdd.evaluations ?? 0,
                rows: willAdd.task_evaluations ?? 0,
              })}
            </p>
            {preview.models.length > 0 && (
              <>
                <div className="mb-1 text-sm font-medium text-zinc-900 dark:text-white">
                  {t('projects.mergeImport.modelMapTitle')}
                </div>
                <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
                  {t('projects.mergeImport.modelMapHint')}
                </p>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-zinc-500 dark:text-zinc-400">
                      <th className="pb-1 font-medium">
                        {t('projects.mergeImport.sourceModel')}
                      </th>
                      <th className="pb-1 font-medium">
                        {t('projects.mergeImport.targetModel')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.models.map((model, index) => {
                      const required = needsMapping(model)
                      const missing =
                        required && !targets[model.source_model_id]
                      return (
                        <tr key={model.source_model_id} className="align-top">
                          <td className="py-1 pr-2">
                            <div className="font-mono text-xs break-all text-zinc-800 dark:text-zinc-200">
                              {model.source_model_id}
                            </div>
                            <div className="text-xs text-zinc-500 dark:text-zinc-400">
                              {t('projects.mergeImport.modelRows', {
                                added: model.rows_added,
                                present: model.rows_present,
                              })}
                            </div>
                          </td>
                          <td className="py-1">
                            <select
                              value={targets[model.source_model_id] || ''}
                              disabled={busy}
                              onChange={(e) =>
                                setTargets((current) => ({
                                  ...current,
                                  [model.source_model_id]: e.target.value,
                                }))
                              }
                              aria-label={t('projects.mergeImport.targetFor', {
                                model: model.source_model_id,
                              })}
                              aria-invalid={missing}
                              className={`w-full rounded-md border bg-white px-2 py-1.5 text-sm dark:bg-zinc-900 dark:text-white ${
                                missing
                                  ? 'border-red-400 dark:border-red-700'
                                  : 'border-zinc-300 dark:border-zinc-700'
                              }`}
                              data-testid={`merge-model-target-${index}`}
                            >
                              <option value="">
                                {model.known
                                  ? t('projects.mergeImport.keepModel', {
                                      model: model.name || model.model_id,
                                    })
                                  : t('projects.mergeImport.chooseModel')}
                              </option>
                              {preview.available_models.map((option) => (
                                <option key={option.id} value={option.id}>
                                  {option.is_custom
                                    ? `${option.name} (${option.id})`
                                    : option.name}
                                </option>
                              ))}
                            </select>
                            {missing && (
                              <p className="mt-1 text-xs text-red-700 dark:text-red-300">
                                {t('projects.mergeImport.unknownModel')}
                              </p>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </>
            )}
          </div>
        )}

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
                  models: summary.modelsAdded.map(modelName).join(', '),
                })}
              </p>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={close} disabled={busy}>
            {summary ? t('common.close') : t('common.cancel')}
          </Button>
          {!summary && !preview && (
            <Button
              onClick={handleCheck}
              disabled={!file || busy}
              data-testid="merge-results-check"
            >
              {checking
                ? t('projects.mergeImport.checking')
                : t('projects.mergeImport.check')}
            </Button>
          )}
          {!summary && preview && (
            <Button
              onClick={handleMerge}
              disabled={busy || unmapped.length > 0}
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
