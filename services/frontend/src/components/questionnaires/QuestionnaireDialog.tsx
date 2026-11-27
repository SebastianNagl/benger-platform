'use client'

/**
 * A questionnaire in a modal, for the moments that follow an action: after a
 * submission (`after_submit`) and after saving a Korrektur (`korrektur`).
 * It cannot be dismissed: it closes once answered, or skipped when the
 * questionnaire is optional.
 */

import { Dialog, Transition } from '@headlessui/react'
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline'
import { Fragment } from 'react'

import { useI18n } from '@/contexts/I18nContext'
import type { QuestionnaireTrigger } from '@/lib/api/questionnaires'
import type { AnnotationResult } from '@/lib/labelConfig/dataBinding'

import { QuestionnaireForm } from './QuestionnaireForm'

export interface QuestionnaireDialogProps {
  isOpen: boolean
  trigger: QuestionnaireTrigger
  config: string
  required: boolean
  onSubmit: (result: AnnotationResult[]) => Promise<void>
  onSkip?: () => Promise<void>
  /** Remounts the form (fresh answers) when it changes. */
  formKey?: string
}

export function QuestionnaireDialog({
  isOpen,
  trigger,
  config,
  required,
  onSubmit,
  onSkip,
  formKey,
}: QuestionnaireDialogProps) {
  const { t } = useI18n()
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
          <div className="fixed inset-0 bg-black/30 transition-opacity dark:bg-black/50" />
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
              <Dialog.Panel
                className="relative flex max-h-[90vh] w-full transform flex-col rounded-2xl bg-white text-left shadow-xl transition-all sm:my-8 sm:max-w-2xl dark:bg-zinc-800"
                data-testid={`questionnaire-dialog-${trigger}`}
              >
                <div className="shrink-0 px-4 pt-5 sm:px-6 sm:pt-6">
                  <div className="mb-4 flex items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-700">
                      <ClipboardDocumentListIcon className="h-6 w-6 text-zinc-500 dark:text-zinc-300" />
                    </div>
                    <div>
                      <Dialog.Title
                        as="h3"
                        className="text-lg leading-6 font-semibold text-zinc-900 dark:text-white"
                      >
                        {t(`questionnaires.moments.${trigger}.promptTitle`)}
                      </Dialog.Title>
                      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                        {t(
                          `questionnaires.moments.${trigger}.promptDescription`,
                        )}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto px-4 pb-4 sm:px-6 sm:pb-6">
                  <QuestionnaireForm
                    formKey={formKey}
                    config={config}
                    required={required}
                    onSubmit={onSubmit}
                    onSkip={onSkip}
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
