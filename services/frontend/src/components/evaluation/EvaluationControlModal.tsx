'use client'

import { useToast } from '@/components/shared/Toast'
import { useI18n } from '@/contexts/I18nContext'
import { apiClient } from '@/lib/api/client'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { Fragment, useEffect, useState } from 'react'

interface EvaluationControlModalProps {
  isOpen: boolean
  projectId?: string
  evaluationConfigs?: Array<{
    id: string
    metric: string
    display_name?: string
    prediction_fields: string[]
    reference_fields: string[]
    metric_parameters?: Record<string, any>
    enabled?: boolean
  }>
  /** Number of configs to display when using callback mode */
  configCount?: number
  onClose: () => void
  onSuccess?: () => void
  /** If provided, called with mode instead of making API call directly */
  onRunWithMode?: (forceRerun: boolean) => Promise<void>
}

export function EvaluationControlModal({
  isOpen,
  projectId,
  evaluationConfigs,
  configCount,
  onClose,
  onSuccess,
  onRunWithMode,
}: EvaluationControlModalProps) {
  const { addToast } = useToast()
  const { t } = useI18n()
  const [mode, setMode] = useState<'all' | 'missing'>('missing')
  const [loading, setLoading] = useState(false)

  // Calculate number of configs to display
  const displayConfigCount = configCount ?? evaluationConfigs?.length ?? 0

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setMode('missing')
      setLoading(false)
    }
  }, [isOpen])

  const handleSubmit = async () => {
    const forceRerun = mode === 'all'

    // If callback mode is provided, use it instead of making API call
    if (onRunWithMode) {
      try {
        setLoading(true)
        await onRunWithMode(forceRerun)
        onSuccess?.()
        onClose()
      } catch (error: any) {
        console.error('Failed to start evaluation:', error)
        addToast(
          error.message || t('evaluation.controlModal.failedToStart'),
          'error'
        )
      } finally {
        setLoading(false)
      }
      return
    }

    // Direct API mode - requires projectId and evaluationConfigs
    if (!evaluationConfigs || evaluationConfigs.length === 0) {
      addToast(t('evaluation.controlModal.noConfigsFound'), 'error')
      return
    }

    if (!projectId) {
      addToast(t('evaluation.controlModal.projectIdRequired'), 'error')
      return
    }

    try {
      setLoading(true)

      await apiClient.evaluations.runEvaluation({
        project_id: projectId,
        evaluation_configs: evaluationConfigs.map(c => ({ ...c, enabled: c.enabled !== false })),
        force_rerun: forceRerun,
      })

      addToast(t('toasts.project.evaluationStarted'), 'success')
      onSuccess?.()
      onClose()
    } catch (error: any) {
      console.error('Failed to start evaluation:', error)
      addToast(
        error.response?.data?.detail || t('evaluation.controlModal.failedToStart'),
        'error'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity dark:bg-zinc-900 dark:bg-opacity-75" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all dark:bg-zinc-800 sm:my-8 sm:w-full sm:max-w-lg sm:p-6">
                <div className="absolute right-0 top-0 hidden pr-4 pt-4 sm:block">
                  <button
                    type="button"
                    className="rounded-md bg-white text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 dark:bg-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-300"
                    onClick={onClose}
                  >
                    <span className="sr-only">{t('shared.alertDialog.close')}</span>
                    <XMarkIcon className="h-6 w-6" aria-hidden="true" />
                  </button>
                </div>

                <div className="sm:flex sm:items-start">
                  <div className="mt-3 w-full text-center sm:ml-4 sm:mt-0 sm:text-left">
                    <Dialog.Title
                      as="h3"
                      className="text-lg font-semibold leading-6 text-gray-900 dark:text-white"
                    >
                      {t('evaluation.controlModal.title')}
                    </Dialog.Title>

                    <div className="mt-4 space-y-4">
                      {/* Evaluation Mode */}
                      <div>
                        <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-zinc-300">
                          {t('evaluation.controlModal.evaluationMode')}
                        </label>
                        <div className="space-y-2">
                          <div className="flex items-start">
                            <input
                              id="mode-missing"
                              type="radio"
                              value="missing"
                              checked={mode === 'missing'}
                              onChange={(e) =>
                                setMode(e.target.value as 'missing')
                              }
                              className="mr-2 mt-1"
                            />
                            <div>
                              <label
                                htmlFor="mode-missing"
                                className="cursor-pointer font-medium text-gray-900 dark:text-white"
                              >
                                {t('evaluation.controlModal.evaluateMissingOnly')}
                              </label>
                              <p className="text-sm text-gray-500 dark:text-zinc-400">
                                {t('evaluation.controlModal.evaluateMissingOnlyDesc')}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-start">
                            <input
                              id="mode-all"
                              type="radio"
                              value="all"
                              checked={mode === 'all'}
                              onChange={(e) => setMode(e.target.value as 'all')}
                              className="mr-2 mt-1"
                            />
                            <div>
                              <label
                                htmlFor="mode-all"
                                className="cursor-pointer font-medium text-gray-900 dark:text-white"
                              >
                                {t('evaluation.controlModal.evaluateAll')}
                              </label>
                              <p className="text-sm text-gray-500 dark:text-zinc-400">
                                {t('evaluation.controlModal.evaluateAllDesc')}
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Evaluation Config Summary */}
                      {displayConfigCount > 0 && (
                        <div className="rounded-lg border border-gray-300 bg-gray-50 p-3 dark:border-zinc-600 dark:bg-zinc-700">
                          <p className="text-sm font-medium text-gray-700 dark:text-zinc-300">
                            {t('evaluation.controlModal.evaluationConfigurations')}
                          </p>
                          <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-white">
                            {displayConfigCount === 1
                              ? t('evaluation.controlModal.oneConfigWillBeRun')
                              : t('evaluation.controlModal.configsWillBeRun', { count: displayConfigCount })}
                          </p>
                        </div>
                      )}

                      {/* Info */}
                      <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 dark:border-blue-800 dark:bg-blue-900/20">
                        <p className="text-sm text-blue-800 dark:text-blue-300">
                          <strong>{t('evaluation.controlModal.note')}</strong> {t('evaluation.controlModal.backgroundInfo')}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="mt-5 sm:mt-4 sm:flex sm:flex-row-reverse">
                  <button
                    type="button"
                    className="inline-flex w-full justify-center rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 disabled:opacity-50 sm:ml-3 sm:w-auto"
                    onClick={handleSubmit}
                    disabled={loading || (!onRunWithMode && displayConfigCount === 0)}
                  >
                    {loading ? t('evaluation.controlModal.starting') : t('evaluation.controlModal.startEvaluation')}
                  </button>
                  <button
                    type="button"
                    className="mt-3 inline-flex w-full justify-center rounded-md bg-white px-3 py-2 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 dark:bg-zinc-700 dark:text-white dark:ring-zinc-600 dark:hover:bg-zinc-600 sm:mt-0 sm:w-auto"
                    onClick={onClose}
                  >
                    {t('evaluation.controlModal.cancel')}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  )
}
