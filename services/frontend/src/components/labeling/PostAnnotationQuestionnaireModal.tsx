'use client'

import { Dialog, Transition } from '@headlessui/react'
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline'
import { Fragment, useCallback, useState } from 'react'

import { Button } from '@/components/shared/Button'
import { useI18n } from '@/contexts/I18nContext'
import { AnnotationResult } from '@/lib/labelConfig/dataBinding'

import { DynamicAnnotationInterface } from './DynamicAnnotationInterface'

// Stable reference to avoid re-renders — questionnaire items don't reference task data
const EMPTY_TASK_DATA = {}

interface PostAnnotationQuestionnaireModalProps {
  isOpen: boolean
  questionnaireConfig: string
  projectId: string
  taskId: string
  annotationId: string
  onComplete: () => void
  onSubmitResponse: (
    projectId: string,
    taskId: string,
    annotationId: string,
    result: AnnotationResult[]
  ) => Promise<void>
}

export function PostAnnotationQuestionnaireModal({
  isOpen,
  questionnaireConfig,
  projectId,
  taskId,
  annotationId,
  onComplete,
  onSubmitResponse,
}: PostAnnotationQuestionnaireModalProps) {
  const { t } = useI18n()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = useCallback(
    async (annotations: AnnotationResult[]) => {
      setIsSubmitting(true)
      setError(null)
      try {
        await onSubmitResponse(projectId, taskId, annotationId, annotations)
        onComplete()
      } catch (err: any) {
        setError(err?.message || 'Failed to submit questionnaire response')
      } finally {
        setIsSubmitting(false)
      }
    },
    [projectId, taskId, annotationId, onSubmitResponse, onComplete]
  )

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={() => {}}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity dark:bg-zinc-900/80" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="relative flex max-h-[90vh] transform flex-col rounded-lg bg-white text-left shadow-xl transition-all dark:bg-zinc-800 sm:my-8 sm:w-full sm:max-w-2xl">
                {/* Fixed header */}
                <div className="flex-shrink-0 px-4 pt-5 sm:px-6 sm:pt-6">
                  <div className="mb-4 flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
                      <ClipboardDocumentListIcon className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                      <Dialog.Title
                        as="h3"
                        className="text-lg font-semibold leading-6 text-zinc-900 dark:text-white"
                      >
                        {t('annotation.questionnaire.title')}
                      </Dialog.Title>
                      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                        {t('annotation.questionnaire.description')}
                      </p>
                    </div>
                  </div>

                  {/* Error */}
                  {error && (
                    <div className="mb-4 rounded-md bg-red-50 p-3 dark:bg-red-900/20">
                      <p className="text-sm text-red-800 dark:text-red-300">{error}</p>
                    </div>
                  )}
                </div>

                {/* Scrollable form body — kept mounted to preserve state during submit */}
                <div className="relative flex-1 overflow-y-auto px-4 pb-4 sm:px-6 sm:pb-6">
                  {isSubmitting && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/80 dark:bg-zinc-800/80">
                      <div className="text-center">
                        <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-blue-500 border-t-transparent" />
                        <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">
                          {t('annotation.questionnaire.submitting')}
                        </p>
                      </div>
                    </div>
                  )}
                  <DynamicAnnotationInterface
                    labelConfig={questionnaireConfig}
                    taskData={EMPTY_TASK_DATA}
                    onSubmit={handleSubmit}
                    showSubmitButton={true}
                    enableAutoSave={false}
                  />
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  )
}
