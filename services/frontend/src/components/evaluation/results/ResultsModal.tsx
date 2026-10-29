/**
 * ResultDetailsModal — modal that displays generation, evaluation, and
 * annotation result details with tabs. Extracted verbatim from
 * EvaluationResults.tsx; receives its data + open/close handlers via
 * props. The per-tab content panels live in `ResultsTabs`; the tab bar
 * and header/footer chrome stay here because they own `activeTab` and
 * the copy/re-evaluate controls.
 *
 * Output is byte-identical to the previous inline version — the tests
 * render `EvaluationResults` and assert on the modal's rendered text.
 */

'use client'

import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import {
  ArrowPathIcon,
  ClipboardDocumentIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

import { useI18n } from '@/contexts/I18nContext'
import { intlTag } from '@/lib/i18n/locales'

import { ResultsTabs } from './ResultsTabs'
import type {
  AnnotationData,
  EvaluationDetailData,
  GenerationData,
} from './types'

interface ResultDetailsModalProps {
  isOpen: boolean
  onClose: () => void
  taskId: string | null
  modelId: string | null
  annotationData: AnnotationData | null
  generationData: GenerationData | null
  evaluationData: EvaluationDetailData | null
  annotationLoading: boolean
  generationLoading: boolean
  evaluationLoading: boolean
  onReEvaluate?: (
    taskId: string,
    modelId: string,
    selectedConfigIds: string[],
  ) => void
  evaluationConfigs?: Array<{
    id: string
    metric: string
    display_name?: string
    enabled: boolean
  }>
  /** Filters Evaluation Results tab to rows for this metric only.
   * `field_name` shape: "<metric>-<slug>|<pred>|<ref>"; we match by prefix
   * before the first `-`. Pass null/undefined to show everything. */
  selectedMetricName?: string | null
}

/**
 * Modal component for displaying generation and evaluation result details with tabs
 */
export function ResultDetailsModal({
  isOpen,
  onClose,
  taskId,
  modelId,
  annotationData,
  generationData,
  evaluationData,
  annotationLoading,
  generationLoading,
  evaluationLoading,
  onReEvaluate,
  evaluationConfigs = [],
  selectedMetricName = null,
}: ResultDetailsModalProps) {
  const { t, locale } = useI18n()
  const isAnnotatorCell = modelId?.startsWith('annotator:') ?? false
  const [activeTab, setActiveTab] = useState<
    'annotation' | 'generation' | 'evaluation'
  >('annotation')
  const [copySuccess, setCopySuccess] = useState(false)
  const [selectedStructureIndex, setSelectedStructureIndex] = useState(0)
  const [selectedEvalConfigIds, setSelectedEvalConfigIds] = useState<
    Set<string>
  >(new Set())
  const [showMetricSelection, setShowMetricSelection] = useState(false)

  // Reset structure index, metric selection, and default tab when modal opens
  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelectedStructureIndex(0)
      setActiveTab(isAnnotatorCell ? 'annotation' : 'generation')
      // Select all enabled configs by default
      const enabledIds = evaluationConfigs
        .filter((c) => c.enabled !== false)
        .map((c) => c.id)
      setSelectedEvalConfigIds(new Set(enabledIds))
      setShowMetricSelection(false)
    }
  }, [isOpen, generationData, evaluationConfigs, isAnnotatorCell])

  const handleCopyToClipboard = async () => {
    const dataToCopy =
      activeTab === 'annotation'
        ? annotationData
        : activeTab === 'generation'
          ? generationData
          : evaluationData
    if (!dataToCopy) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(dataToCopy, null, 2))
      setCopySuccess(true)
      setTimeout(() => setCopySuccess(false), 2000)
    } catch (error) {
      console.error('Failed to copy to clipboard:', error)
    }
  }

  return (
    <Dialog open={isOpen} onClose={onClose} className="relative z-50">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 dark:bg-black/50"
        aria-hidden="true"
      />

      {/* Full-screen container */}
      <div className="fixed inset-0 flex w-screen items-center justify-center p-4">
        <DialogPanel className="w-full max-w-4xl rounded-2xl bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 p-6 dark:border-zinc-700">
            <div>
              <DialogTitle className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('evaluation.multiFieldResults.taskDetails')}
              </DialogTitle>
              {modelId && (
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {t('evaluation.multiFieldResults.model')}: {modelId}
                  {/* Surface the generation's timestamp + id so the user
                   * can tell which generation the three tabs are
                   * describing. Without this the modal looked identical
                   * for two different generations of the same (task,
                   * model) — the cell that was about to lie. */}
                  {!isAnnotatorCell && generationData && generationData[0] && (
                    <>
                      {' '}
                      · {t('evaluation.multiFieldResults.generation')}:{' '}
                      {generationData[0].generated_at
                        ? new Date(
                            generationData[0].generated_at,
                          ).toLocaleString(intlTag(locale))
                        : (generationData[0].generation_id || '').slice(0, 8) +
                          '…'}
                    </>
                  )}
                  {taskId && (
                    <>
                      {' '}
                      · {t('evaluation.multiFieldResults.task')}:{' '}
                      {taskId.slice(0, 8)}…
                    </>
                  )}
                </p>
              )}
            </div>

            <div className="flex items-center gap-3">
              {/* Copy button */}
              <button
                onClick={handleCopyToClipboard}
                disabled={
                  activeTab === 'annotation'
                    ? !annotationData
                    : activeTab === 'generation'
                      ? !generationData
                      : !evaluationData
                }
                className={`flex h-8 items-center gap-2 rounded-full px-3 text-sm font-medium transition-colors ${
                  copySuccess
                    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400'
                    : 'bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700'
                } disabled:opacity-50`}
              >
                <ClipboardDocumentIcon className="h-4 w-4" />
                {copySuccess
                  ? t('evaluation.multiFieldResults.copied')
                  : t('evaluation.multiFieldResults.copyJson')}
              </button>

              {/* Close button */}
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-zinc-600 transition-colors hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Tab Navigation - show only relevant tabs per cell type */}
          <div className="border-b border-zinc-200 px-6 py-2 dark:border-zinc-700">
            <nav
              className="inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full bg-zinc-100 p-0.5 dark:bg-zinc-800"
              aria-label={t('evaluation.multiFieldResults.tabsLabel')}
            >
              {isAnnotatorCell && (
                <button
                  onClick={() => setActiveTab('annotation')}
                  className={`h-7 rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors ${
                    activeTab === 'annotation'
                      ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                      : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                  } focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900`}
                >
                  {t('evaluation.multiFieldResults.annotationResult')}
                </button>
              )}
              {!isAnnotatorCell && (
                <button
                  onClick={() => setActiveTab('generation')}
                  className={`h-7 rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors ${
                    activeTab === 'generation'
                      ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                      : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                  } focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900`}
                >
                  {t('evaluation.multiFieldResults.generationResults')}
                </button>
              )}
              <button
                onClick={() => setActiveTab('evaluation')}
                className={`h-7 rounded-full px-3 text-sm font-medium whitespace-nowrap transition-colors ${
                  activeTab === 'evaluation'
                    ? 'bg-white text-zinc-900 shadow-sm dark:bg-zinc-700 dark:text-white'
                    : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                } focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-zinc-900`}
              >
                {t('evaluation.multiFieldResults.evaluationResults')}
              </button>
            </nav>
          </div>

          {/* Content */}
          <div className="max-h-[60vh] overflow-y-auto p-6">
            <ResultsTabs
              activeTab={activeTab}
              annotationData={annotationData}
              generationData={generationData}
              evaluationData={evaluationData}
              annotationLoading={annotationLoading}
              generationLoading={generationLoading}
              evaluationLoading={evaluationLoading}
              selectedStructureIndex={selectedStructureIndex}
              setSelectedStructureIndex={setSelectedStructureIndex}
              selectedMetricName={selectedMetricName}
            />
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-zinc-200 p-4 dark:border-zinc-700">
            <div className="flex items-center gap-3">
              {onReEvaluate &&
                taskId &&
                modelId &&
                evaluationConfigs.length > 0 && (
                  <>
                    {showMetricSelection && (
                      <div className="flex flex-wrap items-center gap-2">
                        {evaluationConfigs
                          .filter((c) => c.enabled !== false)
                          .map((config) => (
                            <label
                              key={config.id}
                              className="flex items-center gap-1.5 rounded-md bg-zinc-50 px-2 py-1 text-xs dark:bg-zinc-800"
                            >
                              <input
                                type="checkbox"
                                checked={selectedEvalConfigIds.has(config.id)}
                                onChange={(e) => {
                                  setSelectedEvalConfigIds((prev) => {
                                    const next = new Set(prev)
                                    if (e.target.checked) {
                                      next.add(config.id)
                                    } else {
                                      next.delete(config.id)
                                    }
                                    return next
                                  })
                                }}
                                className="h-3.5 w-3.5 rounded border-zinc-300 text-emerald-600 focus:ring-emerald-500 dark:border-zinc-600"
                              />
                              <span className="text-zinc-700 dark:text-zinc-300">
                                {config.display_name ||
                                  config.metric.replace(/_/g, ' ')}
                              </span>
                            </label>
                          ))}
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      {evaluationConfigs.filter((c) => c.enabled !== false)
                        .length > 1 && (
                        <button
                          onClick={() =>
                            setShowMetricSelection(!showMetricSelection)
                          }
                          className="text-xs text-zinc-500 underline hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
                        >
                          {t('evaluation.multiFieldResults.selectMetrics')}
                        </button>
                      )}
                      <button
                        onClick={() => {
                          onReEvaluate(taskId, modelId, [
                            ...selectedEvalConfigIds,
                          ])
                          onClose()
                        }}
                        disabled={selectedEvalConfigIds.size === 0}
                        className="flex h-8 items-center gap-2 rounded-full bg-zinc-900 px-4 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
                      >
                        <ArrowPathIcon className="h-4 w-4" />
                        {t('evaluation.multiFieldResults.reEvaluate')}
                      </button>
                    </div>
                  </>
                )}
            </div>
            <button
              onClick={onClose}
              className="h-8 rounded-full bg-zinc-100 px-4 text-sm font-medium text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            >
              {t('evaluation.multiFieldResults.close')}
            </button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
