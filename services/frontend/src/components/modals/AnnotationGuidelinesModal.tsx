import { useI18n } from '@/contexts/I18nContext'
import { Dialog } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'

interface AnnotationGuidelinesModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (guidelines: string) => void
  initialValue?: string
}

export function AnnotationGuidelinesModal({
  isOpen,
  onClose,
  onSave,
  initialValue = '',
}: AnnotationGuidelinesModalProps) {
  const { t } = useI18n()
  const [guidelines, setGuidelines] = useState(initialValue)

  // Update local state when initialValue changes
  useEffect(() => {
    setGuidelines(initialValue)
  }, [initialValue])

  const handleSave = () => {
    onSave(guidelines.trim())
    onClose()
  }

  const handleCancel = () => {
    // Reset to initial value on cancel
    setGuidelines(initialValue)
    onClose()
  }

  return (
    <Dialog open={isOpen} onClose={handleCancel} className="relative z-50">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />

      {/* Full-screen container to center the panel */}
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-3xl rounded-lg bg-white shadow-xl dark:bg-zinc-800">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <div>
              <Dialog.Title className="text-lg font-semibold text-zinc-900 dark:text-white">
                {t('modals.annotationGuidelines.title')}
              </Dialog.Title>
              <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                {t('modals.annotationGuidelines.subtitle')}
              </p>
            </div>
            <button
              onClick={handleCancel}
              className="rounded-md p-2 text-zinc-400 transition-colors hover:text-zinc-500 dark:text-zinc-500 dark:hover:text-zinc-400"
              aria-label={t('shared.alertDialog.close')}
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-4">
            <div className="space-y-4">
              <div>
                <label
                  htmlFor="annotation-guidelines"
                  className="mb-2 block text-sm font-medium text-zinc-900 dark:text-white"
                >
                  {t('modals.annotationGuidelines.textareaLabel')}
                </label>
                <textarea
                  id="annotation-guidelines"
                  value={guidelines}
                  onChange={(e) => setGuidelines(e.target.value)}
                  rows={8}
                  className="block w-full resize-none rounded-lg border border-zinc-300 bg-white px-3 py-2.5 text-zinc-900 transition-colors placeholder:text-zinc-500 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 dark:border-zinc-600 dark:bg-zinc-800 dark:text-white dark:placeholder:text-zinc-400 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/20 sm:text-sm"
                  placeholder={t('modals.annotationGuidelines.textareaPlaceholder')}
                />
              </div>

              <div className="rounded-lg bg-amber-50 p-4 dark:bg-amber-900/20">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg
                      className="h-5 w-5 text-amber-400"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-amber-800 dark:text-amber-200">
                      <strong>{t('modals.annotationGuidelines.helpTitle')}</strong>
                    </p>
                    <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-amber-700 dark:text-amber-300">
                      <li>{t('modals.annotationGuidelines.helpItem1')}</li>
                      <li>{t('modals.annotationGuidelines.helpItem2')}</li>
                      <li>{t('modals.annotationGuidelines.helpItem3')}</li>
                      <li>{t('modals.annotationGuidelines.helpItem4')}</li>
                      <li>{t('modals.annotationGuidelines.helpItem5')}</li>
                    </ul>
                  </div>
                </div>
              </div>

              <div className="rounded-lg bg-emerald-50 p-4 dark:bg-emerald-900/20">
                <div className="flex">
                  <div className="flex-shrink-0">
                    <svg
                      className="h-5 w-5 text-emerald-400"
                      viewBox="0 0 20 20"
                      fill="currentColor"
                    >
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <p className="text-sm text-emerald-800 dark:text-emerald-200">
                      <strong>{t('modals.annotationGuidelines.proTip')}</strong>{' '}
                      {t('modals.annotationGuidelines.proTipText')}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 border-t border-zinc-200 px-6 py-4 dark:border-zinc-700">
            <button
              onClick={handleCancel}
              className="rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-50 dark:border-zinc-600 dark:bg-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-600"
            >
              {t('modals.annotationGuidelines.cancel')}
            </button>
            <button
              onClick={handleSave}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600"
            >
              {t('modals.annotationGuidelines.save')}
            </button>
          </div>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}
